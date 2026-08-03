"""Thin CRUD queries used by the API layer. Money mutations live elsewhere.

Every public write is one transaction: all statements, then a single commit;
any failure rolls back so a rejected request never persists partial state.
"""

import json
import sqlite3
from contextlib import contextmanager

from app.adapters.sqlite.payment_store import SqlitePaymentStore
from app.domain.money import percent_of, split_equally
from app.domain.splitting import _proportional_parts
from app.services.payments import net_price, payment_preview
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


def create_level(
    conn: sqlite3.Connection, academy_id: int, name: str, teaching_annees: int
) -> int:
    order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM school_level"
        " WHERE academy_id = ?",
        (academy_id,),
    ).fetchone()[0]
    return _insert(
        conn,
        "INSERT INTO school_level (academy_id, name, sort_order, teaching_annees)"
        " VALUES (?, ?, ?, ?)",
        (academy_id, name, order, teaching_annees),
    )


def _active_clause(include_inactive: bool, prefix: str = "") -> str:
    return "" if include_inactive else f" AND {prefix}is_active = 1"


def list_subjects(
    conn: sqlite3.Connection, academy_id: int, include_inactive: bool = False
) -> list[dict]:
    return _rows(
        conn,
        f"""
        SELECT s.*, sl.name AS level_name,
          (SELECT COUNT(*) FROM class_group cg
           WHERE cg.subject_id = s.id AND cg.is_active = 1) AS class_count,
          (SELECT COUNT(*) FROM class_group cg
           WHERE cg.subject_id = s.id AND cg.is_active = 0)
              AS archived_class_count,
          (SELECT GROUP_CONCAT(DISTINCT sl2.name) FROM class_group cg
           JOIN school_level sl2 ON sl2.id = cg.level_id
           WHERE cg.subject_id = s.id AND cg.is_active = 1) AS levels
        FROM subject s
        LEFT JOIN school_level sl ON sl.id = s.level_id
        WHERE s.academy_id = ?{_active_clause(include_inactive, "s.")}
        ORDER BY COALESCE(sl.sort_order, 99), s.name
        """,
        (academy_id,),
    )


def create_subject(
    conn: sqlite3.Connection, academy_id: int, name: str, level_id: int | None = None
) -> int:
    return _insert(
        conn,
        "INSERT INTO subject (academy_id, name, level_id) VALUES (?, ?, ?)",
        (academy_id, name, level_id),
    )


def update_subject(conn: sqlite3.Connection, subject_id: int, fields: dict) -> None:
    # No archive on matières: they are delete-with-guardrails only.
    _update(conn, "subject", subject_id, fields, {"name"})


def subject_delete_blockers(conn: sqlite3.Connection, subject_id: int) -> dict:
    """What stands between this matière and deletion: active classes must be
    handled first; archived classes only matter when students were ever
    enrolled (ledger history). Archived-but-never-enrolled leftovers are
    noise and will be swept away with the matière."""
    _require_row(conn, "subject", subject_id)
    row = conn.execute(
        """
        SELECT
          SUM(cg.is_active = 1) AS active,
          SUM(cg.is_active = 0 AND EXISTS (
              SELECT 1 FROM enrollment_class ec WHERE ec.class_id = cg.id
          )) AS archived_with_history
        FROM class_group cg WHERE cg.subject_id = ?
        """,
        (subject_id,),
    ).fetchone()
    return {
        "active": row["active"] or 0,
        "archived_with_history": row["archived_with_history"] or 0,
    }


