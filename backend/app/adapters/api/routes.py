"""All /api routes. Thin handlers: parse, delegate to crud/services, serialize."""

import sqlite3
from collections.abc import Iterator
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
from app.domain.splitting import Beneficiary
from app.ports.payments import ConfiguredAdjustment, UnknownEnrollmentError
from app.services import clock, documents
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
    """Deviner un code court est l'affaire d'une minute si l'on peut
    essayer sans fin. La phrase de secours ouvre autant que le code :
    les deux portes attendent donc pareil."""
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
    """Poser le code, une fois. La phrase de secours est rendue ICI et
    nulle part ailleurs : c'est la seule fois où elle sera lisible."""
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
    # Le cookie ne sert qu'aux téléchargements, qui ne peuvent pas porter
    # d'en-tête. Il meurt avec la fenêtre, comme la session elle-même.
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
    """La phrase notée sur papier repose un code — la seule porte de
    sortie d'une application sans réseau."""
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
    """Ce qui distingue CETTE installation. Tiré une fois, gardé pour
    toujours : c'est lui qui fait qu'un dépannage ne vaut que pour une
    académie."""
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
    """Le défi à lire à l'éditeur. Sans clé dans cette version, il n'y a
    rien à montrer et le bouton ne s'affiche pas."""
    if vendor.vendor_key() is None:
        return {"available": False}
    return {
        "available": True,
        "challenge": vendor.challenge_for(_installation_id(conn)),
    }


@router.post("/lock/rescue")
def rescue(body: RescueBody, request: Request, conn: Conn) -> dict:
    """Le dernier recours : le code ET la phrase sont perdus.

    L'éditeur dicte la réponse au défi du jour ; l'académie repart avec
    un code neuf ET une phrase de secours neuve — dépanner ne doit pas
    le priver de sa propre porte."""
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


@router.get("/classes/{class_id}/profile")
def class_profile(class_id: int, conn: Conn, month: MonthQuery | None = None) -> dict:
    """La fiche d'une classe : son créneau, son professeur, la succession
    de ceux qui l'ont enseignée, et ses inscrits du mois."""
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
    """La répartition entre professeurs pour ce mois : automatique (au
    prorata des jours enseignés) ou fixée par le propriétaire."""
    share = crud.class_share(conn, class_id, month or clock.current_month())
    if share is None:
        raise LookupError(f"no class_group {class_id}")
    return share


@router.put("/classes/{class_id}/share")
def set_class_share(class_id: int, body: ShareBody, conn: Conn) -> dict:
    """Le propriétaire tranche lui-même. En pourcentages : un montant figé
    deviendrait faux dès qu'un élève s'inscrit ou qu'une réduction tombe.
    Les mois déjà encaissés ne bougent pas — le registre ne se réécrit
    jamais ; cela vaut pour les encaissements à venir."""
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
def teacher_invoice_route(teacher_id: int, month: MonthQuery, conn: Conn) -> Response:
    """La fiche de paie du mois, imprimable et signable des deux côtés."""
    import unicodedata

    from app.adapters.docx.teacher_invoice import teacher_invoice

    content = teacher_invoice(conn, teacher_id, month)
    row = conn.execute(
        "SELECT name FROM teacher WHERE id = ?", (teacher_id,)
    ).fetchone()
    # Le nom dans le fichier : dix fiches dans un dossier, on doit savoir
    # laquelle est laquelle sans les ouvrir.
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
    """Dire ce que ce geste vient de perimer, nommement.

    Une seule ligne a chaque ecriture : c'est l'ecriture elle-meme qui
    sait qui elle touche, et c'est ce qui permet de signaler JUSTE plutot
    que de crier « ce mois a change » sur tous les documents."""
    month = crud.enrollment_month(conn, enrollment_id)
    if month is None:
        return
    documents.touch(conn, month, documents.scopes_of_enrollment(conn, enrollment_id))
    conn.commit()


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
    """Sortir de la caisse la part d'un bénéficiaire — professeur, salle ou
    le propriétaire lui-même : il se paie comme il paie les autres."""
    return _record_payout(conn, body.kind, body.ref_id, body)


@router.delete("/payouts/{payout_id}")
def delete_payout(payout_id: int, conn: Conn) -> dict:
    """Correction d'une saisie — le versement n'a jamais eu lieu."""
    crud.delete_payout(conn, payout_id)
    return {"deleted": payout_id}


class OverpaidChargeBody(BaseModel):
    kind: Literal["teacher", "venue", "owner"]
    ref_id: int
    month: Month
    amount_centimes: int | None = None  # None = tout le trop-versé
    note: str | None = None


@router.post("/overpaid-charges", status_code=201)
def take_overpaid_charge(body: OverpaidChargeBody, conn: Conn) -> dict:
    """L'académie prend le trop-versé à sa charge : le bénéficiaire garde
    l'argent et le rappel s'éteint. C'est un cadeau assumé, pas un oubli —
    la ligne reste datée, et s'annule si elle a été saisie par erreur."""
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


