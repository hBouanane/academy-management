"""All /api routes. Thin handlers: parse, delegate to crud/services, serialize."""

import sqlite3
from collections.abc import Iterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.adapters.sqlite import crud
from app.adapters.sqlite.db import connect
from app.adapters.sqlite.payment_store import SqlitePaymentStore
from app.adapters.sqlite.reports import arrears, monthly_report
from app.domain.adjustments import AdjustmentSpec
from app.domain.splitting import Beneficiary
from app.ports.payments import ConfiguredAdjustment, UnknownEnrollmentError
from app.services import clock
from app.services.payments import (
    complete_payment,
    guarantee_unpaid,
    payment_preview,
    post_payment,
    reverse_payment,
    validate_adjustment,
)
from app.services.proration import prorated_price

router = APIRouter()

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
Month = Annotated[str, StringConstraints(pattern=MONTH_PATTERN)]
MonthPath = Annotated[str, Path(pattern=MONTH_PATTERN)]
MonthQuery = Annotated[str, Query(pattern=MONTH_PATTERN)]


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    connection = connect(request.app.state.db_path)
    try:
        yield connection
    finally:
        connection.close()


Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


def default_academy_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM academy ORDER BY id LIMIT 1").fetchone()
    return row["id"]


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "app": "academy-management"}


def _require_open_month(month: str) -> None:
    """History is not a workspace: months before the current one are locked
    for structural changes (enrollments, reductions). Paying stays allowed."""
    if month < clock.current_month():
        raise HTTPException(
            status_code=409,
            detail="Mois passé — verrouillé. Les mois écoulés ne se modifient plus ;"
            " seul l'encaissement des impayés reste possible.",
        )


def _require_open_enrollment_month(
    conn: sqlite3.Connection, enrollment_id: int
) -> None:
    month = crud.enrollment_month(conn, enrollment_id)
    if month is None:
        raise UnknownEnrollmentError(f"no enrollment {enrollment_id}")
    _require_open_month(month)


# --- structure -----------------------------------------------------------


class AcademyPatch(BaseModel):
    name: str | None = None
    venue_bp: int | None = None
    owner_bp: int | None = None
    proration_bp: list[int] | None = None  # month segments, e.g. [10000, 6700, 3300]


@router.get("/academies")
def academies(conn: Conn) -> list[dict]:
    return crud.list_academies(conn)


@router.patch("/academies/{academy_id}")
def patch_academy(academy_id: int, patch: AcademyPatch, conn: Conn) -> dict:
    fields = patch.model_dump(exclude_none=True)
    if "proration_bp" in fields:
        segments = fields.pop("proration_bp")
        if not (1 <= len(segments) <= 12) or any(
            not 0 <= bp <= 10_000 for bp in segments
        ):
            raise HTTPException(
                status_code=422,
                detail="Prorata : entre 1 et 12 tranches, chacune entre 0 et 100%.",
            )
        import json

        fields["proration_json"] = json.dumps(segments)
    crud.update_academy(conn, academy_id, fields)
    updated = next(
        (a for a in crud.list_academies(conn) if a["id"] == academy_id), None
    )
    if updated is None:
        raise LookupError(f"no academy {academy_id}")
    return updated


class LevelCreate(BaseModel):
    name: str
    # 0 = one teaching block (Primaire, Formation); N = split into N années.
    teaching_annees: int = Field(0, ge=0, le=12)


@router.get("/levels")
def levels(conn: Conn) -> list[dict]:
    return crud.list_levels(conn, default_academy_id(conn))


@router.post("/levels", status_code=201)
def create_level(body: LevelCreate, conn: Conn) -> dict:
    academy_id = default_academy_id(conn)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Le nom du niveau est requis.")
    if any(
        level["name"].lower() == name.lower()
        for level in crud.list_levels(conn, academy_id)
    ):
        raise HTTPException(
            status_code=422, detail=f"Le niveau « {name} » existe déjà."
        )
    return {"id": crud.create_level(conn, academy_id, name, body.teaching_annees)}


def _ten_digit_phone(value: str) -> str:
    digits = value.replace(" ", "").replace("-", "").replace(".", "")
    if not (digits.isdigit() and len(digits) == 10):
        raise ValueError("le téléphone doit contenir exactement 10 chiffres")
    return digits


