"""Read side (CQRS): reports are sums over ledger entries, never recomputed money.

No mutation here — these queries feed the dashboard, the monthly payout
sheet, and the arrears list.
"""

import sqlite3
from dataclasses import dataclass

from app.adapters.sqlite.payment_store import SqlitePaymentStore
from app.domain.money import Centimes
from app.services.payments import net_price


@dataclass(frozen=True)
class BeneficiaryTotal:
    kind: str  # 'venue' | 'owner' | 'teacher'
    ref_id: int
    name: str
    total: Centimes


@dataclass(frozen=True)
class LevelBreakdown:
    level_id: int
    level_name: str
    totals: tuple[BeneficiaryTotal, ...]


@dataclass(frozen=True)
class MonthlyReport:
    academy_id: int
    month: str
    cash_in: Centimes
    totals: tuple[BeneficiaryTotal, ...]
    by_level: tuple[LevelBreakdown, ...]
    # When the month's ledger last moved — lets the UI warn that an Excel
    # exported before this moment is stale.
    last_entry_at: str | None = None


@dataclass(frozen=True)
class ArrearsItem:
    enrollment_id: int
    month: str
    owed: Centimes


@dataclass(frozen=True)
class StudentArrears:
    student_id: int
    student_name: str
    level_name: str
    items: tuple[ArrearsItem, ...]
    total_owed: Centimes


def monthly_report(
    conn: sqlite3.Connection, academy_id: int, month: str
) -> MonthlyReport:
    return MonthlyReport(
        academy_id=academy_id,
        month=month,
        cash_in=_cash_in(conn, academy_id, month),
        totals=_academy_totals(conn, academy_id, month),
        by_level=_level_breakdowns(conn, academy_id, month),
        last_entry_at=_last_entry_at(conn, academy_id, month),
    )


def _last_entry_at(conn: sqlite3.Connection, academy_id: int, month: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(created_at) FROM ledger_entry WHERE academy_id = ? AND month = ?",
        (academy_id, month),
    ).fetchone()
    return row[0]


def arrears(
    conn: sqlite3.Connection, academy_id: int, up_to_month: str
) -> tuple[StudentArrears, ...]:
    store = SqlitePaymentStore(conn)
    grouped: dict[int, list[sqlite3.Row]] = {}
    for row in _unpaid_enrollments(conn, academy_id, up_to_month):
        grouped.setdefault(row["student_id"], []).append(row)
    return tuple(_student_arrears(store, rows) for rows in grouped.values())


def _cash_in(conn: sqlite3.Connection, academy_id: int, month: str) -> Centimes:
    # Cash lines have no beneficiary: payment_in plus its reversal mirrors,
    # so a reversed month nets back to zero here too.
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_centimes), 0) FROM ledger_entry"
        " WHERE academy_id = ? AND month = ? AND beneficiary_kind IS NULL"
        " AND entry_type IN ('payment_in', 'reversal')",
        (academy_id, month),
    ).fetchone()
    return row[0]


def _academy_totals(
    conn: sqlite3.Connection, academy_id: int, month: str
) -> tuple[BeneficiaryTotal, ...]:
    rows = conn.execute(
        """
        SELECT beneficiary_kind, beneficiary_id, SUM(amount_centimes) AS total
        FROM ledger_entry
        WHERE academy_id = ? AND month = ? AND beneficiary_kind IS NOT NULL
        GROUP BY beneficiary_kind, beneficiary_id
        """,
        (academy_id, month),
    )
    return tuple(_beneficiary_total(conn, row) for row in rows)


def _level_breakdowns(
    conn: sqlite3.Connection, academy_id: int, month: str
) -> tuple[LevelBreakdown, ...]:
    rows = conn.execute(
        """
        SELECT s.level_id, sl.name AS level_name,
               le.beneficiary_kind, le.beneficiary_id,
               SUM(le.amount_centimes) AS total
        FROM ledger_entry le
        JOIN payment p ON p.id = le.payment_id
        JOIN enrollment e ON e.id = p.enrollment_id
        JOIN student s ON s.id = e.student_id
        JOIN school_level sl ON sl.id = s.level_id
        WHERE le.academy_id = ? AND le.month = ? AND le.beneficiary_kind IS NOT NULL
        GROUP BY s.level_id, le.beneficiary_kind, le.beneficiary_id
        ORDER BY sl.sort_order
        """,
        (academy_id, month),
    ).fetchall()
    by_level: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        by_level.setdefault(row["level_id"], []).append(row)
    return tuple(
        LevelBreakdown(
            level_id=level_id,
            level_name=level_rows[0]["level_name"],
            totals=tuple(_beneficiary_total(conn, row) for row in level_rows),
        )
        for level_id, level_rows in by_level.items()
    )


