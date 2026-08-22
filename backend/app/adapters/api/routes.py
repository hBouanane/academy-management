"""All /api routes. Thin handlers: parse, delegate to crud/services, serialize."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC
from pathlib import Path as FsPathlib
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.adapters.api import vendor
from app.adapters.sqlite import crud
from app.adapters.sqlite.db import connect
from app.adapters.sqlite.payment_store import SqlitePaymentStore
from app.adapters.sqlite.reports import arrears, monthly_report
from app.domain import lock as lock_rules
from app.domain.adjustments import AdjustmentSpec
from app.domain.contact import whatsapp_number
from app.domain.splitting import Beneficiary
from app.ports.payments import ConfiguredAdjustment, UnknownEnrollmentError
from app.services import clock, documents
from app.services.payments import (
    complete_payment,
    guarantee_unpaid,
    net_price,
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


# --- le verrou ------------------------------------------------------------


class CodeBody(BaseModel):
    code: Annotated[str, StringConstraints(min_length=4, max_length=64)]


class RecoverBody(CodeBody):
    phrase: str


class LockPatch(BaseModel):
    code: str | None = None
    new_code: Annotated[str, StringConstraints(min_length=4, max_length=64)] | None = (
        None
    )
    auto_lock_minutes: Annotated[int, Field(ge=1, le=240)] | None = None


def _secret(row: dict, prefix: str) -> lock_rules.Secret:
    return lock_rules.Secret(salt=row[f"{prefix}_salt"], digest=row[f"{prefix}_digest"])


def _refuse_if_impatient(sessions) -> None:
    """Guessing a short code is a minute's work if attempts are unlimited.
    The recovery phrase opens as much as the code does: both doors
    therefore wait alike.
    """
    waiting = sessions.seconds_to_wait()
    if waiting > 0:
        raise HTTPException(
            status_code=429,
            detail=f"Trop d'essais — patientez {waiting} seconde(s).",
        )


def _lock_row(conn: sqlite3.Connection) -> dict:
    row = crud.read_lock(conn)
    if row is None:
        raise HTTPException(status_code=409, detail="Aucun code n'est posé.")
    return row


@router.get("/lock")
def lock_state(request: Request, conn: Conn) -> dict:
    """Toujours joignable, même verrouillé : sinon l'écran de
    déverrouillage n'aurait rien à quoi se raccrocher."""
    row = crud.read_lock(conn)
    return {
        "configured": row is not None,
        "auto_lock_minutes": row["auto_lock_minutes"] if row else 5,
        "unlocked": request.app.state.sessions.holds(
            request.headers.get("X-Session-Token")
            or request.cookies.get("academy_session")
        ),
    }


@router.post("/lock", status_code=201)
def pose_lock(body: CodeBody, conn: Conn) -> dict:
    """Set the code, once. The recovery phrase is returned HERE and nowhere
    else: this is the only time it will be readable.
    """
    if crud.read_lock(conn) is not None:
        raise HTTPException(
            status_code=409,
            detail="Un code est déjà posé — changez-le plutôt que d'en poser"
            " un second.",
        )
    phrase = lock_rules.recovery_phrase()
    crud.write_lock(conn, lock_rules.seal(body.code), lock_rules.seal(phrase))
    return {"recovery_phrase": phrase}


@router.post("/lock/unlock")
def unlock(body: CodeBody, request: Request, response: Response, conn: Conn) -> dict:
    row = _lock_row(conn)
    sessions = request.app.state.sessions
    _refuse_if_impatient(sessions)
    if not lock_rules.matches(body.code, _secret(row, "code")):
        sessions.note_failure()
        raise HTTPException(status_code=401, detail="Code incorrect.")
    token = sessions.open()
    # The cookie serves downloads only, which cannot carry a header. It
    # dies with the window, like the session itself.
    response.set_cookie(
        "academy_session", token, httponly=True, samesite="strict", path="/"
    )
    return {"token": token}


@router.post("/lock/lock")
def relock(request: Request, response: Response) -> dict:
    """Quitter son poste : tous les jetons meurent d'un coup."""
    request.app.state.sessions.close_all()
    response.delete_cookie("academy_session", path="/")
    return {"locked": True}


@router.post("/lock/recover")
def recover(body: RecoverBody, request: Request, conn: Conn) -> dict:
    """The phrase written on paper sets a new code -- the only way back into
    an application with no network.
    """
    row = _lock_row(conn)
    _refuse_if_impatient(request.app.state.sessions)
    if not lock_rules.matches(body.phrase.strip().lower(), _secret(row, "recovery")):
        request.app.state.sessions.note_failure()
        raise HTTPException(status_code=401, detail="Phrase de secours incorrecte.")
    # La phrase a servi : on en tire une neuve, l'ancienne ne vaut plus.
    phrase = lock_rules.recovery_phrase()
    crud.write_lock(conn, lock_rules.seal(body.code), lock_rules.seal(phrase))
    return {"recovery_phrase": phrase}


class RescueBody(BaseModel):
    answer: str
    code: Annotated[str, StringConstraints(min_length=4, max_length=64)]


def _installation_id(conn: sqlite3.Connection) -> str:
    """What distinguishes THIS installation. Drawn once, kept forever: it is
    what makes a rescue valid for one academy only.
    """
    import secrets

    row = conn.execute(
        "SELECT value FROM app_setting WHERE key = 'installation_id'"
    ).fetchone()
    if row:
        return row["value"]
    fresh = secrets.token_hex(8)
    conn.execute(
        "INSERT INTO app_setting (key, value) VALUES ('installation_id', ?)",
        (fresh,),
    )
    conn.commit()
    return fresh


@router.get("/lock/rescue")
def rescue_challenge(conn: Conn) -> dict:
    """The challenge to read out to the vendor. With no key in this build
    there is nothing to show, and the button does not appear.
    """
    if vendor.vendor_key() is None:
        return {"available": False}
    return {
        "available": True,
        "challenge": vendor.challenge_for(_installation_id(conn)),
    }


@router.post("/lock/rescue")
def rescue(body: RescueBody, request: Request, conn: Conn) -> dict:
    """The last resort: both the code AND the phrase are lost.

    The vendor dictates the answer to the day's challenge; the academy
    leaves with a new code AND a new recovery phrase -- rescuing must not
    deprive the owner of his own door.
    """
    key = vendor.vendor_key()
    if key is None:
        raise HTTPException(
            status_code=404, detail="Cette version n'a pas de dépannage éditeur."
        )
    _lock_row(conn)
    _refuse_if_impatient(request.app.state.sessions)
    challenge = vendor.challenge_for(_installation_id(conn))
    if not vendor.answer_matches(key, challenge, body.answer):
        request.app.state.sessions.note_failure()
        raise HTTPException(status_code=401, detail="Réponse incorrecte.")
    phrase = lock_rules.recovery_phrase()
    crud.write_lock(conn, lock_rules.seal(body.code), lock_rules.seal(phrase))
    return {"recovery_phrase": phrase}