class PhoneField(BaseModel):
    """Phones are normalized to digits and must hold exactly 10 of them.

    None or "" pass through: "" downstream means "clear the stored phone"."""

    phone: str | None = None

    @field_validator("phone")
    @classmethod
    def _ten_digits(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return value
        return _ten_digit_phone(value)


class PhoneIn(BaseModel):
    """One tagged phone line: étudiant, mère, père, …"""

    tag: str
    number: str

    @field_validator("number")
    @classmethod
    def _ten_digits(cls, value: str) -> str:
        return _ten_digit_phone(value)


class NamedCreate(PhoneField):
    name: str


class SubjectPatch(BaseModel):
    # No is_active here: matières cannot be archived — only renamed, or
    # deleted while no class references them.
    name: str | None = None


class LifecyclePatch(PhoneField):
    name: str | None = None
    is_active: bool | None = None
    is_owner: bool | None = None  # teachers only: this teacher IS the owner


def _lifecycle_fields(patch: BaseModel) -> dict:
    fields = patch.model_dump(exclude_none=True)
    for flag in ("is_active", "is_owner"):
        if flag in fields:
            fields[flag] = int(fields[flag])
    if fields.get("phone") == "":
        fields["phone"] = None  # an emptied phone field means "clear it"
    return fields


@router.get("/subjects")
def subjects(conn: Conn) -> list[dict]:
    return crud.list_subjects(conn, default_academy_id(conn))


class SubjectCreate(BaseModel):
    name: str
    # Obligatoire : une matière appartient à SON niveau. Sans lui elle
    # n'apparaîtrait nulle part — c'est l'ancien « Tous niveaux » qu'on a
    # supprimé (migration 0012).
    level_id: int


@router.post("/subjects", status_code=201)
def create_subject(body: SubjectCreate, conn: Conn) -> dict:
    return {
        "id": crud.create_subject(
            conn, default_academy_id(conn), body.name, body.level_id
        )
    }


@router.patch("/subjects/{subject_id}")
def patch_subject(subject_id: int, patch: SubjectPatch, conn: Conn) -> dict:
    crud.update_subject(conn, subject_id, _lifecycle_fields(patch))
    return {"id": subject_id}


@router.delete("/subjects/{subject_id}")
def delete_subject(subject_id: int, conn: Conn) -> dict:
    """A matière deletes outright (capabilities and never-enrolled archived
    classes go with it) — unless active classes still use it, or archived
    classes carry real enrollment history the ledger must keep."""
    blockers = crud.subject_delete_blockers(conn, subject_id)
    if blockers["active"]:
        raise HTTPException(
            status_code=409,
            detail=f"Cette matière a {blockers['active']} classe(s) active(s)"
            " — gérez-les d'abord (remplacez le professeur, archivez ou"
            " supprimez-les).",
        )
    if blockers["archived_with_history"]:
        raise HTTPException(
            status_code=409,
            detail=f"{blockers['archived_with_history']} classe(s) archivée(s)"
            " de cette matière portent un historique d'inscriptions — la"
            " matière doit rester consultable.",
        )
    crud.delete_subject(conn, subject_id)
    return {"deleted": subject_id}


@router.get("/teachers")
def teachers(
    conn: Conn, include_inactive: bool = False, month: MonthQuery | None = None
) -> list[dict]:
    return crud.list_teachers(
        conn,
        default_academy_id(conn),
        include_inactive,
        month or clock.current_month(),
    )


@router.post("/teachers", status_code=201)
def create_teacher(body: NamedCreate, conn: Conn) -> dict:
    academy_id = default_academy_id(conn)
    return {"id": crud.create_teacher(conn, academy_id, body.name, body.phone or None)}


@router.patch("/teachers/{teacher_id}")
def patch_teacher(teacher_id: int, patch: LifecyclePatch, conn: Conn) -> dict:
    if patch.is_active is False:
        count = crud.teacher_open_class_count(conn, teacher_id)
        if count:
            raise HTTPException(
                status_code=409,
                detail=f"Ce professeur enseigne encore {count} classe(s) —"
                " remplacez-le, laissez la classe sans professeur, ou"
                " archivez la classe d'abord.",
            )
    crud.update_teacher(conn, teacher_id, _lifecycle_fields(patch))
    return {"id": teacher_id}


class ClassCreate(BaseModel):
    level_id: int
    subject_id: int
    teacher_id: int
    name: str = "A"
    annee: int | None = Field(None, ge=1, le=6)
    filiere: str | None = None
    parcours: str | None = None
    day_of_week: int | None = None
    start_time: str | None = None


class ClassPatch(BaseModel):
    name: str | None = None
    level_id: int | None = None
    subject_id: int | None = None
    teacher_id: int | None = None
    annee: int | None = Field(None, ge=1, le=6)
    filiere: str | None = None
    parcours: str | None = None
    day_of_week: int | None = None
    start_time: str | None = None
    is_active: bool | None = None


class ReplaceTeacherBody(BaseModel):
    date: Annotated[str, StringConstraints(pattern=DATE_PATTERN)]
    # Une classe, un professeur : la reprise se donne à quelqu'un. Deux
    # professeurs sur le même créneau ? Dédoublez la classe.
    successor_id: int


class DuplicateBody(BaseModel):
    teacher_id: int | None = None


class CapabilityIn(BaseModel):
    level_id: int
    annee: int | None = Field(None, ge=1, le=6)
    parcours: str | None = None
    subject_id: int


class CapabilitiesBody(BaseModel):
    items: list[CapabilityIn]


@router.get("/classes")
def classes(
    conn: Conn, include_inactive: bool = False, month: MonthQuery | None = None
) -> list[dict]:
    return crud.list_classes(
        conn,
        default_academy_id(conn),
        include_inactive,
        month or clock.current_month(),
    )


@router.post("/classes", status_code=201)
def create_class(body: ClassCreate, conn: Conn) -> dict:
    academy_id = default_academy_id(conn)
    return {"id": crud.create_class(conn, academy_id, body.model_dump())}


@router.patch("/classes/{class_id}")
def patch_class(class_id: int, patch: ClassPatch, conn: Conn) -> dict:
    crud.update_class(conn, class_id, _lifecycle_fields(patch))
    return {"id": class_id}


@router.post("/classes/{class_id}/replace-teacher")
def replace_teacher(class_id: int, body: ReplaceTeacherBody, conn: Conn) -> dict:
    """Dated handover: the outgoing teacher earns up to the day before,
    successors from that day on — old months keep paying whoever taught."""
    crud.replace_teacher(conn, class_id, body.date, body.successor_id)
    return {"id": class_id}


@router.post("/classes/{class_id}/duplicate", status_code=201)
def duplicate_class(class_id: int, body: DuplicateBody, conn: Conn) -> dict:
    return {"id": crud.duplicate_class(conn, class_id, body.teacher_id)}


@router.delete("/classes/{class_id}")
def delete_class(class_id: int, conn: Conn) -> dict:
    """The 'created by mistake' escape hatch — refused the moment any
    student was ever enrolled: history archives, it never disappears."""
    if crud.class_has_enrollments(conn, class_id):
        raise HTTPException(
            status_code=409,
            detail="Des élèves ont été inscrits dans cette classe — archivez"
            " plutôt, l'historique doit rester.",
        )
    crud.delete_class(conn, class_id)
    return {"deleted": class_id}


class VacateBody(BaseModel):
    date: Annotated[str, StringConstraints(pattern=DATE_PATTERN)]


@router.post("/classes/{class_id}/vacate-teacher")
def vacate_teacher(class_id: int, body: VacateBody, conn: Conn) -> dict:
    """No successor yet: the class survives « Sans professeur »; vacant days
    escrow the teacher share to the académie until someone is named."""
    crud.vacate_teacher(conn, class_id, body.date)
    return {"id": class_id}


class RefundChoice(BaseModel):
    enrollment_id: int
    percent_bp: Annotated[int, Field(ge=0, le=10_000)]


class ArchiveClassBody(BaseModel):
    date: Annotated[str, StringConstraints(pattern=DATE_PATTERN)]
    refunds: list[RefundChoice] = []


@router.post("/classes/{class_id}/archive")
def archive_class(class_id: int, body: ArchiveClassBody, conn: Conn) -> dict:
    """The class dies: paid students get pending refunds at their chosen
    percentage of what they actually paid; unpaid students simply lose the
    class (an impayé gets no money back — he never paid)."""
    for choice in body.refunds:
        if not crud.enrollment_is_paid(conn, choice.enrollment_id):
            raise HTTPException(
                status_code=422,
                detail="Cette inscription est en impayé — on ne rembourse"
                " pas un mois jamais encaissé.",
            )
    refund_ids = crud.archive_class_with_refunds(
        conn,
        default_academy_id(conn),
        class_id,
        body.date,
        [choice.model_dump() for choice in body.refunds],
        clock.current_month(),
    )
    return {"id": class_id, "refund_ids": refund_ids}


@router.get("/refunds")
def refunds(conn: Conn) -> list[dict]:
    """The « Remboursements » place: every promise, pending first."""
    return crud.list_refunds(conn, default_academy_id(conn))


@router.post("/refunds/{refund_id}/settle")
def settle_refund(refund_id: int, conn: Conn) -> dict:
    refund = crud.refund_row(conn, refund_id)
    if refund is None:
        raise LookupError(f"no refund {refund_id}")
    if refund["status"] == "settled":
        raise HTTPException(status_code=409, detail="Déjà remboursé.")
    crud.settle_refund(conn, refund, clock.current_month())
    return {"id": refund_id, "status": "settled"}


@router.get("/capabilities")
def capabilities(conn: Conn) -> list[dict]:
    return crud.list_capabilities(conn, default_academy_id(conn))


@router.put("/teachers/{teacher_id}/capabilities")
def put_capabilities(teacher_id: int, body: CapabilitiesBody, conn: Conn) -> dict:
    crud.set_capabilities(conn, teacher_id, [item.model_dump() for item in body.items])
    return {"id": teacher_id}


@router.get("/teachers/{teacher_id}/profile")
def teacher_profile(
    teacher_id: int, conn: Conn, month: MonthQuery | None = None
) -> dict:
    profile = crud.teacher_profile(conn, teacher_id, month or clock.current_month())
    if profile is None:
        raise LookupError(f"no teacher {teacher_id}")
    return profile


@router.get("/classes/{class_id}/absence.docx")
def absence_sheet_route(class_id: int, month: MonthQuery, conn: Conn) -> Response:
    from app.adapters.docx.absence_sheet import absence_sheet

    content = absence_sheet(conn, class_id, month)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument"
        ".wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="absence-{month}.docx"'},
    )


