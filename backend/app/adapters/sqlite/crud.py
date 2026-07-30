"""Thin CRUD queries used by the API layer. Money mutations live elsewhere.

Every public write is one transaction: all statements, then a single commit;
any failure rolls back so a rejected request never persists partial state.
"""

import json
import sqlite3
from contextlib import contextmanager

from app.adapters.sqlite.payment_store import SqlitePaymentStore
from app.services.payments import net_price
from app.services.proration import DEFAULT_SEGMENTS_BP


@contextmanager
def _transaction(conn: sqlite3.Connection):
    try:
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def list_academies(conn: sqlite3.Connection) -> list[dict]:
    academies = _rows(conn, "SELECT * FROM academy WHERE is_active = 1")
    return [
        {
            **academy,
            "venue": _venue(conn, academy["id"]),
            "proration_bp": (
                json.loads(academy["proration_json"])
                if academy.get("proration_json")
                else list(DEFAULT_SEGMENTS_BP)
            ),
        }
        for academy in academies
    ]


def academy_proration(conn: sqlite3.Connection, academy_id: int) -> tuple[int, ...]:
    row = conn.execute(
        "SELECT proration_json FROM academy WHERE id = ?", (academy_id,)
    ).fetchone()
    if row is None or not row["proration_json"]:
        return DEFAULT_SEGMENTS_BP
    return tuple(json.loads(row["proration_json"]))


def update_academy(conn: sqlite3.Connection, academy_id: int, fields: dict) -> None:
    _update(
        conn,
        "academy",
        academy_id,
        fields,
        {"name", "venue_bp", "owner_bp", "proration_json"},
    )


def list_levels(conn: sqlite3.Connection, academy_id: int) -> list[dict]:
    return _rows(
        conn,
        "SELECT * FROM school_level WHERE academy_id = ? AND is_active = 1"
        " ORDER BY sort_order",
        (academy_id,),
    )


def _active_clause(include_inactive: bool, prefix: str = "") -> str:
    return "" if include_inactive else f" AND {prefix}is_active = 1"


def list_subjects(
    conn: sqlite3.Connection, academy_id: int, include_inactive: bool = False
) -> list[dict]:
    return _rows(
        conn,
        f"""
        SELECT s.*,
          (SELECT COUNT(*) FROM class_group cg
           WHERE cg.subject_id = s.id AND cg.is_active = 1) AS class_count,
          (SELECT GROUP_CONCAT(DISTINCT sl.name) FROM class_group cg
           JOIN school_level sl ON sl.id = cg.level_id
           WHERE cg.subject_id = s.id AND cg.is_active = 1) AS levels
        FROM subject s
        WHERE s.academy_id = ?{_active_clause(include_inactive, "s.")}
        ORDER BY s.name
        """,
        (academy_id,),
    )


def create_subject(conn: sqlite3.Connection, academy_id: int, name: str) -> int:
    return _insert(
        conn, "INSERT INTO subject (academy_id, name) VALUES (?, ?)", (academy_id, name)
    )


def update_subject(conn: sqlite3.Connection, subject_id: int, fields: dict) -> None:
    _update(conn, "subject", subject_id, fields, {"name", "is_active"})


def list_teachers(
    conn: sqlite3.Connection,
    academy_id: int,
    include_inactive: bool = False,
    month: str | None = None,
) -> list[dict]:
    return _rows(
        conn,
        f"""
        SELECT t.*,
          COALESCE((SELECT SUM(le.amount_centimes) FROM ledger_entry le
                    WHERE le.beneficiary_kind = 'teacher'
                      AND le.beneficiary_id = t.id
                      AND le.month = ?), 0) AS earned_centimes,
          (SELECT GROUP_CONCAT(DISTINCT sub.name) FROM class_group cg
           JOIN subject sub ON sub.id = cg.subject_id
           WHERE cg.teacher_id = t.id AND cg.is_active = 1) AS subjects
        FROM teacher t
        WHERE t.academy_id = ?{_active_clause(include_inactive, "t.")}
        ORDER BY t.name
        """,
        (month or "", academy_id),
    )