@router.patch("/lock")
def change_lock(body: LockPatch, conn: Conn) -> dict:
    row = _lock_row(conn)
    if body.new_code is not None:
        if body.code is None or not lock_rules.matches(body.code, _secret(row, "code")):
            raise HTTPException(status_code=401, detail="Code actuel incorrect.")
        crud.set_code(conn, lock_rules.seal(body.new_code))
    if body.auto_lock_minutes is not None:
        crud.set_auto_lock(conn, body.auto_lock_minutes)
    return {"updated": True}


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
    # Mandatory: a matière belongs to ITS level. Without one it would
    # appear nowhere -- this is the old « Tous niveaux » that was removed
    # (migration 0012).
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
    # One class, one teacher: a handover goes to somebody. Two teachers on
    # the same slot? Split the class in two.
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


@router.get("/classes/{class_id}/profile")
def class_profile(class_id: int, conn: Conn, month: MonthQuery | None = None) -> dict:
    """One class's record: its slot, its teacher, the succession of those who
    taught it, and this month's enrolled students.
    """
    profile = crud.class_profile(conn, class_id, month or clock.current_month())
    if profile is None:
        raise LookupError(f"no class_group {class_id}")
    return profile


class ShareIn(BaseModel):
    teacher_id: int
    share_bp: Annotated[int, Field(ge=0, le=10_000)]


class ShareBody(BaseModel):
    month: Month
    shares: list[ShareIn] = Field(min_length=1)


@router.get("/classes/{class_id}/share")
def class_share(class_id: int, conn: Conn, month: MonthQuery | None = None) -> dict:
    """The split between teachers for this month: automatic (pro rata by days
    taught) or fixed by the owner.
    """
    share = crud.class_share(conn, class_id, month or clock.current_month())
    if share is None:
        raise LookupError(f"no class_group {class_id}")
    return share


@router.put("/classes/{class_id}/share")
def set_class_share(class_id: int, body: ShareBody, conn: Conn) -> dict:
    """The owner decides himself. In percentages: a fixed amount would become
    wrong the moment a student enrolls or a reduction lands. Months already
    collected do not move -- the ledger is never rewritten; this applies to
    future collections.
    """
    total = sum(share.share_bp for share in body.shares)
    if total != 10_000:
        raise HTTPException(
            status_code=422,
            detail=f"Les parts doivent faire 100% en tout — elles font"
            f" {total / 100:.2f}%.",
        )
    if len({share.teacher_id for share in body.shares}) != len(body.shares):
        raise HTTPException(
            status_code=422,
            detail="Un même professeur ne peut apparaître qu'une seule fois.",
        )
    if crud.class_share(conn, class_id, body.month) is None:
        raise LookupError(f"no class_group {class_id}")
    crud.set_class_share(
        conn, class_id, body.month, [share.model_dump() for share in body.shares]
    )
    return {"id": class_id, "month": body.month}


@router.delete("/classes/{class_id}/share")
def clear_class_share(class_id: int, conn: Conn, month: MonthQuery) -> dict:
    """Revenir au prorata des jours enseignés."""
    crud.clear_class_share(conn, class_id, month)
    return {"id": class_id, "month": month}


@router.get("/teachers/{teacher_id}/invoice.docx")
def teacher_invoice_route(
    teacher_id: int,
    month: MonthQuery,
    conn: Conn,
    payout: Annotated[int | None, Query()] = None,
) -> Response:
    """The month's payslip, printable and signable on both halves.

    With a payout named, it becomes that payout's receipt: this is the one
    signed at the moment of paying.
    """
    import unicodedata

    from app.adapters.docx.teacher_invoice import teacher_invoice

    content = teacher_invoice(conn, teacher_id, month, payout)
    row = conn.execute(
        "SELECT name FROM teacher WHERE id = ?", (teacher_id,)
    ).fetchone()
    # The name inside the filename: ten sheets in one folder, and you
    # must know which is which without opening them.
    ascii_name = (
        unicodedata.normalize("NFKD", row["name"]).encode("ascii", "ignore").decode()
    )
    slug = "-".join(part for part in ascii_name.split() if part) or "professeur"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument"
        ".wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="paie-{slug}-{month}.docx"'
        },
    )


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


def _touched(conn: sqlite3.Connection, enrollment_id: int) -> None:
    """State what this action has just made stale, by name.

    One line per write: the write itself knows who it touches, and that is
    what allows a PRECISE warning rather than shouting « this month
    changed » across every document.
    """
    month = crud.enrollment_month(conn, enrollment_id)
    if month is None:
        return
    documents.touch(conn, month, documents.scopes_of_enrollment(conn, enrollment_id))
    conn.commit()
    _refile_quietly(conn)


def _refile_quietly(conn: sqlite3.Connection) -> None:
    """Redo what has just aged, without saying so.

    An August impayé arriving in November makes August's export stale: we
    redo it at once rather than demand a click. And if that fails -- folder
    moved, disk full -- the user's action still completes: it is his
    payment that matters, not our filing.
    """
    try:
        reconcile_documents(conn)
    except Exception:  # noqa: BLE001, S110 - un rangement ne casse pas un paiement
        pass


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
    _touched(conn, enrollment_id)
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
    # What is actually given. Absent: whatever the days taught say.
    # C'est son argent : il peut donner moins, ou davantage.
    amount_centimes: int | None = None


@router.get("/enrollments/{enrollment_id}/guarantee")
def guarantee_proposal(
    enrollment_id: int,
    conn: Conn,
    present_until: Annotated[str | None, Query(pattern=DATE_PATTERN)] = None,
) -> dict:
    """What we suggest giving the teacher, and the ceiling.

    The suggestion follows the days taught; the ceiling is the month's
    price -- beyond it, this is a typo, not generosity.
    """
    store = SqlitePaymentStore(conn)
    context = store.enrollment_context(enrollment_id)
    if context is None:
        raise UnknownEnrollmentError(f"no enrollment {enrollment_id}")
    from app.services.payments import guarantee_proposal as proposed

    return proposed(context, present_until)


def _check_guarantee_amount(
    store: SqlitePaymentStore, enrollment_id: int, amount: int
) -> None:
    """A negative amount makes no sense, and beyond the month's price it is a
    typo -- we do not let one extra zero through on an entry that touches
    money.
    """
    if amount < 0:
        raise HTTPException(
            status_code=422, detail="Le montant ne peut pas etre negatif."
        )
    context = store.enrollment_context(enrollment_id)
    if context is None:
        raise UnknownEnrollmentError(f"no enrollment {enrollment_id}")
    ceiling = net_price(context)
    if amount > ceiling:
        raise HTTPException(
            status_code=422,
            detail=f"Le mois vaut {_dh(ceiling)} — impossible d'en avancer"
            f" {_dh(amount)} au professeur.",
        )