class MotifBody(BaseModel):
    label: str


class MotifPatch(BaseModel):
    label: str | None = None
    is_active: bool | None = None


@router.get("/motifs")
def motifs(conn: Conn, include_inactive: bool = False) -> list[dict]:
    return crud.list_motifs(conn, default_academy_id(conn), include_inactive)


@router.post("/motifs", status_code=201)
def create_motif(body: MotifBody, conn: Conn) -> dict:
    return {"id": crud.create_motif(conn, default_academy_id(conn), body.label)}


@router.patch("/motifs/{motif_id}")
def patch_motif(motif_id: int, patch: MotifPatch, conn: Conn) -> dict:
    crud.update_motif(conn, motif_id, _lifecycle_fields(patch))
    return {"id": motif_id}


class PackageCreate(BaseModel):
    subject_count: int
    monthly_price_centimes: int
    level_id: int | None = None
    # Price variants (bloc niveaux): a name for the price point — NOT a
    # reduction. « 1ère–4ème année », « Cas particulier », …
    label: str | None = None


class PackagePatch(BaseModel):
    subject_count: int | None = None
    monthly_price_centimes: int | None = None
    level_id: int | None = None
    is_active: bool | None = None
    label: str | None = None


@router.get("/packages")
def packages(conn: Conn, include_inactive: bool = False) -> list[dict]:
    return crud.list_packages(conn, default_academy_id(conn), include_inactive)


