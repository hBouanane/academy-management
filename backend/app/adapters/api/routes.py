"""All /api routes. Thin handlers: parse, delegate to crud/services, serialize."""

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.adapters.sqlite import crud
from app.adapters.sqlite.db import connect
from app.adapters.sqlite.payment_store import SqlitePaymentStore
from app.adapters.sqlite.reports import arrears, monthly_report
from app.services.payments import post_payment, reverse_payment

router = APIRouter()


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


# --- structure -----------------------------------------------------------


class AcademyPatch(BaseModel):
    name: str | None = None
    venue_bp: int | None = None
    owner_bp: int | None = None


@router.get("/academies")
def academies(conn: Conn) -> list[dict]:
    return crud.list_academies(conn)


@router.patch("/academies/{academy_id}")
def patch_academy(academy_id: int, patch: AcademyPatch, conn: Conn) -> dict:
    crud.update_academy(conn, academy_id, patch.model_dump(exclude_none=True))
    return next(a for a in crud.list_academies(conn) if a["id"] == academy_id)


@router.get("/levels")
def levels(conn: Conn) -> list[dict]:
    return crud.list_levels(conn, default_academy_id(conn))


class NamedCreate(BaseModel):
    name: str
    phone: str | None = None


@router.get("/subjects")
def subjects(conn: Conn) -> list[dict]:
    return crud.list_subjects(conn, default_academy_id(conn))


@router.post("/subjects", status_code=201)
def create_subject(body: NamedCreate, conn: Conn) -> dict:
    return {"id": crud.create_subject(conn, default_academy_id(conn), body.name)}


@router.get("/teachers")
def teachers(conn: Conn) -> list[dict]:
    return crud.list_teachers(conn, default_academy_id(conn))


@router.post("/teachers", status_code=201)
def create_teacher(body: NamedCreate, conn: Conn) -> dict:
    academy_id = default_academy_id(conn)
    return {"id": crud.create_teacher(conn, academy_id, body.name, body.phone)}


class ClassCreate(BaseModel):
    level_id: int
    subject_id: int
    teacher_id: int
    name: str = "A"
    day_of_week: int | None = None
    start_time: str | None = None


@router.get("/classes")
def classes(conn: Conn) -> list[dict]:
    return crud.list_classes(conn, default_academy_id(conn))


@router.post("/classes", status_code=201)
def create_class(body: ClassCreate, conn: Conn) -> dict:
    academy_id = default_academy_id(conn)
    return {"id": crud.create_class(conn, academy_id, body.model_dump())}


class PackageCreate(BaseModel):
    subject_count: int
    monthly_price_centimes: int


@router.get("/packages")
def packages(conn: Conn) -> list[dict]:
    return crud.list_packages(conn, default_academy_id(conn))


@router.post("/packages", status_code=201)
def create_package(body: PackageCreate, conn: Conn) -> dict:
    academy_id = default_academy_id(conn)
    package_id = crud.create_package(
        conn, academy_id, body.subject_count, body.monthly_price_centimes
    )
    return {"id": package_id}


# --- students ------------------------------------------------------------


class StudentCreate(BaseModel):
    name: str
    level_id: int
    phone: str | None = None


class StudentPatch(BaseModel):
    name: str | None = None
    level_id: int | None = None
    phone: str | None = None
    is_active: bool | None = None


@router.get("/students")
def students(conn: Conn, include_inactive: bool = False) -> list[dict]:
    return crud.list_students(conn, default_academy_id(conn), include_inactive)


@router.post("/students", status_code=201)
def create_student(body: StudentCreate, conn: Conn) -> dict:
    academy_id = default_academy_id(conn)
    student_id = crud.create_student(
        conn, academy_id, body.name, body.level_id, body.phone
    )
    return {"id": student_id}


@router.patch("/students/{student_id}")
def patch_student(student_id: int, patch: StudentPatch, conn: Conn) -> dict:
    fields = patch.model_dump(exclude_none=True)
    if "is_active" in fields:
        fields["is_active"] = int(fields["is_active"])
    crud.update_student(conn, student_id, fields)
    return {"id": student_id}


# --- enrollments & months ------------------------------------------------


class EnrollmentCreate(BaseModel):
    student_id: int
    month: str
    package_id: int
    class_ids: list[int]
    price_centimes: int | None = None


class AdjustmentCreate(BaseModel):
    kind: str  # 'percent' | 'amount'
    value: int
    scope: str = "package"
    class_id: int | None = None
    category: str = "discount"
    reason: str | None = None
    bearers: list[dict] = []


class CopyMonth(BaseModel):
    from_month: str
    to_month: str


@router.get("/months/{month}/overview")
def overview(month: str, conn: Conn) -> list[dict]:
    return crud.month_overview(conn, default_academy_id(conn), month)


@router.post("/enrollments", status_code=201)
def create_enrollment(body: EnrollmentCreate, conn: Conn) -> dict:
    enrollment_id = crud.create_enrollment(
        conn,
        body.student_id,
        body.month,
        body.package_id,
        body.class_ids,
        body.price_centimes,
    )
    return {"id": enrollment_id}


@router.post("/enrollments/{enrollment_id}/adjustments", status_code=201)
def create_adjustment(enrollment_id: int, body: AdjustmentCreate, conn: Conn) -> dict:
    adjustment_id = crud.add_adjustment(conn, enrollment_id, body.model_dump())
    return {"id": adjustment_id}


@router.post("/months/copy")
def copy_month(body: CopyMonth, conn: Conn) -> dict:
    academy_id = default_academy_id(conn)
    copied = crud.copy_month(conn, academy_id, body.from_month, body.to_month)
    return {"copied": copied}


# --- payments ------------------------------------------------------------


class PaymentCreate(BaseModel):
    enrollment_id: int
    paid_on: str | None = None


class ReverseBody(BaseModel):
    reason: str | None = None


@router.post("/payments", status_code=201)
def create_payment(body: PaymentCreate, conn: Conn) -> dict:
    posted = post_payment(SqlitePaymentStore(conn), body.enrollment_id, body.paid_on)
    return {"payment_id": posted.payment_id, "net_centimes": posted.net_amount}


@router.post("/payments/{payment_id}/reverse")
def reverse(payment_id: int, body: ReverseBody, conn: Conn) -> dict:
    reversed_payment = reverse_payment(
        SqlitePaymentStore(conn), payment_id, body.reason
    )
    return {"payment_id": reversed_payment.payment_id}


# --- reports -------------------------------------------------------------


@router.get("/reports/monthly")
def report_monthly(month: str, conn: Conn) -> dict:
    report = monthly_report(conn, default_academy_id(conn), month)
    return {
        "month": report.month,
        "cash_in": report.cash_in,
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


@router.get("/reports/arrears")
def report_arrears(up_to_month: str, conn: Conn) -> list[dict]:
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