@router.post("/enrollments/{enrollment_id}/guarantee")
def guarantee(enrollment_id: int, body: GuaranteeBody, conn: Conn) -> dict:
    """Settle an impayé on the teacher's side: he is paid for the days taught,
    the academie fronts it -- and the salle takes the hit with it.
    """
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
    store = SqlitePaymentStore(conn)
    if body.amount_centimes is not None:
        _check_guarantee_amount(store, enrollment_id, body.amount_centimes)
    posted = guarantee_unpaid(
        store,
        enrollment_id,
        None if body.never_came else body.present_until,
        body.never_came,
        body.amount_centimes,
    )
    if body.stop:
        crud.stop_enrollment(conn, enrollment_id)
    _touched(conn, enrollment_id)
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
    """Take a beneficiary's share out of the till -- teacher, salle, or the
    owner himself: he pays himself the way he pays the others.

    A teacher's receipt is filed here, at the moment the money moves. It
    is the paper he signs for what he has just been handed, so it should
    exist without being asked for -- and printing it later must send THAT
    file, not produce a second one.

    Filing can never fail the payout: the money moved, and our paperwork
    comes second.
    """
    made = _record_payout(conn, body.kind, body.ref_id, body)
    if body.kind == "teacher" and _backup_root(conn) is not None:
        try:
            file_document(
                FileDocumentBody(
                    kind="payslip",
                    month=body.month,
                    ref_id=body.ref_id,
                    payout_id=made["id"],
                ),
                conn,
            )
        except Exception:  # noqa: BLE001, S110 - filing never blocks a payout
            pass
    return made


def _default_printer() -> str | None:
    """The printer Windows will send it to, by name.

    Worth saying out loud: on a machine whose default is « Microsoft Print
    to PDF », the document goes to a FILE and a dialog asks where to put
    it. That looks like a fault in the application, when it is the printer
    doing exactly its job. Naming it turns a mystery into a fact the owner
    can act on.
    """
    try:
        import winreg
    except ImportError:  # not Windows
        return None
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows NT\CurrentVersion\Windows",
        )
        device = winreg.QueryValueEx(key, "Device")[0]
    except OSError:
        return None
    # « Nom,pilote,port » -- only the name means anything to him.
    return device.split(",")[0] or None


def _print_file(path: str) -> None:
    """Send a file to the default printer, the way Windows does it.

    os.startfile with the « print » verb hands it to whatever program owns
    the extension -- Word for a .docx -- and lets that program print it. If
    the machine has no printer or no Word, opening it is still better than
    a button that appears to do nothing.
    """
    import os

    opener = getattr(os, "startfile", None)
    if opener is None:
        return
    try:
        opener(path, "print")
    except OSError:
        opener(path)