@router.post("/packages", status_code=201)
def create_package(body: PackageCreate, conn: Conn) -> dict:
    academy_id = default_academy_id(conn)
    if body.level_id is not None:
        _check_package_fits_level(conn, body.level_id, body.subject_count)
    package_id = crud.create_package(
        conn,
        academy_id,
        body.subject_count,
        body.monthly_price_centimes,
        body.level_id,
        body.label,
    )
    return {"id": package_id}


def _check_package_fits_level(
    conn: sqlite3.Connection, level_id: int, subject_count: int
) -> None:
    """A forfait must not promise more matières than the niveau teaches.
    A 1-matière forfait always passes: price variants (Primaire) are set up
    BEFORE the classes exist, and enrolling still requires a real class."""
    taught = crud.subjects_taught_at_level(conn, level_id)
    if subject_count > max(taught, 1):
        raise HTTPException(
            status_code=422,
            detail=f"Ce niveau n'enseigne que {taught} matière(s) —"
            f" impossible de créer un forfait de {subject_count}.",
        )


@router.patch("/packages/{package_id}")
def patch_package(package_id: int, patch: PackagePatch, conn: Conn) -> dict:
    row = crud.package_row(conn, package_id)
    if row is None:
        raise LookupError(f"no package {package_id}")
    effective_level = patch.level_id if patch.level_id is not None else row["level_id"]
    effective_count = (
        patch.subject_count if patch.subject_count is not None else row["subject_count"]
    )
    if effective_level is not None:
        _check_package_fits_level(conn, effective_level, effective_count)
    crud.update_package(conn, package_id, _lifecycle_fields(patch))
    return {"id": package_id}


# --- students ------------------------------------------------------------


class StudentCreate(PhoneField):
    name: str
    first_name: str | None = None
    level_id: int
    annee: int | None = Field(None, ge=1, le=6)
    filiere: str | None = None
    parcours: str | None = None
    school: str | None = None
    phones: list[PhoneIn] = []


class StudentPatch(PhoneField):
    name: str | None = None
    first_name: str | None = None
    level_id: int | None = None
    annee: int | None = Field(None, ge=1, le=6)
    filiere: str | None = None
    parcours: str | None = None
    school: str | None = None
    phones: list[PhoneIn] | None = None
    is_active: bool | None = None


def _student_fields(body: StudentCreate | StudentPatch, conn, academy_id: int) -> dict:
    """API shape -> storage shape: the school name becomes a managed-list id,
    the legacy single `phone` becomes a tagged line, and the first tagged
    number is denormalized back into student.phone for lists and exports."""
    fields = body.model_dump(
        exclude_none=True, exclude={"school", "phones", "is_active"}
    )
    if isinstance(body, StudentPatch) and body.is_active is not None:
        fields["is_active"] = int(body.is_active)
    if body.school is not None:
        fields["school_id"] = (
            crud.get_or_create_school(conn, academy_id, body.school)
            if body.school
            else None
        )
    phones = body.phones
    if not phones and body.phone:
        phones = [PhoneIn(tag="étudiant", number=body.phone)]
    if phones is not None:
        fields["phones"] = [phone.model_dump() for phone in phones]
        fields["phone"] = phones[0].number if phones else None
    return fields


@router.get("/students")
def students(
    conn: Conn, include_inactive: bool = False, month: MonthQuery | None = None
) -> list[dict]:
    return crud.list_students(
        conn,
        default_academy_id(conn),
        include_inactive,
        month or clock.current_month(),
    )


@router.post("/students", status_code=201)
def create_student(body: StudentCreate, conn: Conn) -> dict:
    academy_id = default_academy_id(conn)
    student_id = crud.create_student(
        conn, academy_id, _student_fields(body, conn, academy_id)
    )
    return {"id": student_id}


@router.get("/schools")
def schools(conn: Conn) -> list[dict]:
    return crud.list_schools(conn, default_academy_id(conn))


@router.get("/filieres")
def filieres(conn: Conn) -> list[str]:
    """Every filière ever typed — the dropdown suggests them back."""
    return crud.list_filieres(conn, default_academy_id(conn))


@router.get("/students/{student_id}/profile")
def student_profile(student_id: int, conn: Conn) -> dict:
    profile = crud.student_profile(conn, student_id)
    if profile is None:
        raise LookupError(f"no student {student_id}")
    return profile