# --- le classement des documents -----------------------------------------

# Le mois en toutes lettres dans le nom du dossier : « 2026-09 Septembre »
# se trie tout seul ET se lit d'un coup d'oeil dans l'explorateur.
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


# Deux dossiers, et surtout PAS le meme.
#
# Les documents se donnent : une fiche de paie s'imprime et se tend au
# professeur, une feuille d'absence circule. La base, elle, contient
# toute l'academie -- chaque eleve, chaque paiement. Les melanger ferait
# voyager le tout des qu'il tend sa cle USB a quelqu'un.
#
# Les cles de stockage gardent leurs anciens noms : les renommer
# effacerait le reglage des installations deja posees.
FOLDERS = {"documents": "backup_root", "database": "db_backup_root"}
FolderKind = Literal["documents", "database"]


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
    """Les deux dossiers, et pour les documents un exemple de ce qu'ils
    contiendront — l'interface ne devine pas le nom du sous-dossier,
    elle le demande."""
    documents = _folder(conn, "documents")
    return {
        "documents": {
            "path": documents,
            "example": None
            if documents is None
            else str(FsPathlib(documents) / _month_folder(clock.current_month())),
        },
        "database": {"path": _folder(conn, "database")},
    }


@router.get("/settings/backup-root")
def backup_root(conn: Conn) -> dict:
    """Le dossier des documents, seul — garde l'ancienne adresse."""
    return folders(conn)["documents"]


@router.post("/settings/backup-root/browse")
def browse_for_backup_root(conn: Conn) -> dict:
    """Ouvrir la vraie fenêtre de Windows pour choisir un dossier.

    Taper un chemin à la main marche, mais personne ne connaît par cœur
    l'adresse de sa clé USB. L'application et la fenêtre sont le même
    programme : on peut donc lui demander d'ouvrir le sélecteur du
    système, comme n'importe quel logiciel.

    Renvoie `null` si la fenêtre a été fermée sans choisir — annuler
    n'est pas une erreur.
    """
    chosen = _ask_for_a_folder(_backup_root(conn))
    if chosen is None:
        return {"path": None, "cancelled": True}
    return set_backup_root(BackupRootBody(path=chosen), conn)


def _ask_for_a_folder(start_at: str | None) -> str | None:
    """Le sélecteur de dossier du système, par la porte qui répond.

    Dans l'application livrée c'est la fenêtre elle-même qui le fournit ;
    en développement il n'y a pas de fenêtre, alors on se rabat sur
    tkinter — même sélecteur Windows, autre chemin pour y arriver.
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
    """Le dossier ou l'application rangera tout. On le cree s'il manque —
    taper un chemin qui n'existe pas encore est le cas normal."""
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
    """Un dossier ou l'on pourra vraiment ecrire. On le cree s'il manque —
    designer un dossier qui n'existe pas encore est le cas normal."""
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
    """Ne plus rien y deposer. Pour la base, les copies retournent dans
    le dossier cache -- elles ne cessent jamais d'exister."""
    conn.execute("DELETE FROM app_setting WHERE key = ?", (FOLDERS[kind],))
    conn.commit()
    return {"path": None}


class FileDocumentBody(BaseModel):
    kind: Literal["payslip", "absence", "excel"]
    month: Month
    ref_id: int = 0


@router.post("/documents/file", status_code=201)
def file_document(body: FileDocumentBody, conn: Conn) -> dict:
    """Ranger le document dans le dossier du proprietaire, a sa place.

    Un dossier par mois, un tiroir par sorte : le classement qu'il ferait
    a la main, fait pour lui — et un nom stable, pour que regenerer
    remplace au lieu d'empiler des « (2) »."""
    root = _backup_root(conn)
    if root is None:
        raise HTTPException(
            status_code=409,
            detail="Choisissez d'abord un dossier de sauvegarde dans la page Academie.",
        )
    drawer = FsPathlib(root) / _month_folder(body.month) / documents.DRAWERS[body.kind]
    drawer.mkdir(parents=True, exist_ok=True)
    content, name = _render_document(conn, body.kind, body.month, body.ref_id)
    target = drawer / name
    target.write_bytes(content)
    documents.record_export(conn, body.kind, body.month, body.ref_id, str(target))
    return {"path": str(target)}


def _render_document(
    conn: sqlite3.Connection, kind: str, month: str, ref_id: int
) -> tuple[bytes, str]:
    if kind == "payslip":
        from app.adapters.docx.teacher_invoice import teacher_invoice

        row = conn.execute(
            "SELECT name FROM teacher WHERE id = ?", (ref_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Professeur inconnu.")
        return teacher_invoice(conn, ref_id, month), f"paie-{_slug(row['name'])}.docx"
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


@router.get("/documents/stale")
def stale_documents_route(
    conn: Conn, month: Annotated[str | None, Query(pattern=MONTH_PATTERN)] = None
) -> list[dict]:
    """Ce qui a ete sorti avant que les chiffres ne bougent — et pour qui,
    nommement, pour qu'on sache quel fichier retelecharger."""
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