@router.post("/payouts/{payout_id}/print")
def print_receipt(payout_id: int, conn: Conn) -> dict:
    """Print the receipt that was filed when the money moved.

    Not a download: it was already filed at the payout, and handing him a
    second copy in his Downloads folder is how two versions of one signed
    paper start existing.
    """
    path = documents.receipt_path(conn, payout_id)
    if path is None or not FsPathlib(path).exists():
        # Payouts made before receipts were filed automatically -- or while
        # no folder was chosen -- have no paper at all. A receipt that does
        # not exist cannot be frozen, so producing it now beats a button
        # that answers « not found »; it is frozen from then on.
        row = conn.execute(
            "SELECT month, beneficiary_id FROM payout"
            " WHERE id = ? AND beneficiary_kind = 'teacher'",
            (payout_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Versement inconnu.")
        filed = file_document(
            FileDocumentBody(
                kind="payslip",
                month=row["month"],
                ref_id=row["beneficiary_id"],
                payout_id=payout_id,
            ),
            conn,
        )
        path = filed["path"]
    _print_file(path)
    return {"path": path, "printer": _default_printer()}


@router.delete("/payouts/{payout_id}")
def delete_payout(payout_id: int, conn: Conn) -> dict:
    """Correction d'une saisie — le versement n'a jamais eu lieu.

    The receipt is renamed, never removed: the professor may already hold
    the signed sheet, and deleting our copy does not retrieve his. A file
    marked « annule » makes the mismatch visible instead of silent.

    Renaming must not be able to fail the cancellation itself -- that is
    the owner's decision about money, and our filing comes second.
    """
    renamed = None
    try:
        renamed = documents.cancel_receipt(conn, payout_id)
    except Exception:  # noqa: BLE001, S110 - filing never blocks a correction
        pass
    crud.delete_payout(conn, payout_id)
    return {"deleted": payout_id, "receipt": renamed}


class OverpaidChargeBody(BaseModel):
    kind: Literal["teacher", "venue", "owner"]
    ref_id: int
    month: Month
    amount_centimes: int | None = None  # None = the whole overpayment
    note: str | None = None


@router.post("/overpaid-charges", status_code=201)
def take_overpaid_charge(body: OverpaidChargeBody, conn: Conn) -> dict:
    """The academie writes off the overpayment: the beneficiary keeps the
    money and the reminder stops. It is a deliberate gift, not an oversight
    -- the line stays dated, and can be undone if it was entered by
    mistake.
    """
    academy_id = default_academy_id(conn)
    overpaid = crud.overpaid_for(conn, academy_id, body.month, body.kind, body.ref_id)
    amount = body.amount_centimes if body.amount_centimes is not None else overpaid
    if amount <= 0 or amount > overpaid:
        raise HTTPException(
            status_code=422,
            detail=f"Le trop-versé de ce mois est de {overpaid / 100:.2f} DH —"
            f" impossible d'en prendre {amount / 100:.2f} DH à sa charge.",
        )
    charge_id = crud.add_overpaid_charge(
        conn, academy_id, body.kind, body.ref_id, body.month, amount, body.note
    )
    return {"id": charge_id, "amount_centimes": amount}


@router.delete("/overpaid-charges/{charge_id}")
def cancel_overpaid_charge(charge_id: int, conn: Conn) -> dict:
    """L'académie ne l'assume plus : le rappel de déduction revient."""
    crud.delete_overpaid_charge(conn, charge_id)
    return {"deleted": charge_id}


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
    _touched(conn, body.enrollment_id)
    return {"payment_id": posted.payment_id, "net_centimes": posted.net_amount}


@router.post("/payments/{payment_id}/complete")
def complete(payment_id: int, body: CompleteBody, conn: Conn) -> dict:
    """A later installment on an avance — cash in, straight back to the
    académie that fronted it."""
    posted = complete_payment(
        SqlitePaymentStore(conn), payment_id, body.amount_centimes
    )
    _touched(conn, crud.payment_enrollment(conn, payment_id))
    return {"payment_id": payment_id, "posted_centimes": posted}


@router.post("/payments/{payment_id}/reverse")
def reverse(payment_id: int, body: ReverseBody, conn: Conn) -> dict:
    reversed_payment = reverse_payment(
        SqlitePaymentStore(conn), payment_id, body.reason
    )
    _touched(conn, crud.payment_enrollment(conn, payment_id))
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


# --- filing the documents ------------------------------------------------

# The month spelled out in the folder name: « 2026-09 Septembre » sorts
# itself AND reads at a glance in the file explorer.
_MONTHS_FR = (
    "Janvier",
    "Fevrier",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Aout",
    "Septembre",
    "Octobre",
    "Novembre",
    "Decembre",
)


# Only one folder to configure: the one where the application files
# documents. Database backups are not configured -- they happen by
# themselves next to the file, and are carried onto a stick on demand
# (see /api/backups).
#
# The storage key keeps its old name: renaming it would wipe the setting
# on installations already in place.
FOLDERS = {"documents": "backup_root"}
FolderKind = Literal["documents"]


def _folder(conn: sqlite3.Connection, kind: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM app_setting WHERE key = ?", (FOLDERS[kind],)
    ).fetchone()
    return row["value"] if row else None


def _backup_root(conn: sqlite3.Connection) -> str | None:
    """Le dossier des documents — celui ou l'application les range."""
    return _folder(conn, "documents")


def _month_folder(month: str) -> str:
    """« 2026-09 Septembre » : ça se trie tout seul dans l'explorateur, et
    ça se lit sans compter sur ses doigts."""
    return f"{month} {_MONTHS_FR[int(month.split('-')[1]) - 1]}"


def _slug(text: str) -> str:
    """Un nom de fichier lisible et sans piege : pas d'accent, pas
    d'espace, rien que Windows refuserait."""
    import re
    import unicodedata

    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", plain).strip("-") or "sans-nom"


class BackupRootBody(BaseModel):
    path: str


@router.get("/settings/folders")
def folders(conn: Conn) -> dict:
    """The two folders, and for documents an example of what they will
    contain -- the interface does not guess the subfolder's name, it asks
    for it.
    """
    documents = _folder(conn, "documents")
    return {
        "documents": {
            "path": documents,
            "example": None
            if documents is None
            else str(FsPathlib(documents) / _month_folder(clock.current_month())),
        }
    }


@router.get("/settings/backup-root")
def backup_root(conn: Conn) -> dict:
    """Le dossier des documents, seul — garde l'ancienne adresse."""
    return folders(conn)["documents"]


@router.post("/settings/backup-root/browse")
def browse_for_backup_root(conn: Conn) -> dict:
    """Open the real Windows dialog to choose a folder.

    Typing a path by hand works, but nobody knows their USB stick's address
    by heart. The application and the window are the same program, so it
    can be asked to open the system picker, like any other software.

    Returns `null` if the window was closed without choosing -- cancelling
    is not an error.
    """
    chosen = _ask_for_a_folder(_backup_root(conn))
    if chosen is None:
        return {"path": None, "cancelled": True}
    return set_backup_root(BackupRootBody(path=chosen), conn)


def _ask_for_a_folder(start_at: str | None) -> str | None:
    """The system's folder picker, through whichever door answers.

    In the delivered application the window itself provides it; in
    development there is no window, so we fall back on tkinter -- the same
    Windows picker, reached another way.
    """
    try:
        import webview

        if webview.windows:
            # pywebview a renomme la constante en cours de route : on
            # prend la nouvelle si elle existe, l'ancienne sinon.
            folder = (
                getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
                or webview.FOLDER_DIALOG
            )
            picked = webview.windows[0].create_file_dialog(
                folder, directory=start_at or ""
            )
            return str(picked[0]) if picked else None
    except Exception:  # noqa: S110, BLE001 - on se rabat, on ne casse pas
        pass
    try:
        import tkinter
        from tkinter import filedialog

        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        picked = filedialog.askdirectory(initialdir=start_at or None)
        root.destroy()
        return picked or None
    except Exception as error:
        raise HTTPException(
            status_code=501,
            detail="Le sélecteur de dossier n'est pas disponible ici —"
            " tapez le chemin à la main.",
        ) from error


@router.put("/settings/backup-root")
def set_backup_root(body: BackupRootBody, conn: Conn) -> dict:
    """The folder where the application will file everything. We create it if
    it is missing -- typing a path that does not exist yet is the normal
    case.
    """
    root = FsPathlib(body.path).expanduser()
    if root.exists() and not root.is_dir():
        raise HTTPException(
            status_code=422, detail=f"« {root} » est un fichier, pas un dossier."
        )
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise HTTPException(
            status_code=422, detail=f"Dossier impossible a creer : {error}"
        ) from error
    return _remember_folder(conn, "documents", root)


def _remember_folder(conn: sqlite3.Connection, kind: str, root: FsPathlib) -> dict:
    conn.execute(
        "INSERT INTO app_setting (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (FOLDERS[kind], str(root)),
    )
    conn.commit()
    return {"path": str(root)}


def _usable_folder(path: str) -> FsPathlib:
    """A folder we can genuinely write into. We create it if it is missing --
    naming a folder that does not exist yet is the normal case.
    """
    root = FsPathlib(path).expanduser()
    if root.exists() and not root.is_dir():
        raise HTTPException(
            status_code=422, detail=f"« {root} » est un fichier, pas un dossier."
        )
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise HTTPException(
            status_code=422, detail=f"Dossier impossible a creer : {error}"
        ) from error
    return root


@router.put("/settings/folders/{kind}")
def set_folder(kind: FolderKind, body: BackupRootBody, conn: Conn) -> dict:
    """Designer l'un des deux dossiers."""
    return _remember_folder(conn, kind, _usable_folder(body.path))


@router.post("/settings/folders/{kind}/browse")
def browse_for_folder(kind: FolderKind, conn: Conn) -> dict:
    """Ouvrir la fenetre de Windows pour designer l'un des deux."""
    chosen = _ask_for_a_folder(_folder(conn, kind))
    if chosen is None:
        return {"path": None, "cancelled": True}
    return _remember_folder(conn, kind, _usable_folder(chosen))


@router.delete("/settings/folders/{kind}")
def forget_folder(kind: FolderKind, conn: Conn) -> dict:
    """Stop depositing anything there. For the database, copies return to the
    hidden folder -- they never stop existing.
    """
    conn.execute("DELETE FROM app_setting WHERE key = ?", (FOLDERS[kind],))
    conn.commit()
    return {"path": None}


# --- les repartitions nommees ---------------------------------------------


class SplitRuleBody(BaseModel):
    name: str
    venue_bp: Annotated[int, Field(ge=0, le=10_000)]
    owner_bp: Annotated[int, Field(ge=0, le=10_000)]


class AppliesToBody(BaseModel):
    scope: Literal["class", "teacher", "filiere", "level"]
    ref_id: int | None = None
    ref_text: str | None = None


@router.get("/split-rules")
def split_rules(conn: Conn) -> list[dict]:
    """Ses repartitions, et a qui chacune s applique."""
    rules = crud.rows(
        conn,
        "SELECT id, name, venue_bp, owner_bp FROM split_rule"
        " WHERE academy_id = ? ORDER BY id",
        (default_academy_id(conn),),
    )
    for rule in rules:
        rule["applies_to"] = crud.rows(
            conn,
            "SELECT scope, ref_id, ref_text FROM split_assignment"
            " WHERE rule_id = ? ORDER BY id",
            (rule["id"],),
        )
    return rules


@router.post("/split-rules", status_code=201)
def add_split_rule(body: SplitRuleBody, conn: Conn) -> dict:
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Donnez un nom a la repartition.")
    if body.venue_bp + body.owner_bp > 10_000:
        raise HTTPException(
            status_code=422,
            detail="La salle et l academie ne peuvent pas prendre plus de 100 %"
            " a elles deux -- il ne resterait rien au professeur.",
        )
    return {
        "id": crud.insert(
            conn,
            "INSERT INTO split_rule (academy_id, name, venue_bp, owner_bp)"
            " VALUES (?, ?, ?, ?)",
            (
                default_academy_id(conn),
                body.name.strip(),
                body.venue_bp,
                body.owner_bp,
            ),
        )
    }


@router.patch("/split-rules/{rule_id}")
def edit_split_rule(rule_id: int, body: SplitRuleBody, conn: Conn) -> dict:
    if body.venue_bp + body.owner_bp > 10_000:
        raise HTTPException(
            status_code=422,
            detail="La salle et l academie ne peuvent pas prendre plus de 100 %"
            " a elles deux.",
        )
    conn.execute(
        "UPDATE split_rule SET name = ?, venue_bp = ?, owner_bp = ? WHERE id = ?",
        (body.name.strip(), body.venue_bp, body.owner_bp, rule_id),
    )
    conn.commit()
    return {"id": rule_id}


@router.delete("/split-rules/{rule_id}")
def delete_split_rule(rule_id: int, conn: Conn) -> dict:
    """Classes that followed it climb back up the chain: teacher, filière,
    level, then the academy's split. Nothing is lost -- what is already
    collected keeps its division.
    """
    conn.execute("DELETE FROM split_assignment WHERE rule_id = ?", (rule_id,))
    conn.execute("DELETE FROM split_rule WHERE id = ?", (rule_id,))
    conn.commit()
    return {"deleted": rule_id}


@router.post("/split-rules/{rule_id}/applies-to")
def rule_applies_to(rule_id: int, body: AppliesToBody, conn: Conn) -> dict:
    """State who this split applies to.

    One target follows one rule only: setting it again replaces the
    previous one, otherwise you would have to guess which wins.
    """
    if body.scope == "filiere":
        if not body.ref_text:
            raise HTTPException(status_code=422, detail="Quelle filiere ?")
        conn.execute(
            "DELETE FROM split_assignment WHERE scope = 'filiere' AND ref_text = ?",
            (body.ref_text,),
        )
        conn.execute(
            "INSERT INTO split_assignment (rule_id, scope, ref_text)"
            " VALUES (?, 'filiere', ?)",
            (rule_id, body.ref_text),
        )
    else:
        if body.ref_id is None:
            raise HTTPException(status_code=422, detail="Sur quoi l appliquer ?")
        conn.execute(
            "DELETE FROM split_assignment WHERE scope = ? AND ref_id = ?",
            (body.scope, body.ref_id),
        )
        conn.execute(
            "INSERT INTO split_assignment (rule_id, scope, ref_id) VALUES (?, ?, ?)",
            (rule_id, body.scope, body.ref_id),
        )
    conn.commit()
    return {"rule_id": rule_id, "scope": body.scope}


@router.delete("/split-rules/applies-to/{scope}/{ref}")
def rule_no_longer_applies(scope: str, ref: str, conn: Conn) -> dict:
    """Retirer une regle d une cible : elle remonte la chaine."""
    column = "ref_text" if scope == "filiere" else "ref_id"
    conn.execute(
        f"DELETE FROM split_assignment WHERE scope = ? AND {column} = ?",
        (scope, ref),
    )
    conn.commit()
    return {"scope": scope, "ref": ref}


@router.get("/split-preview")
def split_preview(
    conn: Conn,
    teacher_id: Annotated[int | None, Query()] = None,
    level_id: Annotated[int | None, Query()] = None,
    filiere: Annotated[str | None, Query()] = None,
) -> dict:
    """What will apply to a class currently being created.

    The form thus shows the consequence at the moment one thinks about it,
    without having to ask -- and without restating the precedence order in
    the interface, where it would eventually drift.
    """
    from app.services.splits import resolve

    found = resolve(
        conn,
        default_academy_id(conn),
        teacher_id=teacher_id,
        level_id=level_id,
        filiere=filiere,
    )
    return {
        "venue_bp": found.venue_bp,
        "owner_bp": found.owner_bp,
        "from": found.origin,
        "rule_name": found.rule_name,
    }


@router.get("/classes/{class_id}/split")
def class_split(class_id: int, conn: Conn) -> dict:
    """Which split this class follows, and where it gets it from -- because
    « pourquoi ce chiffre ? » deserves an answer.
    """
    from app.services.splits import split_for_class

    found = split_for_class(conn, class_id, default_academy_id(conn))
    return {
        "venue_bp": found.venue_bp,
        "owner_bp": found.owner_bp,
        "from": found.origin,
        "rule_name": found.rule_name,
    }


# --- telling the family ----------------------------------------------------
#
# The application PREPARES the message and opens WhatsApp on it. It sends
# nothing by itself: the owner rereads it and presses send. Software that
# writes to families without the text having been seen is software people
# distrust -- and a wrong amount sent on its own cannot be taken back.


class WhatsAppBody(BaseModel):
    phone: str
    text: str


def _open_outside(url: str) -> None:
    """Open OUTSIDE the window: WhatsApp Desktop if installed, the browser
    otherwise. Never inside the application's own window, which would turn
    it into a browser with no back button.

    os.startfile first: it is what Windows does when a link is clicked, and
    it is the only path that can be relied on in an application with no
    console -- webbrowser sometimes looks there for a command-line browser
    that does not exist.
    """
    import os
    import webbrowser

    opener = getattr(os, "startfile", None)
    if opener is not None:
        opener(url)
        return
    webbrowser.open(url)


@router.post("/whatsapp")
def open_whatsapp(body: WhatsAppBody) -> dict:
    """Ouvrir WhatsApp sur ce numero, message deja ecrit."""
    from urllib.parse import quote

    number = whatsapp_number(body.phone)
    if number is None:
        raise HTTPException(
            status_code=422,
            detail=f"« {body.phone} » n'est pas un numero utilisable —"
            " corrigez-le dans la fiche de l'eleve.",
        )
    url = f"https://wa.me/{number}?text={quote(body.text)}"
    _open_outside(url)
    return {"url": url}


# Quand un modele a un sens. « Vous n avez pas paye » propose a une
# famille qui vient de regler, et l application se fait desinstaller.
ShownWhen = Literal["always", "paid", "unpaid", "arrears"]


class TemplateBody(BaseModel):
    label: str
    body: str
    shown_when: ShownWhen = "always"


class TemplatePatch(BaseModel):
    label: str | None = None
    body: str | None = None
    shown_when: ShownWhen | None = None


def _clean_template(label: str | None, body: str | None) -> None:
    """An empty template has no business in the list: it would take up a slot
    and say nothing.
    """
    if label is not None and not label.strip():
        raise HTTPException(status_code=422, detail="Donnez un nom au modèle.")
    if body is not None and not body.strip():
        raise HTTPException(status_code=422, detail="Le message est vide.")


@router.get("/message-templates")
def message_templates(conn: Conn) -> list[dict]:
    """His own templates, in the order he gave them."""
    return crud.rows(
        conn,
        "SELECT id, label, body, shown_when, position FROM message_template"
        " ORDER BY position, id",
    )


@router.post("/message-templates", status_code=201)
def add_message_template(body: TemplateBody, conn: Conn) -> dict:
    _clean_template(body.label, body.body)
    position = conn.execute(
        "SELECT COALESCE(MAX(position), 0) + 1 FROM message_template"
    ).fetchone()[0]
    template_id = crud.insert(
        conn,
        "INSERT INTO message_template (label, body, shown_when, position)"
        " VALUES (?, ?, ?, ?)",
        (body.label.strip(), body.body.strip(), body.shown_when, position),
    )
    return {"id": template_id}


@router.patch("/message-templates/{template_id}")
def edit_message_template(template_id: int, body: TemplatePatch, conn: Conn) -> dict:
    _clean_template(body.label, body.body)
    for column, value in (
        ("label", body.label),
        ("body", body.body),
        ("shown_when", body.shown_when),
    ):
        if value is not None:
            conn.execute(
                f"UPDATE message_template SET {column} = ? WHERE id = ?",
                (value.strip(), template_id),
            )
    conn.commit()
    return {"id": template_id}


@router.delete("/message-templates/{template_id}")
def delete_message_template(template_id: int, conn: Conn) -> dict:
    conn.execute("DELETE FROM message_template WHERE id = ?", (template_id,))
    conn.commit()
    return {"deleted": template_id}


@router.get("/students/{student_id}/messages")
def student_messages(student_id: int, month: MonthQuery, conn: Conn) -> dict:
    """Ce qu'on peut annoncer a cette famille ce mois-ci, et a quel
    numero. Rien d inscrit, rien a dire."""
    student = conn.execute(
        "SELECT id, name FROM student WHERE id = ?", (student_id,)
    ).fetchone()
    if student is None:
        raise LookupError(f"no student {student_id}")
    academy = conn.execute("SELECT name FROM academy ORDER BY id LIMIT 1").fetchone()
    row = next(
        (
            entry
            for entry in crud.month_overview(conn, default_academy_id(conn), month)
            if entry["student_id"] == student_id
        ),
        None,
    )
    return {
        "student_name": student["name"],
        "phones": [
            {
                "tag": phone["tag"],
                "number": phone["number"],
                # None: the number is unusable as written. We show it
                # anyway, so he knows which one to correct.
                "whatsapp": whatsapp_number(phone["number"]),
            }
            for phone in _rows_of(conn, student_id)
        ],
        "messages": _messages_for(conn, row, student["name"], academy["name"], month),
    }


def _rows_of(conn: sqlite3.Connection, student_id: int) -> list[dict]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT tag, number FROM student_phone WHERE student_id = ? ORDER BY id",
            (student_id,),
        )
    ]