@router.patch("/students/{student_id}")
def patch_student(student_id: int, patch: StudentPatch, conn: Conn) -> dict:
    fields = _student_fields(patch, conn, default_academy_id(conn))
    if patch.phone == "" and patch.phones is None:
        fields["phone"] = None  # legacy "clear it" path
        fields["phones"] = []
    crud.update_student(conn, student_id, fields)
    return {"id": student_id}


# --- enrollments & months ------------------------------------------------


class EnrollmentCreate(BaseModel):
    student_id: int
    month: Month
    package_id: int
    class_ids: list[int]
    price_centimes: int | None = None
    # Mid-month arrival: the price is prorated by the academy's segments.
    arrival_date: Annotated[str, StringConstraints(pattern=DATE_PATTERN)] | None = None


class BearerIn(BaseModel):
    kind: Literal["owner", "venue", "teacher"]
    ref_id: int
    # Sponsor part: explicit centimes OR a % of the reduction; both empty
    # (on every sponsor) means "equal split".
    share_centimes: Annotated[int, Field(ge=0)] | None = None
    share_bp: Annotated[int, Field(ge=0, le=10_000)] | None = None


def _require_unique_bearers(bearers: list[BearerIn]) -> None:
    seen = {(b.kind, b.ref_id) for b in bearers}
    if len(seen) != len(bearers):
        raise HTTPException(
            status_code=422,
            detail="Un même sponsor ne peut apparaître qu'une seule fois.",
        )


def _shares_spec(
    bearers: list[BearerIn],
) -> tuple[tuple[int | None, int | None], ...] | None:
    spec = tuple((b.share_centimes, b.share_bp) for b in bearers)
    if all(c is None and bp is None for c, bp in spec):
        return None
    return spec


class AdjustmentCreate(BaseModel):
    kind: Literal["percent", "amount"]
    value: int  # basis points for 'percent' (10000 = 100%), centimes for 'amount'
    scope: Literal["package", "subject"] = "package"
    class_id: int | None = None
    category: Literal["discount", "coupon", "gift"] = "discount"
    reason: str | None = None
    recurring: bool = False  # follow the enrollment into every next month?
    bearers: list[BearerIn] = []


@router.get("/months/{month}/overview")
def overview(month: MonthPath, conn: Conn) -> list[dict]:
    return crud.month_overview(conn, default_academy_id(conn), month)


@router.post("/enrollments", status_code=201)
def create_enrollment(body: EnrollmentCreate, conn: Conn) -> dict:
    # Backfill is allowed: he really started in August, entered in September —
    # the past month's enrollment lands directly as an unpaid arrear.
    price = body.price_centimes
    if price is None and body.arrival_date is not None:
        from datetime import date

        try:
            arrival = date.fromisoformat(body.arrival_date)
        except ValueError:
            raise HTTPException(
                status_code=422, detail="Date d'arrivée invalide."
            ) from None
        if body.arrival_date[:7] != body.month:
            raise HTTPException(
                status_code=422,
                detail="La date d'arrivée doit être dans le mois d'inscription.",
            )
        package = crud.package_row(conn, body.package_id)
        if package is None:
            raise LookupError(f"no package {body.package_id}")
        price = prorated_price(
            package["monthly_price_centimes"],
            crud.academy_proration(conn, default_academy_id(conn)),
            body.month,
            arrival.day,
        )
    enrollment_id = crud.create_enrollment(
        conn,
        body.student_id,
        body.month,
        body.package_id,
        body.class_ids,
        price,
        arrival_date=body.arrival_date,
    )
    return {"id": enrollment_id}


@router.delete("/enrollments/{enrollment_id}")
def delete_enrollment(enrollment_id: int, conn: Conn) -> dict:
    """Un-enroll a student from an open month — the escape hatch for a
    browsed-ahead future month or a cancellation before any money moved."""
    month = crud.enrollment_month(conn, enrollment_id)
    if month is None:
        raise UnknownEnrollmentError(f"no enrollment {enrollment_id}")
    _require_open_month(month)
    if crud.enrollment_has_payment_history(conn, enrollment_id):
        raise HTTPException(
            status_code=409,
            detail="Cette inscription a un historique de paiement — elle ne"
            " peut plus être supprimée (contre-passez plutôt le paiement).",
        )
    crud.delete_enrollment(conn, enrollment_id)
    return {"deleted": enrollment_id}


def _require_unpaid_enrollment(conn: sqlite3.Connection, enrollment_id: int) -> None:
    """Reductions follow the enrollment's payment state, not the calendar:
    an UNPAID month — even a past one — can still be negotiated (that is how
    arrears get settled, and how reverse-then-fix corrections work). A paid
    month must be reversed first."""
    if crud.enrollment_month(conn, enrollment_id) is None:
        raise UnknownEnrollmentError(f"no enrollment {enrollment_id}")
    if crud.enrollment_is_paid(conn, enrollment_id):
        raise HTTPException(
            status_code=409,
            detail="Mois déjà encaissé — contre-passez le paiement avant de"
            " modifier les réductions.",
        )