def update_teacher(conn: sqlite3.Connection, teacher_id: int, fields: dict) -> None:
    _update(conn, "teacher", teacher_id, fields, {"name", "phone", "is_active"})


def create_teacher(
    conn: sqlite3.Connection, academy_id: int, name: str, phone: str | None
) -> int:
    return _insert(
        conn,
        "INSERT INTO teacher (academy_id, name, phone) VALUES (?, ?, ?)",
        (academy_id, name, phone),
    )


def list_classes(
    conn: sqlite3.Connection,
    academy_id: int,
    include_inactive: bool = False,
    month: str | None = None,
) -> list[dict]:
    return _rows(
        conn,
        f"""
        SELECT cg.*, sub.name AS subject_name, t.name AS teacher_name,
               sl.name AS level_name,
          (SELECT COUNT(*) FROM enrollment_class ec
           JOIN enrollment e ON e.id = ec.enrollment_id
           JOIN student st ON st.id = e.student_id
           WHERE ec.class_id = cg.id AND e.month = ? AND st.is_active = 1
          ) AS enrolled_count
        FROM class_group cg
        JOIN subject sub ON sub.id = cg.subject_id
        JOIN teacher t ON t.id = cg.teacher_id
        JOIN school_level sl ON sl.id = cg.level_id
        WHERE cg.academy_id = ?{_active_clause(include_inactive, "cg.")}
        ORDER BY sl.sort_order, sub.name, cg.name
        """,
        (month or "", academy_id),
    )