def _beneficiary_total(conn: sqlite3.Connection, row: sqlite3.Row) -> BeneficiaryTotal:
    kind, ref_id = row["beneficiary_kind"], row["beneficiary_id"]
    return BeneficiaryTotal(
        kind=kind,
        ref_id=ref_id,
        name=_beneficiary_name(conn, kind, ref_id),
        total=row["total"],
    )


_NAME_QUERIES = {
    "teacher": "SELECT name FROM teacher WHERE id = ?",
    "venue": "SELECT name FROM venue WHERE id = ?",
    "owner": "SELECT name FROM academy WHERE id = ?",
}


def _beneficiary_name(conn: sqlite3.Connection, kind: str, ref_id: int) -> str:
    row = conn.execute(_NAME_QUERIES[kind], (ref_id,)).fetchone()
    return row["name"] if row else f"{kind} {ref_id}"


def _unpaid_enrollments(
    conn: sqlite3.Connection, academy_id: int, up_to_month: str
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT e.id AS enrollment_id, e.month, e.price_centimes,
               s.id AS student_id, s.name AS student_name, sl.name AS level_name
        FROM enrollment e
        JOIN student s ON s.id = e.student_id
        JOIN school_level sl ON sl.id = s.level_id
        LEFT JOIN payment p
            ON p.enrollment_id = e.id AND p.reversed_at IS NULL
        WHERE s.academy_id = ? AND e.month <= ? AND p.id IS NULL
        ORDER BY s.name, e.month
        """,
        (academy_id, up_to_month),
    ).fetchall()


def _student_arrears(
    store: SqlitePaymentStore, rows: list[sqlite3.Row]
) -> StudentArrears:
    items = tuple(
        ArrearsItem(
            enrollment_id=row["enrollment_id"],
            month=row["month"],
            owed=_safe_owed(store, row),
        )
        for row in rows
    )
    return StudentArrears(
        student_id=rows[0]["student_id"],
        student_name=rows[0]["student_name"],
        level_name=rows[0]["level_name"],
        items=items,
        total_owed=sum(item.owed for item in items),
    )


def history(
    conn: sqlite3.Connection, academy_id: int, up_to_month: str, months: int = 6
) -> list[dict]:
    """Cash-in and paid/unpaid counts for the last N months — feeds the charts."""
    return [
        _month_stats(conn, academy_id, month)
        for month in _month_range(up_to_month, months)
    ]


def _month_range(up_to_month: str, months: int) -> list[str]:
    year, month = int(up_to_month[:4]), int(up_to_month[5:7])
    result = []
    for offset in range(months - 1, -1, -1):
        total = year * 12 + (month - 1) - offset
        result.append(f"{total // 12:04d}-{total % 12 + 1:02d}")
    return result


def _month_stats(conn: sqlite3.Connection, academy_id: int, month: str) -> dict:
    counts = conn.execute(
        """
        SELECT
          COUNT(*) AS enrolled,
          SUM(CASE WHEN p.id IS NOT NULL THEN 1 ELSE 0 END) AS paid
        FROM enrollment e
        JOIN student s ON s.id = e.student_id
        LEFT JOIN payment p ON p.enrollment_id = e.id AND p.reversed_at IS NULL
        WHERE s.academy_id = ? AND e.month = ?
        """,
        (academy_id, month),
    ).fetchone()
    paid = counts["paid"] or 0
    return {
        "month": month,
        "cash_in": _cash_in(conn, academy_id, month),
        "enrolled_count": counts["enrolled"],
        "paid_count": paid,
        "unpaid_count": counts["enrolled"] - paid,
    }


def _safe_owed(store: SqlitePaymentStore, row: sqlite3.Row) -> Centimes:
    # One invalid stored adjustment must not take down the whole arrears list.
    try:
        return net_price(store.enrollment_context(row["enrollment_id"]))
    except ValueError:
        return row["price_centimes"]