def _messages_for(
    conn, row: dict | None, name: str, academy: str, month: str
) -> list[dict]:
    """The messages that make sense this month -- never more.

    They all come from the same list, including the ones placed at
    installation: the owner can rework them to his taste, translate them or
    throw them away. Each says when it serves, and none is offered that
    would land wrong.
    """
    from app.adapters.docx.labels import month_label

    enrollment = (row or {}).get("enrollment")
    if not enrollment:
        return []
    left = enrollment["remaining_centimes"]
    settled = bool(enrollment["paid"]) and left == 0
    debt = _whole_debt(conn, row["student_id"], month)
    filling = {
        "eleve": name,
        "mois": month_label(month).lower(),
        "montant": _dh(
            enrollment["net_centimes"]
            if settled
            else (left or enrollment["net_centimes"])
        ),
        "classes": ", ".join(entry["subject_name"] for entry in enrollment["classes"]),
        "academie": academy,
        "impayes": _dh(debt["total"]),
        "mois_impayes": ", ".join(debt["months"]),
    }
    return _templates(conn, settled, filling, behind=len(debt["months"]) > 1)


def _whole_debt(conn: sqlite3.Connection, student_id: int, month: str) -> dict:
    """Everything this family owes, all months together.

    The ordinary reminder speaks of one month; this one speaks of the debt.
    Claiming 300 DH from someone who owes 900 loses the other 600.
    """
    from app.adapters.docx.labels import month_label
    from app.adapters.sqlite.reports import arrears

    owed = arrears(conn, default_academy_id(conn), month)
    mine = next((entry for entry in owed if entry.student_id == student_id), None)
    if mine is None:
        return {"total": 0, "months": []}
    return {
        "total": mine.total_owed,
        "months": [month_label(item.month).lower() for item in mine.items],
    }


