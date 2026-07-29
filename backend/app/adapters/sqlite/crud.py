"""Thin CRUD queries used by the API layer. Money mutations live elsewhere."""

import sqlite3

from app.adapters.sqlite.payment_store import SqlitePaymentStore
from app.services.payments import net_price


def list_academies(conn: sqlite3.Connection) -> list[dict]:
    academies = _rows(conn, "SELECT * FROM academy WHERE is_active = 1")
    return [{**academy, "venue": _venue(conn, academy["id"])} for academy in academies]


def update_academy(conn: sqlite3.Connection, academy_id: int, fields: dict) -> None:
    _update(conn, "academy", academy_id, fields, {"name", "venue_bp", "owner_bp"})


def list_levels(conn: sqlite3.Connection, academy_id: int) -> list[dict]:
    return _rows(
        conn,
        "SELECT * FROM school_level WHERE academy_id = ? AND is_active = 1"
        " ORDER BY sort_order",
        (academy_id,),
    )


def list_subjects(conn: sqlite3.Connection, academy_id: int) -> list[dict]:
    return _rows(
        conn,
        "SELECT * FROM subject WHERE academy_id = ? AND is_active = 1 ORDER BY name",
        (academy_id,),
    )


def create_subject(conn: sqlite3.Connection, academy_id: int, name: str) -> int:
    return _insert(
        conn, "INSERT INTO subject (academy_id, name) VALUES (?, ?)", (academy_id, name)
    )


def list_teachers(conn: sqlite3.Connection, academy_id: int) -> list[dict]:
    return _rows(
        conn,
        "SELECT * FROM teacher WHERE academy_id = ? AND is_active = 1 ORDER BY name",
        (academy_id,),
    )


def create_teacher(
    conn: sqlite3.Connection, academy_id: int, name: str, phone: str | None
) -> int:
    return _insert(
        conn,
        "INSERT INTO teacher (academy_id, name, phone) VALUES (?, ?, ?)",
        (academy_id, name, phone),
    )


def list_classes(conn: sqlite3.Connection, academy_id: int) -> list[dict]:
    return _rows(
        conn,
        """
        SELECT cg.*, sub.name AS subject_name, t.name AS teacher_name,
               sl.name AS level_name
        FROM class_group cg
        JOIN subject sub ON sub.id = cg.subject_id
        JOIN teacher t ON t.id = cg.teacher_id
        JOIN school_level sl ON sl.id = cg.level_id
        WHERE cg.academy_id = ? AND cg.is_active = 1
        ORDER BY sl.sort_order, sub.name, cg.name
        """,
        (academy_id,),
    )


def create_class(conn: sqlite3.Connection, academy_id: int, fields: dict) -> int:
    return _insert(
        conn,
        "INSERT INTO class_group (academy_id, level_id, subject_id, teacher_id,"
        " name, day_of_week, start_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            academy_id,
            fields["level_id"],
            fields["subject_id"],
            fields["teacher_id"],
            fields.get("name", "A"),
            fields.get("day_of_week"),
            fields.get("start_time"),
        ),
    )


def list_packages(conn: sqlite3.Connection, academy_id: int) -> list[dict]:
    return _rows(
        conn,
        "SELECT * FROM package WHERE academy_id = ? AND is_active = 1"
        " ORDER BY subject_count",
        (academy_id,),
    )


def create_package(
    conn: sqlite3.Connection, academy_id: int, subject_count: int, price: int
) -> int:
    return _insert(
        conn,
        "INSERT INTO package (academy_id, subject_count, monthly_price_centimes)"
        " VALUES (?, ?, ?)",
        (academy_id, subject_count, price),
    )


def list_students(
    conn: sqlite3.Connection, academy_id: int, include_inactive: bool
) -> list[dict]:
    active_filter = "" if include_inactive else " AND s.is_active = 1"
    return _rows(
        conn,
        "SELECT s.*, sl.name AS level_name FROM student s"
        " JOIN school_level sl ON sl.id = s.level_id"
        f" WHERE s.academy_id = ?{active_filter} ORDER BY s.name",
        (academy_id,),
    )


def create_student(
    conn: sqlite3.Connection,
    academy_id: int,
    name: str,
    level_id: int,
    phone: str | None,
) -> int:
    return _insert(
        conn,
        "INSERT INTO student (academy_id, level_id, name, phone) VALUES (?, ?, ?, ?)",
        (academy_id, level_id, name, phone),
    )


def update_student(conn: sqlite3.Connection, student_id: int, fields: dict) -> None:
    _update(
        conn, "student", student_id, fields, {"name", "level_id", "phone", "is_active"}
    )


def create_enrollment(
    conn: sqlite3.Connection,
    student_id: int,
    month: str,
    package_id: int,
    class_ids: list[int],
    price_centimes: int | None,
) -> int:
    price = (
        price_centimes
        if price_centimes is not None
        else _package_price(conn, package_id)
    )
    enrollment_id = _insert(
        conn,
        "INSERT INTO enrollment (student_id, package_id, month, price_centimes)"
        " VALUES (?, ?, ?, ?)",
        (student_id, package_id, month, price),
    )
    conn.executemany(
        "INSERT INTO enrollment_class (enrollment_id, class_id) VALUES (?, ?)",
        [(enrollment_id, class_id) for class_id in class_ids],
    )
    conn.commit()
    return enrollment_id