def update_class(conn: sqlite3.Connection, class_id: int, fields: dict) -> None:
    _update(
        conn,
        "class_group",
        class_id,
        fields,
        {
            "name",
            "level_id",
            "subject_id",
            "teacher_id",
            "day_of_week",
            "start_time",
            "is_active",
        },
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


def list_motifs(
    conn: sqlite3.Connection, academy_id: int, include_inactive: bool = False
) -> list[dict]:
    return _rows(
        conn,
        "SELECT * FROM motif WHERE academy_id = ?"
        f"{_active_clause(include_inactive)} ORDER BY label",
        (academy_id,),
    )


def create_motif(conn: sqlite3.Connection, academy_id: int, label: str) -> int:
    return _insert(
        conn, "INSERT INTO motif (academy_id, label) VALUES (?, ?)", (academy_id, label)
    )


def update_motif(conn: sqlite3.Connection, motif_id: int, fields: dict) -> None:
    _update(conn, "motif", motif_id, fields, {"label", "is_active"})


def subjects_taught_at_level(conn: sqlite3.Connection, level_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(DISTINCT subject_id) FROM class_group"
        " WHERE level_id = ? AND is_active = 1",
        (level_id,),
    ).fetchone()
    return row[0]


def list_packages(
    conn: sqlite3.Connection, academy_id: int, include_inactive: bool = False
) -> list[dict]:
    return _rows(
        conn,
        "SELECT p.*, sl.name AS level_name FROM package p"
        " LEFT JOIN school_level sl ON sl.id = p.level_id"
        f" WHERE p.academy_id = ?{_active_clause(include_inactive, 'p.')}"
        " ORDER BY sl.sort_order, p.subject_count",
        (academy_id,),
    )


def package_row(conn: sqlite3.Connection, package_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM package WHERE id = ?", (package_id,)).fetchone()
    return dict(row) if row else None


def update_package(conn: sqlite3.Connection, package_id: int, fields: dict) -> None:
    _update(
        conn,
        "package",
        package_id,
        fields,
        {"subject_count", "monthly_price_centimes", "level_id", "is_active"},
    )


def create_package(
    conn: sqlite3.Connection,
    academy_id: int,
    subject_count: int,
    price: int,
    level_id: int | None = None,
) -> int:
    return _insert(
        conn,
        "INSERT INTO package (academy_id, subject_count, monthly_price_centimes,"
        " level_id) VALUES (?, ?, ?, ?)",
        (academy_id, subject_count, price, level_id),
    )


def list_students(
    conn: sqlite3.Connection,
    academy_id: int,
    include_inactive: bool,
    month: str | None = None,
) -> list[dict]:
    active_filter = "" if include_inactive else " AND s.is_active = 1"
    return _rows(
        conn,
        f"""
        SELECT s.*, sl.name AS level_name,
          (SELECT COUNT(*) FROM enrollment e
           LEFT JOIN payment p ON p.enrollment_id = e.id AND p.reversed_at IS NULL
           WHERE e.student_id = s.id AND e.month < ? AND p.id IS NULL
          ) AS unpaid_months,
          (SELECT e2.id FROM enrollment e2
           WHERE e2.student_id = s.id AND e2.month = ?
          ) AS month_enrollment_id,
          EXISTS(SELECT 1 FROM enrollment e3
           JOIN payment p3 ON p3.enrollment_id = e3.id AND p3.reversed_at IS NULL
           WHERE e3.student_id = s.id AND e3.month = ?
          ) AS month_paid
        FROM student s
        JOIN school_level sl ON sl.id = s.level_id
        WHERE s.academy_id = ?{active_filter} ORDER BY s.name
        """,
        (month or "", month or "", month or "", academy_id),
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
    arrival_date: str | None = None,
) -> int:
    with _transaction(conn):
        return _insert_enrollment(
            conn,
            student_id,
            month,
            package_id,
            class_ids,
            price_centimes,
            arrival_date,
        )


def _insert_enrollment(
    conn: sqlite3.Connection,
    student_id: int,
    month: str,
    package_id: int,
    class_ids: list[int],
    price_centimes: int | None,
    arrival_date: str | None = None,
) -> int:
    price = (
        price_centimes
        if price_centimes is not None
        else _package_price(conn, package_id)
    )
    enrollment_id = conn.execute(
        "INSERT INTO enrollment (student_id, package_id, month, price_centimes,"
        " arrival_date) VALUES (?, ?, ?, ?, ?)",
        (student_id, package_id, month, price, arrival_date),
    ).lastrowid
    conn.executemany(
        "INSERT INTO enrollment_class (enrollment_id, class_id) VALUES (?, ?)",
        [(enrollment_id, class_id) for class_id in class_ids],
    )
    return enrollment_id


def enrollment_class_ids(conn: sqlite3.Connection, enrollment_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT class_id FROM enrollment_class WHERE enrollment_id = ?"
        " ORDER BY class_id",
        (enrollment_id,),
    )
    return [row["class_id"] for row in rows]


def add_adjustment(conn: sqlite3.Connection, enrollment_id: int, fields: dict) -> int:
    with _transaction(conn):
        adjustment_id = conn.execute(
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
        ).lastrowid
        conn.executemany(
            "INSERT INTO adjustment_bearer (adjustment_id, bearer_kind, bearer_id,"
            " share_centimes, share_bp) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    adjustment_id,
                    bearer["kind"],
                    bearer["ref_id"],
                    bearer.get("share_centimes"),
                    bearer.get("share_bp"),
                )
                for bearer in fields.get("bearers", [])
            ],
        )
        return adjustment_id


def adjustment_row(conn: sqlite3.Connection, adjustment_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM adjustment WHERE id = ? AND is_active = 1", (adjustment_id,)
    ).fetchone()
    return dict(row) if row else None


def adjustment_bearers(conn: sqlite3.Connection, adjustment_id: int) -> list[dict]:
    return _rows(
        conn,
        "SELECT bearer_kind AS kind, bearer_id AS ref_id, share_centimes, share_bp"
        " FROM adjustment_bearer WHERE adjustment_id = ?",
        (adjustment_id,),
    )


def enrollment_month(conn: sqlite3.Connection, enrollment_id: int) -> str | None:
    row = conn.execute(
        "SELECT month FROM enrollment WHERE id = ?", (enrollment_id,)
    ).fetchone()
    return row["month"] if row else None


def enrollment_is_paid(conn: sqlite3.Connection, enrollment_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM payment WHERE enrollment_id = ? AND reversed_at IS NULL",
        (enrollment_id,),
    ).fetchone()
    return row is not None