@router.post("/enrollments/{enrollment_id}/adjustments", status_code=201)
def create_adjustment(enrollment_id: int, body: AdjustmentCreate, conn: Conn) -> dict:
    _require_unpaid_enrollment(conn, enrollment_id)
    _require_unique_bearers(body.bearers)
    _check_adjustment_is_postable(conn, enrollment_id, body)
    adjustment_id = crud.add_adjustment(conn, enrollment_id, body.model_dump())
    return {"id": adjustment_id}


def _check_adjustment_is_postable(
    conn: sqlite3.Connection, enrollment_id: int, body: AdjustmentCreate
) -> None:
    """Reject unpostable adjustments with 422 BEFORE anything is stored."""
    context = SqlitePaymentStore(conn).enrollment_context(enrollment_id)
    if context is None:
        raise UnknownEnrollmentError(f"no enrollment {enrollment_id}")
    subject_index = None
    if body.scope == "subject":
        class_ids = crud.enrollment_class_ids(conn, enrollment_id)
        if body.class_id not in class_ids:
            raise ValueError(f"class {body.class_id} is not in this enrollment")
        subject_index = class_ids.index(body.class_id)
    spec = AdjustmentSpec(
        kind=body.kind, value=body.value, scope=body.scope, subject_index=subject_index
    )
    bearers = tuple(Beneficiary(b.kind, b.ref_id) for b in body.bearers) or (
        Beneficiary("owner", context.owner_id),
    )
    validate_adjustment(
        context,
        ConfiguredAdjustment(
            0,
            spec,
            bearers,
            shares_spec=_shares_spec(body.bearers),
            category=body.category,
        ),
    )


@router.delete("/adjustments/{adjustment_id}")
def delete_adjustment(adjustment_id: int, conn: Conn) -> dict:
    row = crud.adjustment_row(conn, adjustment_id)
    if row is None:
        raise LookupError(f"no adjustment {adjustment_id}")
    _require_unpaid_enrollment(conn, row["enrollment_id"])
    crud.delete_adjustment(conn, adjustment_id)
    return {"deleted": adjustment_id}


class AdjustmentPatch(BaseModel):
    kind: Literal["percent", "amount"] | None = None
    value: int | None = None
    category: Literal["discount", "coupon", "gift"] | None = None
    reason: str | None = None
    recurring: bool | None = None
    bearers: list[BearerIn] | None = None


@router.patch("/adjustments/{adjustment_id}")
def patch_adjustment(adjustment_id: int, body: AdjustmentPatch, conn: Conn) -> dict:
    """Edit a reduction in place — no delete-and-recreate dance."""
    row = crud.adjustment_row(conn, adjustment_id)
    if row is None:
        raise LookupError(f"no adjustment {adjustment_id}")
    _require_unpaid_enrollment(conn, row["enrollment_id"])
    if body.bearers is not None:
        _require_unique_bearers(body.bearers)
    if body.kind is not None and body.kind != row["kind"] and body.value is None:
        raise HTTPException(
            status_code=422,
            detail="Changer l'unité (DH ↔ %) exige aussi la nouvelle valeur —"
            " sinon les centimes seraient relus comme des pourcentages.",
        )
    _validate_adjustment_edit(conn, row, body)
    fields = body.model_dump(exclude_none=True, exclude={"bearers"})
    bearers = (
        [bearer.model_dump() for bearer in body.bearers]
        if body.bearers is not None
        else None
    )
    crud.update_adjustment(conn, adjustment_id, fields, bearers)
    return {"id": adjustment_id}


def _validate_adjustment_edit(
    conn: sqlite3.Connection, row: dict, body: AdjustmentPatch
) -> None:
    """Validate the merged (existing + patch) adjustment against the enrollment
    with THIS adjustment excluded — never store an unpostable state."""
    from dataclasses import replace as dc_replace

    store = SqlitePaymentStore(conn)
    context = store.enrollment_context(row["enrollment_id"])
    if context is None:
        raise UnknownEnrollmentError(f"no enrollment {row['enrollment_id']}")
    context = dc_replace(
        context,
        adjustments=tuple(
            configured
            for configured in context.adjustments
            if configured.adjustment_id != row["id"]
        ),
    )
    merged_kind = body.kind or row["kind"]
    merged_value = body.value if body.value is not None else row["value"]
    subject_index = None
    if row["scope"] == "subject":
        class_ids = crud.enrollment_class_ids(conn, row["enrollment_id"])
        subject_index = class_ids.index(row["class_id"])
    spec = AdjustmentSpec(
        kind=merged_kind,
        value=merged_value,
        scope=row["scope"],
        subject_index=subject_index,
    )
    if body.bearers is not None:
        bearers = tuple(Beneficiary(b.kind, b.ref_id) for b in body.bearers)
        shares_spec = _shares_spec(body.bearers)
    else:
        stored_bearers = crud.adjustment_bearers(conn, row["id"])
        bearers = tuple(Beneficiary(b["kind"], b["ref_id"]) for b in stored_bearers)
        spec_tuple = tuple((b["share_centimes"], b["share_bp"]) for b in stored_bearers)
        shares_spec = (
            None
            if all(c is None and bp is None for c, bp in spec_tuple)
            else spec_tuple
        )
    if not bearers:
        bearers = (Beneficiary("owner", context.owner_id),)
        shares_spec = None
    validate_adjustment(
        context,
        ConfiguredAdjustment(
            0,
            spec,
            bearers,
            shares_spec=shares_spec,
            category=body.category or row["category"],
        ),
    )


