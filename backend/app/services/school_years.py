"""Seasons: defining them, closing them, and reporting on them.

Closing a year erases nothing. Students are archived because we do not
presume they will return -- whoever comes back is re-enrolled as usual
and finds his whole history. What a family owes, by contrast, follows
it: money due does not disappear because the calendar turned.
"""

import sqlite3

from app.domain.school_year import months_between


class SchoolYearError(ValueError):
    pass


def list_years(conn: sqlite3.Connection, academy_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM school_year WHERE academy_id = ? ORDER BY start_month DESC",
        (academy_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def create_year(
    conn: sqlite3.Connection,
    academy_id: int,
    *,
    name: str,
    start_month: str,
    end_month: str,
) -> dict:
    if end_month < start_month:
        raise SchoolYearError("Une année ne peut pas s'arrêter avant d'avoir commencé.")
    cursor = conn.execute(
        "INSERT INTO school_year (academy_id, name, start_month, end_month)"
        " VALUES (?, ?, ?, ?)",
        (academy_id, name.strip(), start_month, end_month),
    )
    conn.commit()
    return _one(conn, cursor.lastrowid)


def update_year(conn: sqlite3.Connection, year_id: int, **fields) -> dict:
    year = _one(conn, year_id)
    start = fields.get("start_month") or year["start_month"]
    end = fields.get("end_month") or year["end_month"]
    if end < start:
        raise SchoolYearError("Une année ne peut pas s'arrêter avant d'avoir commencé.")
    for column, value in fields.items():
        if value is not None:
            conn.execute(
                f"UPDATE school_year SET {column} = ? WHERE id = ?",
                (value, year_id),
            )
    conn.commit()
    return _one(conn, year_id)


def close_year(conn: sqlite3.Connection, year_id: int) -> dict:
    """Puts the season away and archives the students.

    Two clicks in a row must change nothing: a year already closed stays
    closed, with its original date. Re-archiving on the second pass would
    sweep away the students he has just taken back for the new term.
    """
    year = _one(conn, year_id)
    if year["closed_at"]:
        return year
    conn.execute(
        "UPDATE student SET is_active = 0 WHERE academy_id = ? AND is_active = 1",
        (year["academy_id"],),
    )
    conn.execute(
        "UPDATE school_year SET closed_at = datetime('now') WHERE id = ?",
        (year_id,),
    )
    conn.commit()
    return _one(conn, year_id)


def delete_year(conn: sqlite3.Connection, year_id: int) -> None:
    """Effacer une saison n'efface rien d'autre.

    A school year is only a period: two months between which a report can
    be produced. Deleting it undoes no payment and wakes no archived
    student -- it removes the boundary, nothing else.
    """
    _one(conn, year_id)
    conn.execute("DELETE FROM school_year WHERE id = ?", (year_id,))
    conn.commit()


def season_report(conn: sqlite3.Connection, year_id: int) -> dict:
    """The whole season's report: cash in, each party's share, and what
    every teacher earned across the full year."""
    from app.adapters.sqlite.reports import monthly_report

    year = _one(conn, year_id)
    months = months_between(year["start_month"], year["end_month"])

    cash_in = 0
    shares: dict[tuple[str, int], dict] = {}
    for month in months:
        report = monthly_report(conn, year["academy_id"], month)
        cash_in += report.cash_in
        for total in report.totals:
            key = (total.kind, total.ref_id)
            entry = shares.setdefault(
                key,
                {
                    "kind": total.kind,
                    "ref_id": total.ref_id,
                    "name": total.name,
                    "total": 0,
                },
            )
            entry["total"] += total.total

    return {
        "school_year_id": year["id"],
        "name": year["name"],
        "start_month": year["start_month"],
        "end_month": year["end_month"],
        "months": len(months),
        "cash_in": cash_in,
        "totals": sorted(shares.values(), key=lambda item: item["total"], reverse=True),
        "teachers": [
            {
                "teacher_id": item["ref_id"],
                "name": item["name"],
                "earned": item["total"],
            }
            for item in sorted(
                shares.values(), key=lambda item: item["total"], reverse=True
            )
            if item["kind"] == "teacher"
        ],
    }


def _one(conn: sqlite3.Connection, year_id: int) -> dict:
    row = conn.execute("SELECT * FROM school_year WHERE id = ?", (year_id,)).fetchone()
    if row is None:
        raise SchoolYearError("Cette année scolaire n'existe pas.")
    return dict(row)