def _templates(conn, settled: bool, filling: dict, behind: bool = False) -> list[dict]:
    """The templates that suit this month, with the markers filled in.

    An unknown marker stays visible as it is: better he sees « {truc} » in
    the preview than be left believing we understood what he meant.
    """
    # « arrears » ne sort que s il y a VRAIMENT plusieurs mois en
    # retard : pour un seul, le rappel du mois suffit, et deux
    # messages sur la meme dette se contrediraient.
    allowed = ("always", "paid" if settled else "unpaid") + (
        ("arrears",) if behind else ()
    )
    offers = []
    for template in crud.rows(
        conn,
        "SELECT id, label, body, shown_when FROM message_template"
        " ORDER BY position, id",
    ):
        if template["shown_when"] not in allowed:
            continue
        text = template["body"]
        for marker, value in filling.items():
            text = text.replace("{" + marker + "}", value)
        offers.append(
            {
                "kind": f"template-{template['id']}",
                "label": template["label"],
                "text": text,
            }
        )
    return offers


def _dh(centimes: int) -> str:
    return f"{centimes / 100:,.2f} DH".replace(",", " ").replace(".", ",")


# --- carrying the backups away ---------------------------------------------

# Beyond this, we remind him. A permanent warning ends up becoming part
# of the furniture. This one waits until thirty backups have never left
# the computer -- and since a snapshot is only taken when the database
# moved, thirty means
# trente vraies journees de travail. A ce compte-la, il y a de quoi
# perdre.
_REMIND_AFTER = 30

# On the stick, everything goes into a folder of our own: a stick serves
# twenty purposes, and ours must not get lost among them.
_ON_THE_STICK = "AcademyManagement"


class CopyBackupsBody(BaseModel):
    # Absent : on ouvre le selecteur de dossiers.
    path: str | None = None


def _backups_folder(request: Request) -> FsPathlib:
    """Copies live next to the database, where closing the app puts them."""
    return FsPathlib(request.app.state.db_path).parent / "backups"


def _snapshots(request: Request) -> list[FsPathlib]:
    folder = _backups_folder(request)
    return sorted(folder.glob("data-*.db")) if folder.is_dir() else []