def _stored_bp(conn: sqlite3.Connection, adjustment_id: int, bearer) -> int | None:
    row = conn.execute(
        "SELECT share_bp FROM adjustment_bearer WHERE adjustment_id = ?"
        " AND bearer_kind = ? AND bearer_id = ?",
        (adjustment_id, bearer.kind, bearer.ref_id),
    ).fetchone()
    return row["share_bp"] if row else None


class GuaranteeBody(BaseModel):
    # Until when the student actually attended; None = the whole month.
    present_until: Annotated[str, StringConstraints(pattern=DATE_PATTERN)] | None = None
    never_came: bool = False  # nothing taught, nothing owed to anyone
    stop: bool = False  # « il a arrêté » : don't carry him into next month


@router.post("/enrollments/{enrollment_id}/guarantee")
def guarantee(enrollment_id: int, body: GuaranteeBody, conn: Conn) -> dict:
    """Solder un impayé côté professeur : il est payé pour les jours
    enseignés, l'académie avance — et la salle encaisse le coup avec elle."""
    month = crud.enrollment_month(conn, enrollment_id)
    if month is None:
        raise UnknownEnrollmentError(f"no enrollment {enrollment_id}")
    if crud.enrollment_is_paid(conn, enrollment_id):
        raise HTTPException(
            status_code=409,
            detail="Ce mois est déjà encaissé — le professeur a été payé"
            " normalement, il n'y a rien à garantir.",
        )
    if body.present_until is not None and body.present_until[:7] != month:
        raise HTTPException(
            status_code=422,
            detail="La date de présence doit être dans le mois concerné.",
        )
    posted = guarantee_unpaid(
        SqlitePaymentStore(conn),
        enrollment_id,
        None if body.never_came else body.present_until,
        body.never_came,
    )
    if body.stop:
        crud.stop_enrollment(conn, enrollment_id)
    return {
        "enrollment_id": enrollment_id,
        "amount_centimes": posted.amount,
        "shares": [
            {"teacher_id": teacher_id, "amount_centimes": amount}
            for teacher_id, amount in posted.shares
        ],
    }


# --- versements aux professeurs -------------------------------------------


class PayoutBody(BaseModel):
    month: Month
    amount_centimes: int | None = None  # None = tout ce qui reste
    note: str | None = None


class CaissePayoutBody(PayoutBody):
    kind: Literal["teacher", "venue", "owner"]
    ref_id: int


@router.get("/caisse")
def caisse(month: MonthQuery, conn: Conn) -> dict:
    """L'état de la caisse : entré, sorti, ce qu'il reste dedans, et la part
    de chacun — professeurs, salle et académie comprises."""
    return crud.caisse_summary(conn, default_academy_id(conn), month)


def _record_payout(
    conn: sqlite3.Connection, kind: str, ref_id: int, body: PayoutBody
) -> dict:
    academy_id = default_academy_id(conn)
    remaining = crud.beneficiary_remaining(conn, academy_id, kind, ref_id, body.month)
    amount = body.amount_centimes if body.amount_centimes is not None else remaining
    if amount <= 0 or amount > remaining:
        raise HTTPException(
            status_code=422,
            detail=f"Il reste {remaining / 100:.2f} DH à verser pour ce mois —"
            f" impossible de sortir {amount / 100:.2f} DH de la caisse.",
        )
    payout_id = crud.add_payout(
        conn, academy_id, kind, ref_id, body.month, amount, body.note
    )
    return {"id": payout_id, "amount_centimes": amount}


@router.post("/payouts", status_code=201)
def create_caisse_payout(body: CaissePayoutBody, conn: Conn) -> dict:
    """Sortir de la caisse la part d'un bénéficiaire — professeur, salle ou
    le propriétaire lui-même : il se paie comme il paie les autres."""
    return _record_payout(conn, body.kind, body.ref_id, body)


@router.delete("/payouts/{payout_id}")
def delete_payout(payout_id: int, conn: Conn) -> dict:
    """Correction d'une saisie — le versement n'a jamais eu lieu."""
    crud.delete_payout(conn, payout_id)
    return {"deleted": payout_id}