def update_adjustment(
    conn: sqlite3.Connection,
    adjustment_id: int,
    fields: dict,
    bearers: list[dict] | None,
) -> None:
    """Edit a configured adjustment in place; bearers=None keeps the current ones."""
    allowed = {"kind", "value", "scope", "class_id", "category", "reason"}
    changes = {key: value for key, value in fields.items() if key in allowed}
    with _transaction(conn):
        if changes:
            assignments = ", ".join(f"{column} = ?" for column in changes)
            conn.execute(
                f"UPDATE adjustment SET {assignments} WHERE id = ?",
                (*changes.values(), adjustment_id),
            )
        if bearers is not None:
            conn.execute(
                "DELETE FROM adjustment_bearer WHERE adjustment_id = ?",
                (adjustment_id,),
            )
            conn.executemany(
                "INSERT INTO adjustment_bearer (adjustment_id, bearer_kind, bearer_id,"
                " share_centimes, share_bp) VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        adjustment_id,
                        bearer["kind"],
                        bearer["ref_id"],
                        bearer.get("share_centimes"),
                        bearer.get("share_bp"),
                    )
                    for bearer in bearers
                ],
            )


def delete_adjustment(conn: sqlite3.Connection, adjustment_id: int) -> None:
    """Deactivate a configured adjustment — only while its enrollment is unpaid.

    Soft delete: after a reversed payment, ledger lines still reference the
    adjustment, so removing the row would break the ledger's foreign keys."""
    from app.ports.payments import AlreadyPaidError

    row = conn.execute(
        "SELECT enrollment_id FROM adjustment WHERE id = ?", (adjustment_id,)
    ).fetchone()
    if row is None:
        raise LookupError(f"no adjustment {adjustment_id}")
    paid = conn.execute(
        "SELECT 1 FROM payment WHERE enrollment_id = ? AND reversed_at IS NULL",
        (row["enrollment_id"],),
    ).fetchone()
    if paid:
        raise AlreadyPaidError(
            "enrollment is paid; reverse the payment before changing adjustments"
        )
    with _transaction(conn):
        conn.execute(
            "UPDATE adjustment SET is_active = 0 WHERE id = ?", (adjustment_id,)
        )


def month_overview(
    conn: sqlite3.Connection,
    academy_id: int,
    month: str,
    include_inactive: bool = False,
) -> list[dict]:
    """include_inactive matters for archival exports: a student deactivated in
    October must still appear on September's record."""
    active_filter = "" if include_inactive else " AND s.is_active = 1"
    students = _rows(
        conn,
        f"""
        SELECT s.id AS student_id, s.name AS student_name, s.level_id,
               sl.name AS level_name,
               e.id AS enrollment_id, e.price_centimes, e.arrival_date,
               p.id AS payment_id,
               EXISTS(
                 SELECT 1 FROM enrollment prior
                 LEFT JOIN payment pp ON pp.enrollment_id = prior.id
                   AND pp.reversed_at IS NULL
                 WHERE prior.student_id = s.id AND prior.month < ?
                   AND pp.id IS NULL
               ) AS has_arrears
        FROM student s
        JOIN school_level sl ON sl.id = s.level_id
        LEFT JOIN enrollment e ON e.student_id = s.id AND e.month = ?
        LEFT JOIN payment p ON p.enrollment_id = e.id AND p.reversed_at IS NULL
        WHERE s.academy_id = ?{active_filter}
        ORDER BY s.name
        """,
        (month, month, academy_id),
    )
    store = SqlitePaymentStore(conn)
    return [_overview_row(conn, store, row) for row in students]


def enrollment_has_payment_history(
    conn: sqlite3.Connection, enrollment_id: int
) -> bool:
    row = conn.execute(
        "SELECT 1 FROM payment WHERE enrollment_id = ?", (enrollment_id,)
    ).fetchone()
    return row is not None


def delete_enrollment(conn: sqlite3.Connection, enrollment_id: int) -> None:
    """Un-enroll: only for enrollments with NO payment history at all —
    anything the ledger has ever referenced stays forever."""
    with _transaction(conn):
        conn.execute(
            "DELETE FROM adjustment_bearer WHERE adjustment_id IN"
            " (SELECT id FROM adjustment WHERE enrollment_id = ?)",
            (enrollment_id,),
        )
        conn.execute("DELETE FROM adjustment WHERE enrollment_id = ?", (enrollment_id,))
        conn.execute(
            "DELETE FROM enrollment_class WHERE enrollment_id = ?", (enrollment_id,)
        )
        conn.execute("DELETE FROM enrollment WHERE id = ?", (enrollment_id,))