@router.get("/backups")
def backups_state(request: Request, conn: Conn) -> dict:
    """Ou en sont les sauvegardes, et depuis quand elles n'ont pas quitte
    cet ordinateur."""
    from datetime import datetime

    copies = _snapshots(request)
    last = _setting_value(conn, "backups_copied_at")
    days = None
    if last:
        try:
            days = (datetime.now(UTC) - datetime.fromisoformat(last)).days
        except ValueError:
            days = None
    uncopied = _uncopied(conn, request, copies)
    return {
        "count": len(copies),
        "newest": copies[-1].name if copies else None,
        "destination": _setting_value(conn, "backups_destination"),
        "last_copied_at": last,
        "days_since": days,
        "uncopied": uncopied,
        "remind_after": _REMIND_AFTER,
        "stale": uncopied >= _REMIND_AFTER,
    }


def _uncopied(conn: sqlite3.Connection, request: Request, copies: list) -> int:
    """How many backups have never left this computer.

    We count what is missing at the destination rather than days elapsed:
    fifteen days of holiday endanger nothing, fifteen unsaved working days
    do.
    """
    destination = _setting_value(conn, "backups_destination")
    if destination is None:
        return len(copies)
    there = FsPathlib(destination) / _ON_THE_STICK
    if not there.is_dir():
        # The stick is not plugged in: we do not know, so we do not shout.
        return len(copies) - int(_setting_value(conn, "backups_copied_count") or 0)
    saved = {item.name for item in there.glob("data-*.db")}
    return sum(1 for item in copies if item.name not in saved)


@router.post("/backups/copy")
def copy_backups(body: CopyBackupsBody, request: Request, conn: Conn) -> dict:
    """Carry the backups onto a stick, or any other disk.

    Automatic copying to a stick does not work: nobody leaves one plugged
    in, and a safety net that fails silently is worse than none. He plugs it
    in when he thinks of it, he clicks, everything goes.
    """
    import shutil
    from datetime import datetime

    chosen = body.path or _ask_for_a_folder(_setting_value(conn, "backups_destination"))
    if chosen is None:
        return {"copied": 0, "cancelled": True}
    destination = _usable_folder(chosen) / _ON_THE_STICK
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    for snapshot in _snapshots(request):
        target = destination / snapshot.name
        # Already there: we do not copy the same file ten times.
        if target.exists() and target.stat().st_size == snapshot.stat().st_size:
            continue
        shutil.copy2(snapshot, target)
        copied += 1
    _remember(conn, "backups_destination", chosen)
    # What is safe, so we can still count once the stick is unplugged.
    _remember(conn, "backups_copied_count", str(len(_snapshots(request))))
    _remember(
        conn, "backups_copied_at", datetime.now(UTC).isoformat(timespec="seconds")
    )
    return {"copied": copied, "destination": str(destination)}


