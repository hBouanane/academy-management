"""Writing the journal, and reading it back.

Two rules hold the whole thing up.

The line is written only once the action has SUCCEEDED. A refused payout
leaves nothing behind, so a line that exists is a thing that happened --
without that, the journal would need to be read with suspicion, and a
journal read with suspicion answers nothing.

The name is resolved and frozen at that moment. Resolving it at READ time
would have been less code and one fewer column, and it would have made
every past line follow the student's current name -- so a family renamed
in March would silently rewrite what was on screen in September, which is
precisely the question the journal exists to answer.
"""

import sqlite3

from app.domain.journal import Entry

_NOW = "strftime('%Y-%m-%d %H:%M:%f', 'now')"

# Une page tient dans un ecran ; au-dela on pagine plutot que de charger
# une annee de lignes pour en lire trois.
PAGE = 50
MAX_PAGE = 200


def note(
    conn: sqlite3.Connection,
    academy_id: int,
    action: str,
    *,
    month: str | None = None,
    subject: tuple[str, int] | None = None,
    amount_centimes: int | None = None,
    detail: str | None = None,
) -> None:
    """Remember an action, naming who it concerned.

    Takes the subject as (kind, id) and looks its name up here: the call
    sites are inside routes that already did the real work, and each extra
    line there is a line that can be forgotten on the next one added.
    """
    kind, ref_id = subject if subject else (None, None)
    entry = Entry(
        action=action,
        month=month,
        subject_kind=kind,
        subject_id=ref_id,
        subject_label=name_of(conn, kind, ref_id) if kind else None,
        amount_centimes=amount_centimes,
        detail=detail,
    )
    record(conn, academy_id, entry)


def record(conn: sqlite3.Connection, academy_id: int, entry: Entry) -> None:
    """Append one line. Nothing ever updates or deletes one."""
    conn.execute(
        "INSERT INTO journal_entry (academy_id, happened_at, action, month,"
        " subject_kind, subject_id, subject_label, amount_centimes, detail)"
        f" VALUES (?, {_NOW}, ?, ?, ?, ?, ?, ?, ?)",
        (
            academy_id,
            entry.action,
            entry.month,
            entry.subject_kind,
            entry.subject_id,
            entry.subject_label,
            entry.amount_centimes,
            entry.detail,
        ),
    )
    conn.commit()


def name_of(
    conn: sqlite3.Connection, kind: str | None, ref_id: int | None
) -> str | None:
    """« Sami » beats « 12 » -- on the day it is read, the id says nothing."""
    if kind is None or ref_id is None:
        return None
    if kind == "student":
        return _one(conn, "SELECT name FROM student WHERE id = ?", ref_id)
    if kind == "teacher":
        return _one(conn, "SELECT name FROM teacher WHERE id = ?", ref_id)
    if kind == "venue":
        return _one(conn, "SELECT name FROM venue WHERE id = ?", ref_id)
    if kind == "owner":
        return _one(conn, "SELECT name FROM academy WHERE id = ?", ref_id)
    if kind == "class":
        return _one(
            conn,
            "SELECT s.name FROM class_group c JOIN subject s ON s.id = c.subject_id"
            " WHERE c.id = ?",
            ref_id,
        )
    return None


def _one(conn: sqlite3.Connection, sql: str, ref_id: int) -> str | None:
    row = conn.execute(sql, (ref_id,)).fetchone()
    return row[0] if row else None


def entries(
    conn: sqlite3.Connection,
    academy_id: int,
    *,
    month: str | None = None,
    subject_kind: str | None = None,
    subject_id: int | None = None,
    limit: int = PAGE,
    before_id: int | None = None,
) -> list[dict]:
    """The most recent first, optionally narrowed.

    Paged by id rather than by offset: the journal grows while it is being
    read, and an offset would then show one line twice or skip one --
    exactly the line being looked for, on the day it matters.
    """
    sql = "SELECT * FROM journal_entry WHERE academy_id = ?"
    params: list = [academy_id]
    if month is not None:
        sql += " AND month = ?"
        params.append(month)
    if subject_kind is not None:
        sql += " AND subject_kind = ? AND subject_id = ?"
        params += [subject_kind, subject_id]
    if before_id is not None:
        sql += " AND id < ?"
        params.append(before_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(limit, MAX_PAGE)))
    return [dict(row) for row in conn.execute(sql, params)]
