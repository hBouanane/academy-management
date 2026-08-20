"""Les saisons : les définir, les clore, et faire leur bilan.

Clore une année n'efface rien. Les élèves sont archivés parce qu'on ne
présume pas qu'ils reviendront -- celui qui revient est réinscrit comme
d'habitude et retrouve son histoire entière. Ce qu'une famille doit, en
revanche, la suit : l'argent dû ne s'efface pas parce que le calendrier
a tourné.
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
    """Range la saison et archive les élèves.

    Deux clics de suite ne doivent rien changer : une année déjà close
    reste close, avec sa date d'origine. Réarchiver au deuxième passage
    balaierait ceux qu'il vient de reprendre pour la rentrée.
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


def season_report(conn: sqlite3.Connection, year_id: int) -> dict:
    """Le bilan de toute la saison : l'encaissé, la part de chacun, et ce
    que chaque professeur a gagné sur l'année entière."""
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