def add_adjustment(conn: sqlite3.Connection, enrollment_id: int, fields: dict) -> int:
    adjustment_id = _insert(
        conn,
        "INSERT INTO adjustment (enrollment_id, scope, class_id, kind, value,"
        " category, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            enrollment_id,
            fields.get("scope", "package"),
            fields.get("class_id"),
            fields["kind"],
            fields["value"],
            fields.get("category", "discount"),
            fields.get("reason"),
        ),
    )
    conn.executemany(
        "INSERT INTO adjustment_bearer (adjustment_id, bearer_kind, bearer_id)"
        " VALUES (?, ?, ?)",
        [
            (adjustment_id, bearer["kind"], bearer["ref_id"])
            for bearer in fields.get("bearers", [])
        ],
    )
    conn.commit()
    return adjustment_id


def month_overview(conn: sqlite3.Connection, academy_id: int, month: str) -> list[dict]:
    students = _rows(
        conn,
        """
        SELECT s.id AS student_id, s.name AS student_name, sl.name AS level_name,
               e.id AS enrollment_id, e.price_centimes,
               p.id AS payment_id
        FROM student s
        JOIN school_level sl ON sl.id = s.level_id
        LEFT JOIN enrollment e ON e.student_id = s.id AND e.month = ?
        LEFT JOIN payment p ON p.enrollment_id = e.id AND p.reversed_at IS NULL
        WHERE s.academy_id = ? AND s.is_active = 1
        ORDER BY s.name
        """,
        (month, academy_id),
    )
    store = SqlitePaymentStore(conn)
    return [_overview_row(conn, store, row) for row in students]


def copy_month(
    conn: sqlite3.Connection, academy_id: int, from_month: str, to_month: str
) -> int:
    source = _rows(
        conn,
        """
        SELECT e.id, e.student_id, e.package_id, e.price_centimes
        FROM enrollment e
        JOIN student s ON s.id = e.student_id
        WHERE s.academy_id = ? AND e.month = ? AND s.is_active = 1
          AND NOT EXISTS (
            SELECT 1 FROM enrollment t
            WHERE t.student_id = e.student_id AND t.month = ?
          )
        """,
        (academy_id, from_month, to_month),
    )
    for enrollment in source:
        class_ids = [
            row["class_id"]
            for row in _rows(
                conn,
                "SELECT class_id FROM enrollment_class WHERE enrollment_id = ?",
                (enrollment["id"],),
            )
        ]
        create_enrollment(
            conn,
            enrollment["student_id"],
            to_month,
            enrollment["package_id"],
            class_ids,
            enrollment["price_centimes"],
        )
    return len(source)


def _overview_row(conn, store, row) -> dict:
    base = {
        "student_id": row["student_id"],
        "student_name": row["student_name"],
        "level_name": row["level_name"],
    }
    if row["enrollment_id"] is None:
        return {**base, "enrollment": None}
    return {
        **base,
        "enrollment": {
            "id": row["enrollment_id"],
            "price_centimes": row["price_centimes"],
            "net_centimes": net_price(store.enrollment_context(row["enrollment_id"])),
            "paid": row["payment_id"] is not None,
            "payment_id": row["payment_id"],
            "classes": _enrollment_classes(conn, row["enrollment_id"]),
        },
    }


def _enrollment_classes(conn: sqlite3.Connection, enrollment_id: int) -> list[dict]:
    return _rows(
        conn,
        """
        SELECT cg.id, sub.name AS subject_name, t.name AS teacher_name
        FROM enrollment_class ec
        JOIN class_group cg ON cg.id = ec.class_id
        JOIN subject sub ON sub.id = cg.subject_id
        JOIN teacher t ON t.id = cg.teacher_id
        WHERE ec.enrollment_id = ?
        ORDER BY ec.class_id
        """,
        (enrollment_id,),
    )


def _venue(conn: sqlite3.Connection, academy_id: int) -> dict | None:
    rows = _rows(
        conn,
        "SELECT * FROM venue WHERE academy_id = ? AND is_active = 1"
        " ORDER BY id LIMIT 1",
        (academy_id,),
    )
    return rows[0] if rows else None


def _package_price(conn: sqlite3.Connection, package_id: int) -> int:
    row = conn.execute(
        "SELECT monthly_price_centimes FROM package WHERE id = ?", (package_id,)
    ).fetchone()
    if row is None:
        raise LookupError(f"no package {package_id}")
    return row["monthly_price_centimes"]


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params)]


def _insert(conn: sqlite3.Connection, sql: str, params: tuple) -> int:
    row_id = conn.execute(sql, params).lastrowid
    conn.commit()
    return row_id


def _update(
    conn: sqlite3.Connection, table: str, row_id: int, fields: dict, allowed: set[str]
) -> None:
    changes = {key: value for key, value in fields.items() if key in allowed}
    if not changes:
        return
    assignments = ", ".join(f"{column} = ?" for column in changes)
    conn.execute(
        f"UPDATE {table} SET {assignments} WHERE id = ?",
        (*changes.values(), row_id),
    )
    conn.commit()