@router.get("/enrollments/{enrollment_id}/preview")
def enrollment_preview(enrollment_id: int, conn: Conn) -> dict:
    """The split a payment would produce — shown before any money moves."""
    from app.adapters.sqlite.reports import _beneficiary_name

    preview = payment_preview(SqlitePaymentStore(conn), enrollment_id)
    stored = {
        row["id"]: row
        for row in conn.execute(
            "SELECT id, kind, value, category, scope, reason, recurring"
            " FROM adjustment WHERE enrollment_id = ? AND is_active = 1",
            (enrollment_id,),
        )
    }

    def named(beneficiary):
        return {
            "kind": beneficiary.kind,
            "ref_id": beneficiary.ref_id,
            "name": _beneficiary_name(conn, beneficiary.kind, beneficiary.ref_id),
        }

    return {
        "month": crud.enrollment_month(conn, enrollment_id),
        "price_centimes": preview.price,
        "net_centimes": preview.net,
        "lines": [
            {
                **named(line.beneficiary),
                "base_centimes": line.base,
                "adjustment_centimes": line.adjustment,
                "final_centimes": line.final,
            }
            for line in preview.lines
        ],
        "adjustments": [
            {
                "id": adjustment.adjustment_id,
                "resolved_centimes": adjustment.reduction,
                "kind": stored[adjustment.adjustment_id]["kind"],
                "value": stored[adjustment.adjustment_id]["value"],
                "category": stored[adjustment.adjustment_id]["category"],
                "scope": stored[adjustment.adjustment_id]["scope"],
                "reason": stored[adjustment.adjustment_id]["reason"],
                "recurring": stored[adjustment.adjustment_id]["recurring"],
                "bearers": [
                    {
                        **named(bearer),
                        "share_centimes": share,
                        "share_bp": _stored_bp(conn, adjustment.adjustment_id, bearer),
                    }
                    for bearer, share in zip(
                        adjustment.bearers, adjustment.shares, strict=True
                    )
                ],
            }
            for adjustment in preview.adjustments
        ],
    }


@router.post("/months/{month}/ensure")
def ensure_month(month: MonthPath, conn: Conn) -> dict:
    """Agenda model: entering an open month extends the latest enrolled month
    before it (idempotent; one-off reductions are deliberately NOT carried —
    they are per-month decisions). Walking back over skipped months means a
    summer break does not empty the agenda in September."""
    if month < clock.current_month():
        raise HTTPException(
            status_code=409,
            detail="Les mois passés sont verrouillés — rien ne s'y ajoute.",
        )
    academy_id = default_academy_id(conn)
    source = crud.latest_enrolled_month_before(conn, academy_id, month)
    if source is None:
        return {"extended": 0, "from_month": None}
    extended = crud.copy_month(conn, academy_id, source, month)
    return {"extended": extended, "from_month": source}


# --- payments ------------------------------------------------------------


class PaymentCreate(BaseModel):
    enrollment_id: int
    paid_on: Annotated[str, StringConstraints(pattern=DATE_PATTERN)] | None = None
    # Less than the net = an avance: every beneficiary gets his FULL share,
    # the académie fronts the missing part until the student completes.
    amount_centimes: int | None = None


class ReverseBody(BaseModel):
    reason: str | None = None


class CompleteBody(BaseModel):
    amount_centimes: int | None = None  # None = the whole remaining amount


@router.post("/payments", status_code=201)
def create_payment(body: PaymentCreate, conn: Conn) -> dict:
    posted = post_payment(
        SqlitePaymentStore(conn),
        body.enrollment_id,
        body.paid_on,
        amount=body.amount_centimes,
    )
    return {"payment_id": posted.payment_id, "net_centimes": posted.net_amount}


@router.post("/payments/{payment_id}/complete")
def complete(payment_id: int, body: CompleteBody, conn: Conn) -> dict:
    """A later installment on an avance — cash in, straight back to the
    académie that fronted it."""
    posted = complete_payment(
        SqlitePaymentStore(conn), payment_id, body.amount_centimes
    )
    return {"payment_id": payment_id, "posted_centimes": posted}


@router.post("/payments/{payment_id}/reverse")
def reverse(payment_id: int, body: ReverseBody, conn: Conn) -> dict:
    reversed_payment = reverse_payment(
        SqlitePaymentStore(conn), payment_id, body.reason
    )
    return {"payment_id": reversed_payment.payment_id}


# --- reports -------------------------------------------------------------


@router.get("/reports/monthly")
def report_monthly(month: MonthQuery, conn: Conn) -> dict:
    report = monthly_report(conn, default_academy_id(conn), month)
    return {
        "month": report.month,
        "cash_in": report.cash_in,
        "last_entry_at": report.last_entry_at,
        "totals": [vars(t) for t in report.totals],
        "by_level": [
            {
                "level_id": level.level_id,
                "level_name": level.level_name,
                "totals": [vars(t) for t in level.totals],
            }
            for level in report.by_level
        ],
    }


@router.get("/export/monthly.xlsx")
def export_monthly(month: MonthQuery, conn: Conn) -> Response:
    from app.adapters.excel.monthly_workbook import monthly_workbook

    content = monthly_workbook(conn, default_academy_id(conn), month)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="paiements-{month}.xlsx"'
        },
    )


@router.get("/reports/history")
def report_history(
    up_to_month: MonthQuery, conn: Conn, months: int = Query(6, ge=1, le=24)
) -> list[dict]:
    from app.adapters.sqlite.reports import history

    return history(conn, default_academy_id(conn), up_to_month, months)


@router.get("/reports/arrears")
def report_arrears(up_to_month: MonthQuery, conn: Conn) -> list[dict]:
    return [
        {
            "student_id": entry.student_id,
            "student_name": entry.student_name,
            "level_name": entry.level_name,
            "total_owed": entry.total_owed,
            "items": [vars(item) for item in entry.items],
        }
        for entry in arrears(conn, default_academy_id(conn), up_to_month)
    ]