def _setting_value(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM app_setting WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _remember(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_setting (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


class FileDocumentBody(BaseModel):
    kind: Literal["payslip", "absence", "excel"]
    month: Month
    ref_id: int = 0
    # A payslip produced at the moment of paying becomes a receipt.
    payout_id: int | None = None


@router.post("/documents/file", status_code=201)
def file_document(body: FileDocumentBody, conn: Conn) -> dict:
    """File the document in the owner's folder, in its place.

    One folder per month, one drawer per kind: the filing he would do by
    hand, done for him -- and a stable name, so that regenerating replaces
    instead of piling up « (2) » copies.
    """
    root = _backup_root(conn)
    if root is None:
        raise HTTPException(
            status_code=409,
            detail="Choisissez d'abord un dossier de sauvegarde dans la page Academie.",
        )
    # A receipt is not regenerated. It was produced at the moment of paying
    # and signed; asking for it again must return THAT paper, not a fresh
    # one describing a month that has moved on since -- another student may
    # have enrolled, and the professor was never handed money for him.
    if body.payout_id is not None:
        already = documents.receipt_path(conn, body.payout_id)
        if already is not None and FsPathlib(already).exists():
            return {"path": already, "reused": True}

    drawer = FsPathlib(root) / _month_folder(body.month) / documents.DRAWERS[body.kind]
    drawer.mkdir(parents=True, exist_ok=True)
    content, name = _render_document(
        conn, body.kind, body.month, body.ref_id, body.payout_id
    )
    target = drawer / name
    target.write_bytes(content)
    documents.record_export(
        conn, body.kind, body.month, body.ref_id, str(target), body.payout_id
    )
    return {"path": str(target)}


def _payout_rank(
    conn: sqlite3.Connection, teacher_id: int, month: str, payout_id: int
) -> int:
    """Which receipt this is for him THIS MONTH: his first reads 01.

    Counting since the beginning made the number climb forever -- by March
    a teacher paid twice a month is on his fourteenth, and the figure says
    nothing he can check against the month in his hand. It restarts with
    the month, so 02 always means the second of that month.

    Counted by creation order, so cancelling a later one never renumbers a
    receipt already signed.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS rank FROM payout"
        " WHERE beneficiary_kind = 'teacher' AND beneficiary_id = ?"
        " AND month = ? AND id <= ?",
        (teacher_id, month, payout_id),
    ).fetchone()
    return row["rank"] or 1


def _render_document(
    conn: sqlite3.Connection,
    kind: str,
    month: str,
    ref_id: int,
    payout_id: int | None = None,
) -> tuple[bytes, str]:
    if kind == "payslip":
        from app.adapters.docx.teacher_invoice import teacher_invoice

        row = conn.execute(
            "SELECT name FROM teacher WHERE id = ?", (ref_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Professeur inconnu.")
        # A receipt carries the payout number: two payouts in one month
        # make two sheets, and the second does not overwrite the first.
        #
        # The number counts HIS payouts, not the database's. « versement-16 »
        # told the owner how many payouts the academy had ever made, which is
        # not a fact about the man holding the paper -- and it made his fourth
        # receipt look like his sixteenth.
        name = f"paie-{_slug(row['name'])}"
        if payout_id:
            name += f"-versement-{_payout_rank(conn, ref_id, month, payout_id):02d}"
        return teacher_invoice(conn, ref_id, month, payout_id), f"{name}.docx"
    if kind == "absence":
        from app.adapters.docx.absence_sheet import absence_sheet

        row = conn.execute(
            "SELECT s.name AS subject FROM class_group c"
            " JOIN subject s ON s.id = c.subject_id WHERE c.id = ?",
            (ref_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Classe inconnue.")
        return absence_sheet(conn, ref_id, month), f"{_slug(row['subject'])}.docx"
    from app.adapters.excel.monthly_workbook import monthly_workbook

    return monthly_workbook(conn, default_academy_id(conn), month), "paiements.xlsx"


@router.post("/documents/reconcile")
def reconcile_documents(conn: Conn) -> dict:
    """File what is missing, redo what has aged -- without a click.

    A closed month's export and its absence sheet are not a choice: they
    must exist. Asking for a click on a document the application knows how
    to produce is asking the client to remember on our behalf -- and he will
    forget.

    The RUNNING month sees nothing BORN here: its export would change every
    day, and his folder would fill with files he never asked for. But what
    he asked for once, we keep current -- including during the running
    month. Otherwise the banner would spend all of August demanding an
    action the application had forbidden itself to take, and nothing would
    ever clear it.

    The payslip is never produced here either: it is a receipt, made at the
    moment of paying.

    Nothing here may fail the call that triggered it: if the folder has
    vanished, we stay quiet and try again later.
    """
    if _backup_root(conn) is None:
        return {"filed": 0}
    academy_id = default_academy_id(conn)
    running = clock.current_month()
    filed = 0
    for month in _months_with_something(conn):
        wanted: list[tuple[str, int]] = [("excel", 0)]
        wanted += [
            ("absence", row["id"]) for row in _classes_of_month(conn, academy_id, month)
        ]
        for kind, ref_id in wanted:
            if _already_fresh(conn, kind, month, ref_id):
                continue
            if month >= running and not _was_filed(conn, kind, month, ref_id):
                continue
            try:
                file_document(
                    FileDocumentBody(kind=kind, month=month, ref_id=ref_id), conn
                )
                filed += 1
            except (HTTPException, LookupError, OSError):
                continue
    return {"filed": filed}


def _months_with_something(conn: sqlite3.Connection) -> list[str]:
    return [
        row["month"]
        for row in crud.rows(
            conn, "SELECT DISTINCT month FROM enrollment ORDER BY month"
        )
    ]


def _classes_of_month(
    conn: sqlite3.Connection, academy_id: int, month: str
) -> list[dict]:
    """Classes that had at least one enrolled student that month: the others
    have no absence sheet to produce.
    """
    return crud.rows(
        conn,
        "SELECT DISTINCT c.id FROM class_group c"
        " JOIN enrollment_class ec ON ec.class_id = c.id"
        " JOIN enrollment e ON e.id = ec.enrollment_id"
        " WHERE e.month = ? ORDER BY c.id",
        (month,),
    )


def _was_filed(conn: sqlite3.Connection, kind: str, month: str, ref_id: int) -> bool:
    """This document has been filed once already -- so he wanted it.

    That is what separates keeping current from creating unasked.
    """
    return (
        conn.execute(
            "SELECT 1 FROM exported_document WHERE kind = ? AND month = ?"
            " AND ref_id = ?",
            (kind, month, ref_id),
        ).fetchone()
        is not None
    )


def _already_fresh(
    conn: sqlite3.Connection, kind: str, month: str, ref_id: int
) -> bool:
    """Deja range, et rien n'a bouge depuis. Reecrire pour rien userait
    la cle USB et brouillerait les dates."""
    row = conn.execute(
        "SELECT d.generated_at, ("
        "  SELECT t.touched_at FROM document_touch t"
        "  WHERE t.month = d.month AND t.scope = d.scope AND t.ref_id = d.ref_id"
        ") AS touched_at FROM exported_document d"
        " WHERE d.kind = ? AND d.month = ? AND d.ref_id = ?",
        (kind, month, ref_id),
    ).fetchone()
    if row is None:
        return False
    return row["touched_at"] is None or row["touched_at"] <= row["generated_at"]


@router.get("/documents/stale")
def stale_documents_route(
    conn: Conn, month: Annotated[str | None, Query(pattern=MONTH_PATTERN)] = None
) -> list[dict]:
    """What was produced before the figures moved -- and for whom, by name, so
    one knows which file to fetch again.
    """
    return [vars(item) for item in documents.stale_documents(conn, month)]


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


# --- School years -----------------------------------------------------
#
# An academy lives in school years, not in months. The month a season
# stops is not guessable: here it closes in June, elsewhere in July.


class SchoolYearBody(BaseModel):
    name: str
    start_month: Annotated[str, Field(pattern=MONTH_PATTERN)]
    end_month: Annotated[str, Field(pattern=MONTH_PATTERN)]


class SchoolYearPatch(BaseModel):
    name: str | None = None
    start_month: Annotated[str | None, Field(pattern=MONTH_PATTERN)] = None
    end_month: Annotated[str | None, Field(pattern=MONTH_PATTERN)] = None


@router.get("/school-years")
def school_years(conn: Conn) -> list[dict]:
    from app.services.school_years import list_years

    return list_years(conn, default_academy_id(conn))


@router.post("/school-years", status_code=201)
def create_school_year(body: SchoolYearBody, conn: Conn) -> dict:
    from app.services.school_years import create_year

    return create_year(
        conn,
        default_academy_id(conn),
        name=body.name,
        start_month=body.start_month,
        end_month=body.end_month,
    )


@router.patch("/school-years/{year_id}")
def patch_school_year(year_id: int, patch: SchoolYearPatch, conn: Conn) -> dict:
    from app.services.school_years import update_year

    return update_year(conn, year_id, **patch.model_dump(exclude_none=True))


@router.delete("/school-years/{year_id}")
def delete_school_year(year_id: int, conn: Conn) -> dict:
    from app.services.school_years import delete_year

    delete_year(conn, year_id)
    return {"deleted": year_id}


@router.post("/school-years/{year_id}/close")
def close_school_year(year_id: int, conn: Conn) -> dict:
    """Put the season away and archive the students.

    We do not presume they will return: whoever comes back is re-enrolled as
    usual and finds his history. What a family owes, by contrast, follows it
    -- money due does not disappear because the calendar turned.
    """
    from app.services.school_years import close_year

    return close_year(conn, year_id)


@router.get("/reports/school-year/{year_id}")
def report_school_year(year_id: int, conn: Conn) -> dict:
    from app.services.school_years import season_report

    return season_report(conn, year_id)


# --- The academy's logo -----------------------------------------------
#
# « Academy Management » at the top of the sidebar is the name of the
# TOOL. He opens the application to see HIS academy -- and when a parent
# looks over his shoulder, it is his own sign that should be there.
#
# It lives in the database, not in a folder: that way it travels with the
# backups. A file dropped on the desktop and later deleted would leave an
# empty square at the next launch.

# Enough for a handsome sign, too little for a holiday photograph: the
# logo goes into EVERY backup, and would weigh them all down.
_LOGO_MAX = 2 * 1024 * 1024
_LOGO_PREFIX = "data:image/"


class LogoBody(BaseModel):
    logo: str | None = None


@router.get("/settings/logo")
def academy_logo(conn: Conn) -> dict:
    return {"logo": _setting_value(conn, "logo")}


@router.put("/settings/logo")
def set_academy_logo(body: LogoBody, conn: Conn) -> dict:
    """Set his sign, or take it down (logo: null).

    We check it really is an image: any other file dropped here would show
    as a broken square, and he would spend a long time wondering why.
    """
    if body.logo is not None:
        if not body.logo.startswith(_LOGO_PREFIX):
            raise ValueError(
                "Ce fichier n'est pas une image. Choisissez un PNG ou un JPEG."
            )
        if len(body.logo) > _LOGO_MAX:
            raise ValueError(
                "Cette image est trop lourde. Elle entrerait dans chacune de"
                " vos sauvegardes -- prenez-en une plus legere."
            )
    if body.logo is None:
        conn.execute("DELETE FROM app_setting WHERE key = 'logo'")
        conn.commit()
    else:
        _remember(conn, "logo", body.logo)
    return {"logo": body.logo}