def delete_subject(conn: sqlite3.Connection, subject_id: int) -> None:
    """Only once nothing money-bearing references it — then the matière, its
    never-enrolled archived classes and its capabilities all go, so no
    ghost ✓ chips survive on any professor profile."""
    with _transaction(conn):
        conn.execute(
            "DELETE FROM class_teacher WHERE class_id IN"
            " (SELECT id FROM class_group WHERE subject_id = ?)",
            (subject_id,),
        )
        conn.execute("DELETE FROM class_group WHERE subject_id = ?", (subject_id,))
        conn.execute(
            "DELETE FROM teacher_capability WHERE subject_id = ?", (subject_id,)
        )
        conn.execute("DELETE FROM subject WHERE id = ?", (subject_id,))


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
    if fields.get("is_owner"):
        row = conn.execute(
            "SELECT academy_id FROM teacher WHERE id = ?", (teacher_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f"no teacher {teacher_id}")
        # One human wears the crown: linking this teacher unlinks the others.
        conn.execute(
            "UPDATE teacher SET is_owner = 0 WHERE academy_id = ?",
            (row["academy_id"],),
        )
    _update(
        conn, "teacher", teacher_id, fields, {"name", "phone", "is_active", "is_owner"}
    )


def create_teacher(
    conn: sqlite3.Connection, academy_id: int, name: str, phone: str | None
) -> int:
    return _insert(
        conn,
        "INSERT INTO teacher (academy_id, name, phone, created_at)"
        " VALUES (?, ?, ?, datetime('now'))",
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
        LEFT JOIN teacher t ON t.id = cg.teacher_id
        JOIN school_level sl ON sl.id = cg.level_id
        WHERE cg.academy_id = ?{_active_clause(include_inactive, "cg.")}
        ORDER BY sl.sort_order, sub.name, cg.name
        """,
        (month or "", academy_id),
    )


def update_class(conn: sqlite3.Connection, class_id: int, fields: dict) -> None:
    with _transaction(conn):
        if "teacher_id" in fields:
            # The pencil is a CORRECTION ("wrong name"), not a handover: the
            # open assignment is rewritten as if this teacher always taught.
            conn.execute(
                "UPDATE class_teacher SET teacher_id = ? WHERE class_id = ?"
                " AND to_date IS NULL",
                (fields["teacher_id"], class_id),
            )
            _learn_capability_from_class(conn, class_id, fields["teacher_id"])
        allowed = {
            "name",
            "level_id",
            "subject_id",
            "teacher_id",
            "annee",
            "filiere",
            "parcours",
            "day_of_week",
            "start_time",
            "is_active",
        }
        changes = {key: value for key, value in fields.items() if key in allowed}
        if changes:
            assignments = ", ".join(f"{column} = ?" for column in changes)
            updated = conn.execute(
                f"UPDATE class_group SET {assignments} WHERE id = ?",
                (*changes.values(), class_id),
            )
            if updated.rowcount == 0:
                raise LookupError(f"no class_group {class_id}")


def create_class(conn: sqlite3.Connection, academy_id: int, fields: dict) -> int:
    with _transaction(conn):
        class_id = conn.execute(
            "INSERT INTO class_group (academy_id, level_id, subject_id, teacher_id,"
            " name, annee, filiere, parcours, day_of_week, start_time)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                academy_id,
                fields["level_id"],
                fields["subject_id"],
                fields["teacher_id"],
                _free_class_name(
                    conn,
                    academy_id,
                    fields["level_id"],
                    fields["subject_id"],
                    fields["teacher_id"],
                    fields.get("name", "A"),
                ),
                fields.get("annee"),
                fields.get("filiere"),
                fields.get("parcours"),
                fields.get("day_of_week"),
                fields.get("start_time"),
            ),
        ).lastrowid
        conn.execute(
            "INSERT INTO class_teacher (class_id, teacher_id) VALUES (?, ?)",
            (class_id, fields["teacher_id"]),
        )
        _learn_capability_from_class(conn, class_id, fields["teacher_id"])
        return class_id


def _free_class_name(
    conn: sqlite3.Connection,
    academy_id: int,
    level_id: int,
    subject_id: int,
    teacher_id: int,
    wanted: str,
) -> str:
    """The legacy UNIQUE(level, subject, teacher, name) predates années: one
    prof opening the same matière in two années collided on the internal
    name. Bump to the next free letter — the name is invisible in the UI."""
    used = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM class_group WHERE academy_id = ? AND level_id = ?"
            " AND subject_id = ? AND teacher_id = ?",
            (academy_id, level_id, subject_id, teacher_id),
        )
    }
    if wanted not in used:
        return wanted
    for offset in range(26):
        candidate = chr(ord("A") + offset)
        if candidate not in used:
            return candidate
    suffix = 2
    while f"A{suffix}" in used:
        suffix += 1
    return f"A{suffix}"


def _learn_capability_from_class(
    conn: sqlite3.Connection, class_id: int, teacher_id: int
) -> None:
    """A class someone teaches is proof of capability — record it silently."""
    row = conn.execute(
        "SELECT level_id, subject_id, annee, parcours FROM class_group WHERE id = ?",
        (class_id,),
    ).fetchone()
    if row is None:
        return
    ensure_capability(
        conn,
        teacher_id,
        row["level_id"],
        row["annee"],
        row["parcours"],
        row["subject_id"],
    )


def ensure_capability(
    conn: sqlite3.Connection,
    teacher_id: int,
    level_id: int,
    annee: int | None,
    parcours: str | None,
    subject_id: int,
) -> None:
    existing = conn.execute(
        "SELECT 1 FROM teacher_capability WHERE teacher_id = ? AND level_id = ?"
        " AND annee IS ? AND parcours IS ? AND subject_id = ?",
        (teacher_id, level_id, annee, parcours, subject_id),
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO teacher_capability (teacher_id, level_id, annee,"
            " parcours, subject_id) VALUES (?, ?, ?, ?, ?)",
            (teacher_id, level_id, annee, parcours, subject_id),
        )


def set_capabilities(
    conn: sqlite3.Connection, teacher_id: int, items: list[dict]
) -> None:
    with _transaction(conn):
        conn.execute(
            "DELETE FROM teacher_capability WHERE teacher_id = ?", (teacher_id,)
        )
        conn.executemany(
            "INSERT INTO teacher_capability (teacher_id, level_id, annee,"
            " parcours, subject_id) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    teacher_id,
                    item["level_id"],
                    item.get("annee"),
                    item.get("parcours"),
                    item["subject_id"],
                )
                for item in items
            ],
        )


def list_capabilities(conn: sqlite3.Connection, academy_id: int) -> list[dict]:
    return _rows(
        conn,
        """
        SELECT tc.*, sub.name AS subject_name, sl.name AS level_name
        FROM teacher_capability tc
        JOIN teacher t ON t.id = tc.teacher_id
        JOIN subject sub ON sub.id = tc.subject_id
        JOIN school_level sl ON sl.id = tc.level_id
        WHERE t.academy_id = ?
        """,
        (academy_id,),
    )


def replace_teacher(
    conn: sqlite3.Connection, class_id: int, date: str, successor_ids: list[int]
) -> None:
    """Dated handover: the money splits by days taught around `date`. The
    outgoing teacher keeps earning whenever his old months get collected."""
    from datetime import date as date_type
    from datetime import timedelta

    day_before = str(date_type.fromisoformat(date) - timedelta(days=1))
    with _transaction(conn):
        conn.execute(
            "UPDATE class_teacher SET to_date = ? WHERE class_id = ?"
            " AND to_date IS NULL",
            (day_before, class_id),
        )
        conn.executemany(
            "INSERT INTO class_teacher (class_id, teacher_id, from_date)"
            " VALUES (?, ?, ?)",
            [(class_id, successor, date) for successor in successor_ids],
        )
        conn.execute(
            "UPDATE class_group SET teacher_id = ? WHERE id = ?",
            (successor_ids[0], class_id),
        )
        for successor in successor_ids:
            _learn_capability_from_class(conn, class_id, successor)


def vacate_teacher(conn: sqlite3.Connection, class_id: int, date: str) -> None:
    """The teacher leaves with no successor yet: his assignment closes the
    day before, the class survives loudly marked « Sans professeur ». From
    `date` on, paid months escrow the teacher share to the académie."""
    from datetime import date as date_type
    from datetime import timedelta

    _require_row(conn, "class_group", class_id)
    day_before = str(date_type.fromisoformat(date) - timedelta(days=1))
    with _transaction(conn):
        conn.execute(
            "UPDATE class_teacher SET to_date = ? WHERE class_id = ?"
            " AND to_date IS NULL",
            (day_before, class_id),
        )
        conn.execute(
            "UPDATE class_group SET teacher_id = NULL WHERE id = ?", (class_id,)
        )


def teacher_open_class_count(conn: sqlite3.Connection, teacher_id: int) -> int:
    """Active classes this teacher still holds — as current teacher or via an
    open assignment. Archiving him is refused while this is non-zero."""
    return conn.execute(
        """
        SELECT COUNT(DISTINCT cg.id) FROM class_group cg
        LEFT JOIN class_teacher ct ON ct.class_id = cg.id
            AND ct.teacher_id = ? AND ct.to_date IS NULL
        WHERE cg.is_active = 1 AND (cg.teacher_id = ? OR ct.id IS NOT NULL)
        """,
        (teacher_id, teacher_id),
    ).fetchone()[0]


def class_has_enrollments(conn: sqlite3.Connection, class_id: int) -> bool:
    _require_row(conn, "class_group", class_id)
    row = conn.execute(
        "SELECT 1 FROM enrollment_class WHERE class_id = ? LIMIT 1", (class_id,)
    ).fetchone()
    return row is not None


def delete_class(conn: sqlite3.Connection, class_id: int) -> None:
    """Only for classes NO student was ever enrolled in — the 'created by
    mistake' case. Anything with history archives instead."""
    with _transaction(conn):
        conn.execute("DELETE FROM class_teacher WHERE class_id = ?", (class_id,))
        conn.execute("DELETE FROM class_group WHERE id = ?", (class_id,))


def archive_class_with_refunds(
    conn: sqlite3.Connection,
    academy_id: int,
    class_id: int,
    date: str,
    refunds: list[dict],
    current_month: str,
) -> list[int]:
    """No teacher was found: the class dies. From the current month on,
    paid students keep their history and get a pending refund (their chosen
    percentage of the class's slice of what they ACTUALLY paid); unpaid
    students simply lose the class — an impayé gets no money back."""
    from datetime import date as date_type
    from datetime import timedelta

    _require_row(conn, "class_group", class_id)
    percent_by_enrollment = {r["enrollment_id"]: r["percent_bp"] for r in refunds}
    day_before = str(date_type.fromisoformat(date) - timedelta(days=1))
    refund_ids: list[int] = []
    with _transaction(conn):
        conn.execute(
            "UPDATE class_teacher SET to_date = ? WHERE class_id = ?"
            " AND to_date IS NULL",
            (day_before, class_id),
        )
        conn.execute("UPDATE class_group SET is_active = 0 WHERE id = ?", (class_id,))
        affected = conn.execute(
            """
            SELECT e.id, e.student_id,
                   (SELECT p.id FROM payment p WHERE p.enrollment_id = e.id
                      AND p.reversed_at IS NULL) AS payment_id,
                   EXISTS(SELECT 1 FROM payment p2
                          WHERE p2.enrollment_id = e.id) AS has_history,
                   e.month
            FROM enrollment e
            JOIN enrollment_class ec ON ec.enrollment_id = e.id
            WHERE ec.class_id = ? AND e.month >= ?
            """,
            (class_id, current_month),
        ).fetchall()
        for enrollment in affected:
            if enrollment["payment_id"] is not None:
                refund_id = _create_refund(
                    conn,
                    academy_id,
                    enrollment,
                    class_id,
                    percent_by_enrollment.get(enrollment["id"], 0),
                )
                if refund_id is not None:
                    refund_ids.append(refund_id)
            else:
                _drop_class_from_enrollment(conn, enrollment, class_id)
    return refund_ids


def _drop_class_from_enrollment(
    conn: sqlite3.Connection, enrollment: sqlite3.Row, class_id: int
) -> None:
    conn.execute(
        "DELETE FROM enrollment_class WHERE enrollment_id = ? AND class_id = ?",
        (enrollment["id"], class_id),
    )
    remaining = enrollment_class_ids(conn, enrollment["id"])
    if not remaining and not enrollment["has_history"]:
        # His only class died before any money moved: fully un-enrolled.
        conn.execute(
            "DELETE FROM adjustment_bearer WHERE adjustment_id IN"
            " (SELECT id FROM adjustment WHERE enrollment_id = ?)",
            (enrollment["id"],),
        )
        conn.execute(
            "DELETE FROM adjustment WHERE enrollment_id = ?", (enrollment["id"],)
        )
        conn.execute("DELETE FROM enrollment WHERE id = ?", (enrollment["id"],))
    elif remaining:
        _refit_package(conn, enrollment["id"], len(remaining))


def _refit_package(
    conn: sqlite3.Connection, enrollment_id: int, subject_count: int
) -> None:
    """An unpaid enrollment that lost a class re-prices from the matching
    package (same niveau, right subject count) when one exists — the student
    must not silently keep paying for a matière that no longer exists."""
    row = conn.execute(
        """
        SELECT pk.id, pk.monthly_price_centimes FROM package pk
        JOIN enrollment e ON e.id = ?
        JOIN student s ON s.id = e.student_id
        WHERE pk.academy_id = s.academy_id AND pk.is_active = 1
          AND pk.subject_count = ?
          AND (pk.level_id IS NULL OR pk.level_id = s.level_id)
        ORDER BY pk.level_id IS NULL, pk.id
        LIMIT 1
        """,
        (enrollment_id, subject_count),
    ).fetchone()
    if row is not None:
        conn.execute(
            "UPDATE enrollment SET package_id = ?, price_centimes = ? WHERE id = ?",
            (row["id"], row["monthly_price_centimes"], enrollment_id),
        )


def _create_refund(
    conn: sqlite3.Connection,
    academy_id: int,
    enrollment: sqlite3.Row,
    class_id: int,
    percent_bp: int,
) -> int | None:
    """percent_bp of the class's equal-split slice of the cash actually
    received (net of reductions, partial if an avance) — never of the list
    price. 0% or a zero slice creates nothing."""
    if percent_bp <= 0:
        return None
    cash = conn.execute(
        "SELECT COALESCE(SUM(amount_centimes), 0) FROM ledger_entry"
        " WHERE payment_id = ? AND entry_type = 'payment_in'",
        (enrollment["payment_id"],),
    ).fetchone()[0]
    class_ids = enrollment_class_ids(conn, enrollment["id"])
    slices = split_equally(cash, len(class_ids))
    amount = percent_of(slices[class_ids.index(class_id)], percent_bp)
    if amount <= 0:
        return None
    return conn.execute(
        "INSERT INTO refund (academy_id, enrollment_id, class_id, student_id,"
        " month, percent_bp, amount_centimes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            academy_id,
            enrollment["id"],
            class_id,
            enrollment["student_id"],
            enrollment["month"],
            percent_bp,
            amount,
        ),
    ).lastrowid


def list_refunds(conn: sqlite3.Connection, academy_id: int) -> list[dict]:
    return _rows(
        conn,
        """
        SELECT r.*, s.name AS student_name, s.first_name,
               sub.name AS subject_name, sl.name AS level_name
        FROM refund r
        JOIN student s ON s.id = r.student_id
        JOIN class_group cg ON cg.id = r.class_id
        JOIN subject sub ON sub.id = cg.subject_id
        JOIN school_level sl ON sl.id = cg.level_id
        WHERE r.academy_id = ?
        ORDER BY r.status DESC, r.created_at DESC
        """,
        (academy_id,),
    )


def refund_row(conn: sqlite3.Connection, refund_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM refund WHERE id = ?", (refund_id,)).fetchone()
    return dict(row) if row else None


def settle_refund(conn: sqlite3.Connection, refund: dict, ledger_month: str) -> None:
    """The cash leaves the drawer NOW: one refund cash-out line plus clawback
    lines taken proportionally from what this payment's beneficiaries had
    actually received (largest-remainder, so the sum is exact)."""
    payment = conn.execute(
        "SELECT id FROM payment WHERE enrollment_id = ? AND reversed_at IS NULL",
        (refund["enrollment_id"],),
    ).fetchone()
    if payment is None:
        raise LookupError(f"no live payment for enrollment {refund['enrollment_id']}")
    received = conn.execute(
        """
        SELECT beneficiary_kind, beneficiary_id, SUM(amount_centimes) AS total
        FROM ledger_entry
        WHERE payment_id = ? AND entry_type IN ('allocation', 'adjustment')
        GROUP BY beneficiary_kind, beneficiary_id
        """,
        (payment["id"],),
    ).fetchall()
    weights = tuple((index, max(row["total"], 0)) for index, row in enumerate(received))
    if sum(weight for _, weight in weights) <= 0:
        raise ValueError("ce paiement n'a rien distribué — rien à reprendre")
    parts = _proportional_parts(weights, refund["amount_centimes"])
    note = f"Remboursement — élève {refund['student_id']}"
    with _transaction(conn):
        conn.execute(
            "INSERT INTO ledger_entry (academy_id, month, entry_type,"
            " amount_centimes, payment_id, note) VALUES (?, ?, 'refund', ?, ?, ?)",
            (
                refund["academy_id"],
                ledger_month,
                -refund["amount_centimes"],
                payment["id"],
                note,
            ),
        )
        conn.executemany(
            "INSERT INTO ledger_entry (academy_id, month, entry_type,"
            " beneficiary_kind, beneficiary_id, amount_centimes, payment_id,"
            " note) VALUES (?, ?, 'refund', ?, ?, ?, ?, ?)",
            [
                (
                    refund["academy_id"],
                    ledger_month,
                    received[index]["beneficiary_kind"],
                    received[index]["beneficiary_id"],
                    -part,
                    payment["id"],
                    note,
                )
                for index, part in parts
                if part != 0
            ],
        )
        conn.execute(
            "UPDATE refund SET status = 'settled', settled_at = datetime('now')"
            " WHERE id = ?",
            (refund["id"],),
        )


def duplicate_class(
    conn: sqlite3.Connection, class_id: int, teacher_id: int | None
) -> int:
    """« Dédoubler » : a second group of the same class — next letter, chosen
    teacher (or the same one) — for when one group overflows."""
    row = conn.execute("SELECT * FROM class_group WHERE id = ?", (class_id,)).fetchone()
    if row is None:
        raise LookupError(f"no class_group {class_id}")
    siblings = conn.execute(
        "SELECT name FROM class_group WHERE academy_id = ? AND level_id = ?"
        " AND subject_id = ? AND annee IS ? AND parcours IS ? AND is_active = 1",
        (
            row["academy_id"],
            row["level_id"],
            row["subject_id"],
            row["annee"],
            row["parcours"],
        ),
    ).fetchall()
    next_name = chr(max(ord(s["name"][:1] or "A") for s in siblings) + 1)
    return create_class(
        conn,
        row["academy_id"],
        {
            "level_id": row["level_id"],
            "subject_id": row["subject_id"],
            "teacher_id": teacher_id or row["teacher_id"],
            "name": next_name,
            "annee": row["annee"],
            "filiere": row["filiere"],
            "parcours": row["parcours"],
            "day_of_week": row["day_of_week"],
            "start_time": row["start_time"],
        },
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
        {"subject_count", "monthly_price_centimes", "level_id", "is_active", "label"},
    )


def create_package(
    conn: sqlite3.Connection,
    academy_id: int,
    subject_count: int,
    price: int,
    level_id: int | None = None,
    label: str | None = None,
) -> int:
    return _insert(
        conn,
        "INSERT INTO package (academy_id, subject_count, monthly_price_centimes,"
        " level_id, label) VALUES (?, ?, ?, ?, ?)",
        (academy_id, subject_count, price, level_id, label),
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
        SELECT s.*, sl.name AS level_name, sc.name AS school_name,
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
          ) AS month_paid,
          -- An avance is NOT « Payé » : what the month still owes, so the
          -- listing can say « Avance · reste X » honestly.
          COALESCE((SELECT MAX(COALESCE(p5.due_centimes, p5.amount_centimes)
              - (SELECT COALESCE(SUM(le.amount_centimes), 0) FROM ledger_entry le
                 WHERE le.payment_id = p5.id AND le.entry_type = 'payment_in'), 0)
           FROM enrollment e5
           JOIN payment p5 ON p5.enrollment_id = e5.id AND p5.reversed_at IS NULL
           WHERE e5.student_id = s.id AND e5.month = ?
          ), 0) AS month_remaining_centimes,
          EXISTS(SELECT 1 FROM enrollment e4 WHERE e4.student_id = s.id
          ) AS ever_enrolled
        FROM student s
        JOIN school_level sl ON sl.id = s.level_id
        LEFT JOIN school sc ON sc.id = s.school_id
        WHERE s.academy_id = ?{active_filter} ORDER BY s.name
        """,
        (month or "", month or "", month or "", month or "", academy_id),
    )


def create_student(conn: sqlite3.Connection, academy_id: int, fields: dict) -> int:
    with _transaction(conn):
        student_id = conn.execute(
            "INSERT INTO student (academy_id, level_id, name, first_name, annee,"
            " filiere, parcours, school_id, phone, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (
                academy_id,
                fields["level_id"],
                fields["name"],
                fields.get("first_name"),
                fields.get("annee"),
                fields.get("filiere"),
                fields.get("parcours"),
                fields.get("school_id"),
                fields.get("phone"),
            ),
        ).lastrowid
        _replace_phones(conn, student_id, fields.get("phones", []))
        return student_id


def update_student(conn: sqlite3.Connection, student_id: int, fields: dict) -> None:
    phones = fields.pop("phones", None)
    allowed = {
        "name",
        "first_name",
        "level_id",
        "annee",
        "filiere",
        "parcours",
        "school_id",
        "phone",
        "is_active",
    }
    changes = {key: value for key, value in fields.items() if key in allowed}
    with _transaction(conn):
        if changes:
            assignments = ", ".join(f"{column} = ?" for column in changes)
            updated = conn.execute(
                f"UPDATE student SET {assignments} WHERE id = ?",
                (*changes.values(), student_id),
            )
            if updated.rowcount == 0:
                raise LookupError(f"no student {student_id}")
        if phones is not None:
            _replace_phones(conn, student_id, phones)


def _replace_phones(
    conn: sqlite3.Connection, student_id: int, phones: list[dict]
) -> None:
    conn.execute("DELETE FROM student_phone WHERE student_id = ?", (student_id,))
    conn.executemany(
        "INSERT INTO student_phone (student_id, tag, number) VALUES (?, ?, ?)",
        [(student_id, phone["tag"], phone["number"]) for phone in phones],
    )


def student_phones(conn: sqlite3.Connection, student_id: int) -> list[dict]:
    return _rows(
        conn,
        "SELECT tag, number FROM student_phone WHERE student_id = ? ORDER BY id",
        (student_id,),
    )


def get_or_create_school(conn: sqlite3.Connection, academy_id: int, name: str) -> int:
    row = conn.execute(
        "SELECT id FROM school WHERE academy_id = ? AND name = ?", (academy_id, name)
    ).fetchone()
    if row is not None:
        return row["id"]
    return _insert(
        conn, "INSERT INTO school (academy_id, name) VALUES (?, ?)", (academy_id, name)
    )


def list_filieres(conn: sqlite3.Connection, academy_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT filiere FROM student WHERE academy_id = ?"
        " AND filiere IS NOT NULL AND filiere != '' ORDER BY filiere",
        (academy_id,),
    ).fetchall()
    return [row["filiere"] for row in rows]


def list_schools(conn: sqlite3.Connection, academy_id: int) -> list[dict]:
    return _rows(
        conn,
        "SELECT * FROM school WHERE academy_id = ? AND is_active = 1 ORDER BY name",
        (academy_id,),
    )


def student_profile(conn: sqlite3.Connection, student_id: int) -> dict | None:
    """Everything about one student: identity, tagged phones, and the full
    month-by-month history — packs, matières, net, paid state. Works for
    archived students too: history is never hidden."""
    row = conn.execute(
        """
        SELECT s.*, sl.name AS level_name, sc.name AS school_name
        FROM student s
        JOIN school_level sl ON sl.id = s.level_id
        LEFT JOIN school sc ON sc.id = s.school_id
        WHERE s.id = ?
        """,
        (student_id,),
    ).fetchone()
    if row is None:
        return None
    store = SqlitePaymentStore(conn)
    months = [
        {
            "month": enrollment["month"],
            "enrollment_id": enrollment["id"],
            "price_centimes": enrollment["price_centimes"],
            "net_centimes": safe_net(
                store, enrollment["id"], enrollment["price_centimes"]
            ),
            "paid": enrollment["payment_id"] is not None,
            "paid_on": enrollment["paid_on"],
            "payment_id": enrollment["payment_id"],
            "remaining_centimes": payment_remaining(conn, enrollment["payment_id"]),
            "arrival_date": enrollment["arrival_date"],
            "subject_count": enrollment["subject_count"],
            "subjects": [
                c["subject_name"] for c in _enrollment_classes(conn, enrollment["id"])
            ],
        }
        for enrollment in _rows(
            conn,
            """
            SELECT e.*, pk.subject_count, p.id AS payment_id, p.paid_on
            FROM enrollment e
            JOIN package pk ON pk.id = e.package_id
            LEFT JOIN payment p ON p.enrollment_id = e.id AND p.reversed_at IS NULL
            WHERE e.student_id = ?
            ORDER BY e.month DESC
            """,
            (student_id,),
        )
    ]
    return {
        **dict(row),
        "phones": student_phones(conn, student_id),
        "months": months,
    }


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
            " category, reason, recurring) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                enrollment_id,
                fields.get("scope", "package"),
                fields.get("class_id"),
                fields["kind"],
                fields["value"],
                fields.get("category", "discount"),
                fields.get("reason"),
                int(bool(fields.get("recurring", False))),
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
    allowed = {"kind", "value", "scope", "class_id", "category", "reason", "recurring"}
    changes = {
        key: int(value) if key == "recurring" else value
        for key, value in fields.items()
        if key in allowed
    }
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


def teacher_profile(
    conn: sqlite3.Connection, teacher_id: int, month: str
) -> dict | None:
    """One teacher, whole story: identity, capabilities, every class with its
    student count and what the month actually paid them, plus history."""
    teacher = conn.execute(
        "SELECT * FROM teacher WHERE id = ?", (teacher_id,)
    ).fetchone()
    if teacher is None:
        return None
    classes = _rows(
        conn,
        """
        SELECT DISTINCT cg.id, cg.name, cg.annee, cg.filiere, cg.parcours,
               cg.is_active, cg.teacher_id, cg.subject_id, cg.level_id,
               sub.name AS subject_name, sl.name AS level_name,
          (SELECT COUNT(*) FROM enrollment_class ec
           JOIN enrollment e ON e.id = ec.enrollment_id
           JOIN student st ON st.id = e.student_id
           WHERE ec.class_id = cg.id AND e.month = ? AND st.is_active = 1
          ) AS enrolled_count
        FROM class_group cg
        JOIN subject sub ON sub.id = cg.subject_id
        JOIN school_level sl ON sl.id = cg.level_id
        WHERE cg.id IN (SELECT class_id FROM class_teacher WHERE teacher_id = ?)
           OR cg.teacher_id = ?
        ORDER BY sl.sort_order, sub.name, cg.name
        """,
        (month, teacher_id, teacher_id),
    )
    earnings = _teacher_class_earnings(
        conn, teacher_id, month, [c["id"] for c in classes]
    )
    for entry in classes:
        entry["earned_centimes"] = earnings.get(entry["id"], 0)
    return {
        **dict(teacher),
        # The owner-professor sees BOTH hats: what the month paid him as a
        # teacher (history/classes) and as the academy owner.
        "owner_earned": (
            _owner_month_total(conn, teacher["academy_id"], month)
            if teacher["is_owner"]
            else 0
        ),
        "capabilities": _rows(
            conn,
            """
            SELECT tc.*, sub.name AS subject_name, sl.name AS level_name
            FROM teacher_capability tc
            JOIN subject sub ON sub.id = tc.subject_id
            JOIN school_level sl ON sl.id = tc.level_id
            WHERE tc.teacher_id = ?
            """,
            (teacher_id,),
        ),
        "classes": classes,
        "history": [
            {"month": past, "earned": _teacher_month_total(conn, teacher_id, past)}
            for past in _months_back(month, 6)
        ],
        "assignments": _rows(
            conn,
            """
            SELECT ct.from_date, ct.to_date, sub.name AS subject_name,
                   cg.name AS group_name, sl.name AS level_name
            FROM class_teacher ct
            JOIN class_group cg ON cg.id = ct.class_id
            JOIN subject sub ON sub.id = cg.subject_id
            JOIN school_level sl ON sl.id = cg.level_id
            WHERE ct.teacher_id = ?
            ORDER BY ct.id
            """,
            (teacher_id,),
        ),
    }


def _teacher_class_earnings(
    conn: sqlite3.Connection, teacher_id: int, month: str, class_ids: list[int]
) -> dict[int, int]:
    """Attribute the teacher's ledger lines to his classes: each payment's
    line is split across the classes he taught within that enrollment."""
    earnings = dict.fromkeys(class_ids, 0)
    lines = conn.execute(
        """
        SELECT le.amount_centimes, p.enrollment_id
        FROM ledger_entry le
        JOIN payment p ON p.id = le.payment_id
        WHERE le.beneficiary_kind = 'teacher' AND le.beneficiary_id = ?
          AND le.month = ?
        """,
        (teacher_id, month),
    ).fetchall()
    for line in lines:
        mine = sorted(
            class_id
            for class_id in enrollment_class_ids(conn, line["enrollment_id"])
            if class_id in earnings
        )
        if not mine:
            continue
        share, remainder = divmod(line["amount_centimes"], len(mine))
        for index, class_id in enumerate(mine):
            earnings[class_id] += share + (remainder if index == 0 else 0)
    return earnings


def _owner_month_total(conn: sqlite3.Connection, academy_id: int, month: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_centimes), 0) FROM ledger_entry"
        " WHERE beneficiary_kind = 'owner' AND beneficiary_id = ? AND month = ?",
        (academy_id, month),
    ).fetchone()
    return row[0]


def _teacher_month_total(conn: sqlite3.Connection, teacher_id: int, month: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_centimes), 0) FROM ledger_entry"
        " WHERE beneficiary_kind = 'teacher' AND beneficiary_id = ?"
        " AND month = ?",
        (teacher_id, month),
    ).fetchone()
    return row[0]


def _months_back(month: str, count: int) -> list[str]:
    year, month_number = int(month[:4]), int(month[5:7])
    total = year * 12 + (month_number - 1)
    return [
        f"{(total - offset) // 12:04d}-{(total - offset) % 12 + 1:02d}"
        for offset in range(count - 1, -1, -1)
    ]


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
               s.annee, s.parcours, s.filiere, sl.name AS level_name,
               e.id AS enrollment_id, e.price_centimes, e.arrival_date,
               e.stopped, p.id AS payment_id,
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


def stop_enrollment(conn: sqlite3.Connection, enrollment_id: int) -> None:
    """« Il a arrêté » : keep the month's history, but don't carry him into
    the next one."""
    with _transaction(conn):
        conn.execute("UPDATE enrollment SET stopped = 1 WHERE id = ?", (enrollment_id,))


def guarantee_row(conn: sqlite3.Connection, enrollment_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM guarantee WHERE enrollment_id = ?", (enrollment_id,)
    ).fetchone()
    return dict(row) if row else None


def payout_summary(conn: sqlite3.Connection, academy_id: int, month: str) -> list[dict]:
    """The end-of-month payout sheet. What a professor is DUE comes from the
    students ENROLLED with him — he taught them whether or not they paid —
    not from what the académie managed to collect. Next to it: what he was
    actually HANDED (teacher_payout, deliberately outside the ledger, since
    paying someone must never change what he earned) and what is left."""
    dues = _teacher_dues(conn, academy_id, month)
    teachers = _rows(
        conn,
        """
        SELECT t.id AS teacher_id, t.name AS teacher_name, t.is_owner,
          COALESCE((SELECT SUM(le.amount_centimes) FROM ledger_entry le
                    WHERE le.beneficiary_kind = 'teacher'
                      AND le.beneficiary_id = t.id AND le.month = ?), 0)
              AS collected_centimes,
          COALESCE((SELECT SUM(p.amount_centimes) FROM payout p
                    WHERE p.beneficiary_kind = 'teacher'
                      AND p.beneficiary_id = t.id AND p.month = ?), 0)
              AS paid_centimes
        FROM teacher t WHERE t.academy_id = ? AND t.is_active = 1
        ORDER BY t.name
        """,
        (month, month, academy_id),
    )
    for teacher in teachers:
        teacher["due_centimes"] = dues.get(teacher["teacher_id"], 0)
        teacher["remaining_centimes"] = max(
            teacher["due_centimes"] - teacher["paid_centimes"], 0
        )
        teacher["payouts"] = _rows(
            conn,
            "SELECT id, amount_centimes, paid_on, note FROM payout"
            " WHERE beneficiary_kind = 'teacher' AND beneficiary_id = ?"
            " AND month = ? ORDER BY id",
            (teacher["teacher_id"], month),
        )
    return teachers


def _teacher_dues(
    conn: sqlite3.Connection, academy_id: int, month: str
) -> dict[int, int]:
    """Per professor, his share of every enrollment of the month.

    A settled impayé is the owner's explicit decision about what was taught:
    « jamais venu » owes nothing, « présent 15 jours » owes those days. Once
    the student pays, the full month was bought and the full share is due
    again. Everything else — paid or not — counts in full."""
    store = SqlitePaymentStore(conn)
    dues: dict[int, int] = {}
    rows = conn.execute(
        """
        SELECT e.id,
               EXISTS(SELECT 1 FROM guarantee g WHERE g.enrollment_id = e.id)
                   AS guaranteed,
               EXISTS(SELECT 1 FROM payment p WHERE p.enrollment_id = e.id
                      AND p.reversed_at IS NULL) AS paid
        FROM enrollment e JOIN student s ON s.id = e.student_id
        WHERE s.academy_id = ? AND e.month = ?
        """,
        (academy_id, month),
    ).fetchall()
    for row in rows:
        shares = (
            store.guaranteed_shares(row["id"])
            if row["guaranteed"] and not row["paid"]
            else _enrollment_teacher_shares(conn, store, row["id"])
        )
        for teacher_id, amount in shares:
            dues[teacher_id] = dues.get(teacher_id, 0) + amount
    return dues


def _enrollment_teacher_shares(
    conn: sqlite3.Connection, store: SqlitePaymentStore, enrollment_id: int
) -> tuple[tuple[int, int], ...]:
    from app.services.payments import payment_preview

    try:
        preview = payment_preview(store, enrollment_id)
    except ValueError:
        return ()  # une ligne invalide ne doit pas casser la feuille de paie
    return tuple(
        (line.beneficiary.ref_id, line.final)
        for line in preview.lines
        if line.beneficiary.kind == "teacher" and line.final > 0
    )


def caisse_summary(conn: sqlite3.Connection, academy_id: int, month: str) -> dict:
    """L'argent réel du mois. Ce qui est entré (élèves), ce qui est sorti
    (versements à qui que ce soit), et ce qui reste dans la caisse.

    Le dû de chacun suit la règle du client :
      professeur — sur les élèves INSCRITS, payés ou non ;
      salle      — uniquement sur l'argent réellement encaissé ;
      académie   — ce qui reste, donc elle absorbe tout le manque.
    """
    from app.adapters.sqlite.reports import _cash_in

    collected = _cash_in(conn, academy_id, month)
    dues = _teacher_dues(conn, academy_id, month)
    venue = _venue(conn, academy_id)
    venue_due = conn.execute(
        "SELECT COALESCE(SUM(amount_centimes), 0) FROM ledger_entry"
        " WHERE academy_id = ? AND month = ? AND beneficiary_kind = 'venue'",
        (academy_id, month),
    ).fetchone()[0]
    owner_due = collected - sum(dues.values()) - venue_due

    lines = [
        _caisse_line(conn, academy_id, month, "venue", venue["id"], venue["name"])
        if venue
        else None,
        _caisse_line(
            conn,
            academy_id,
            month,
            "owner",
            academy_id,
            conn.execute(
                "SELECT name FROM academy WHERE id = ?", (academy_id,)
            ).fetchone()["name"],
        ),
    ]
    lines = [entry for entry in lines if entry is not None]
    if venue:
        lines[0]["due_centimes"] = venue_due
        lines[0]["remaining_centimes"] = max(venue_due - lines[0]["paid_centimes"], 0)
    owner_line = lines[-1]
    owner_line["due_centimes"] = owner_due
    owner_line["remaining_centimes"] = max(owner_due - owner_line["paid_centimes"], 0)

    # Un professeur archivé en cours de mois doit quand même être payé pour
    # ce qu'il a enseigné : on liste les actifs ET tous ceux à qui il reste
    # quelque chose — sinon la somme des lignes ne ferait pas la caisse.
    for teacher in _rows(
        conn,
        """
        SELECT t.id, t.name, t.is_owner FROM teacher t
        WHERE t.academy_id = ? AND (
            t.is_active = 1
            OR EXISTS (SELECT 1 FROM payout p WHERE p.beneficiary_kind = 'teacher'
                       AND p.beneficiary_id = t.id AND p.month = ?)
            OR EXISTS (SELECT 1 FROM ledger_entry le
                       WHERE le.beneficiary_kind = 'teacher'
                         AND le.beneficiary_id = t.id AND le.month = ?)
        )
        ORDER BY t.name
        """,
        (academy_id, month, month),
    ):
        entry = _caisse_line(
            conn, academy_id, month, "teacher", teacher["id"], teacher["name"]
        )
        entry["is_owner"] = teacher["is_owner"]
        entry["due_centimes"] = dues.get(teacher["id"], 0)
        entry["remaining_centimes"] = max(
            entry["due_centimes"] - entry["paid_centimes"], 0
        )
        lines.append(entry)

    paid_out = conn.execute(
        "SELECT COALESCE(SUM(amount_centimes), 0) FROM payout"
        " WHERE academy_id = ? AND month = ?",
        (academy_id, month),
    ).fetchone()[0]
    unpaid, projection = _unpaid_projection(conn, academy_id, month)
    return {
        "month": month,
        "collected_centimes": collected,
        "paid_out_centimes": paid_out,
        "balance_centimes": collected - paid_out,
        "unpaid_centimes": unpaid,
        "projection": projection,
        "lines": lines,
    }


def _caisse_line(
    conn: sqlite3.Connection,
    academy_id: int,
    month: str,
    kind: str,
    ref_id: int,
    name: str,
) -> dict:
    payouts = _rows(
        conn,
        "SELECT id, amount_centimes, paid_on, note FROM payout"
        " WHERE academy_id = ? AND month = ? AND beneficiary_kind = ?"
        " AND beneficiary_id = ? ORDER BY id",
        (academy_id, month, kind, ref_id),
    )
    return {
        "kind": kind,
        "ref_id": ref_id,
        "name": name,
        "is_owner": 0,
        "due_centimes": 0,
        "paid_centimes": sum(payout["amount_centimes"] for payout in payouts),
        "remaining_centimes": 0,
        "payouts": payouts,
    }


def _unpaid_projection(
    conn: sqlite3.Connection, academy_id: int, month: str
) -> tuple[int, dict]:
    """Ce que les impayés du mois rapporteront encore : la salle prendra son
    pourcentage, et TOUT le reste ira à l'académie — elle a déjà payé les
    professeurs pour ces élèves-là."""
    store = SqlitePaymentStore(conn)
    rows = conn.execute(
        """
        SELECT e.id FROM enrollment e JOIN student s ON s.id = e.student_id
        WHERE s.academy_id = ? AND e.month = ?
          AND NOT EXISTS (SELECT 1 FROM payment p WHERE p.enrollment_id = e.id
                          AND p.reversed_at IS NULL)
        """,
        (academy_id, month),
    ).fetchall()
    unpaid = 0
    venue_share = 0
    for row in rows:
        try:
            preview = payment_preview(store, row["id"])
        except ValueError:
            continue
        unpaid += preview.net
        venue_share += sum(
            entry.final for entry in preview.lines if entry.beneficiary.kind == "venue"
        )
    return unpaid, {
        "venue_centimes": venue_share,
        "owner_centimes": unpaid - venue_share,
    }


def beneficiary_remaining(
    conn: sqlite3.Connection, academy_id: int, kind: str, ref_id: int, month: str
) -> int:
    summary = caisse_summary(conn, academy_id, month)
    row = next(
        (
            entry
            for entry in summary["lines"]
            if entry["kind"] == kind and entry["ref_id"] == ref_id
        ),
        None,
    )
    if row is None:
        raise LookupError(f"no {kind} {ref_id}")
    return row["remaining_centimes"]


def teacher_remaining(
    conn: sqlite3.Connection, academy_id: int, teacher_id: int, month: str
) -> int:
    return beneficiary_remaining(conn, academy_id, "teacher", teacher_id, month)


def add_payout(
    conn: sqlite3.Connection,
    academy_id: int,
    kind: str,
    ref_id: int,
    month: str,
    amount: int,
    note: str | None = None,
) -> int:
    return _insert(
        conn,
        "INSERT INTO payout (academy_id, beneficiary_kind, beneficiary_id,"
        " month, amount_centimes, note) VALUES (?, ?, ?, ?, ?, ?)",
        (academy_id, kind, ref_id, month, amount, note),
    )


def delete_payout(conn: sqlite3.Connection, payout_id: int) -> None:
    with _transaction(conn):
        conn.execute("DELETE FROM payout WHERE id = ?", (payout_id,))


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


def _copy_recurring_adjustments(
    conn: sqlite3.Connection, from_enrollment: int, to_enrollment: int
) -> None:
    """A recurring reduction/gift follows the enrollment into the new month —
    as its OWN copy, editable or removable there without touching the past."""
    rows = conn.execute(
        "SELECT * FROM adjustment WHERE enrollment_id = ? AND is_active = 1"
        " AND recurring = 1",
        (from_enrollment,),
    ).fetchall()
    for row in rows:
        new_id = conn.execute(
            "INSERT INTO adjustment (enrollment_id, scope, class_id, kind, value,"
            " category, reason, recurring) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            (
                to_enrollment,
                row["scope"],
                row["class_id"],
                row["kind"],
                row["value"],
                row["category"],
                row["reason"],
            ),
        ).lastrowid
        conn.execute(
            "INSERT INTO adjustment_bearer (adjustment_id, bearer_kind, bearer_id,"
            " share_centimes, share_bp)"
            " SELECT ?, bearer_kind, bearer_id, share_centimes, share_bp"
            " FROM adjustment_bearer WHERE adjustment_id = ?",
            (new_id, row["id"]),
        )


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
          AND e.stopped = 0
          AND NOT EXISTS (
            SELECT 1 FROM enrollment t
            WHERE t.student_id = e.student_id AND t.month = ?
          )
        """,
        (academy_id, from_month, to_month),
    )
    copied = 0
    with _transaction(conn):
        for enrollment in source:
            # Archived classes stay in the past: they are not extended. An
            # enrollment whose every class died is not extended at all.
            class_ids = _active_class_ids(
                conn, enrollment_class_ids(conn, enrollment["id"])
            )
            if not class_ids:
                continue
            # A prorated first month is a one-off concession: the extension
            # re-prices from the package. Manual overrides carry over.
            price = (
                enrollment["package_price"]
                if enrollment["arrival_date"] is not None
                else enrollment["price_centimes"]
            )
            new_id = _insert_enrollment(
                conn,
                enrollment["student_id"],
                to_month,
                enrollment["package_id"],
                class_ids,
                price,
            )
            _copy_recurring_adjustments(conn, enrollment["id"], new_id)
            copied += 1
    return copied


def _active_class_ids(conn: sqlite3.Connection, class_ids: list[int]) -> list[int]:
    if not class_ids:
        return []
    placeholders = ", ".join("?" for _ in class_ids)
    rows = conn.execute(
        f"SELECT id FROM class_group WHERE id IN ({placeholders})"
        " AND is_active = 1 ORDER BY id",
        class_ids,
    )
    return [row["id"] for row in rows]


def _overview_row(conn, store, row) -> dict:
    base = {
        "student_id": row["student_id"],
        "student_name": row["student_name"],
        "level_id": row["level_id"],
        "level_name": row["level_name"],
        "annee": row["annee"],
        "parcours": row["parcours"],
        "filiere": row["filiere"],
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
            "remaining_centimes": payment_remaining(conn, row["payment_id"]),
            # Impayé mais professeur déjà payé par l'académie.
            "guaranteed_centimes": _guaranteed_total(conn, row["enrollment_id"]),
            "stopped": bool(row["stopped"]),
            "classes": _enrollment_classes(conn, row["enrollment_id"]),
            "split": _row_split(conn, store, row["enrollment_id"]),
        },
    }


def _guaranteed_total(conn: sqlite3.Connection, enrollment_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_centimes), 0) FROM ledger_entry"
        " WHERE enrollment_id = ? AND entry_type = 'guarantee'"
        " AND beneficiary_kind = 'teacher'",
        (enrollment_id,),
    ).fetchone()
    return row[0]


def payment_remaining(conn: sqlite3.Connection, payment_id: int | None) -> int:
    """What an avance still owes: due minus every payment_in posted so far.
    0 for a complete payment; 0 too when nothing was paid (that is an
    impayé, not an avance)."""
    if payment_id is None:
        return 0
    row = conn.execute(
        "SELECT COALESCE(due_centimes, amount_centimes) AS due,"
        " (SELECT COALESCE(SUM(amount_centimes), 0) FROM ledger_entry"
        "  WHERE payment_id = payment.id AND entry_type = 'payment_in') AS cash"
        " FROM payment WHERE id = ?",
        (payment_id,),
    ).fetchone()
    if row is None:
        return 0
    return max(row["due"] - row["cash"], 0)


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
        LEFT JOIN teacher t ON t.id = cg.teacher_id
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