def latest_enrolled_month_before(
    conn: sqlite3.Connection, academy_id: int, month: str
) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(e.month) FROM enrollment e
        JOIN student s ON s.id = e.student_id
        WHERE s.academy_id = ? AND e.month < ?
        """,
        (academy_id, month),
    ).fetchone()
    return row[0]


def copy_month(
    conn: sqlite3.Connection, academy_id: int, from_month: str, to_month: str
) -> int:
    source = _rows(
        conn,
        """
        SELECT e.id, e.student_id, e.package_id, e.price_centimes,
               e.arrival_date, p.monthly_price_centimes AS package_price
        FROM enrollment e
        JOIN student s ON s.id = e.student_id
        JOIN package p ON p.id = e.package_id
        WHERE s.academy_id = ? AND e.month = ? AND s.is_active = 1
          AND NOT EXISTS (
            SELECT 1 FROM enrollment t
            WHERE t.student_id = e.student_id AND t.month = ?
          )
        """,
        (academy_id, from_month, to_month),
    )
    with _transaction(conn):
        for enrollment in source:
            # A prorated first month is a one-off concession: the extension
            # re-prices from the package. Manual overrides carry over.
            price = (
                enrollment["package_price"]
                if enrollment["arrival_date"] is not None
                else enrollment["price_centimes"]
            )
            _insert_enrollment(
                conn,
                enrollment["student_id"],
                to_month,
                enrollment["package_id"],
                enrollment_class_ids(conn, enrollment["id"]),
                price,
            )
    return len(source)


def _overview_row(conn, store, row) -> dict:
    base = {
        "student_id": row["student_id"],
        "student_name": row["student_name"],
        "level_id": row["level_id"],
        "level_name": row["level_name"],
        "has_arrears": bool(row["has_arrears"]),
    }
    if row["enrollment_id"] is None:
        return {**base, "enrollment": None}
    return {
        **base,
        "enrollment": {
            "id": row["enrollment_id"],
            "price_centimes": row["price_centimes"],
            "arrival_date": row["arrival_date"],
            "net_centimes": safe_net(
                store, row["enrollment_id"], row["price_centimes"]
            ),
            "paid": row["payment_id"] is not None,
            "payment_id": row["payment_id"],
            "classes": _enrollment_classes(conn, row["enrollment_id"]),
            "split": _row_split(conn, store, row["enrollment_id"]),
        },
    }


def _row_split(conn, store, enrollment_id: int) -> list[dict]:
    """Per-beneficiary final amounts, shown directly in listing rows."""
    from app.adapters.sqlite.reports import _beneficiary_name
    from app.services.payments import payment_preview

    try:
        preview = payment_preview(store, enrollment_id)
    except ValueError:
        return []
    return [
        {
            "kind": line.beneficiary.kind,
            "ref_id": line.beneficiary.ref_id,
            "name": _beneficiary_name(
                conn, line.beneficiary.kind, line.beneficiary.ref_id
            ),
            "final_centimes": line.final,
        }
        for line in preview.lines
    ]


def safe_net(store: SqlitePaymentStore, enrollment_id: int, fallback: int) -> int:
    """Net price, degrading to the list price if a stored adjustment is invalid
    — one bad row must never take down a whole listing."""
    try:
        return net_price(store.enrollment_context(enrollment_id))
    except ValueError:
        return fallback


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
        _require_row(conn, table, row_id)
        return
    assignments = ", ".join(f"{column} = ?" for column in changes)
    cursor = conn.execute(
        f"UPDATE {table} SET {assignments} WHERE id = ?",
        (*changes.values(), row_id),
    )
    if cursor.rowcount == 0:
        conn.rollback()
        raise LookupError(f"no {table} {row_id}")
    conn.commit()


def _require_row(conn: sqlite3.Connection, table: str, row_id: int) -> None:
    row = conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (row_id,)).fetchone()
    if row is None:
        raise LookupError(f"no {table} {row_id}")
