"""Which split a class follows, and where it gets it from.

The academy had a single split. It stays the reference -- but a seasoned
teacher is not paid like a beginner, and primary does not cost what
lycee costs.

The MOST SPECIFIC rule wins. We walk from the particular to the general
and stop at the first match: without that, one would have to guess which
of two applicable rules prevails, and that kind of guessing
finit toujours par surprendre quelqu'un sur une feuille de paie.
"""

import sqlite3
from dataclasses import dataclass

# Du plus precis au plus general. L ordre EST la regle.
PRECEDENCE = ("class", "teacher", "filiere", "level")


@dataclass(frozen=True)
class ResolvedSplit:
    venue_bp: int
    owner_bp: int
    #  Where it comes from: « class », « teacher », « filiere », « level »
    #  or « academy ». Saying so heads off "why this figure?"
    origin: str
    rule_name: str | None = None


def split_for_class(
    conn: sqlite3.Connection, class_id: int, academy_id: int
) -> ResolvedSplit:
    """The split that applies to this class, today."""
    row = conn.execute(
        "SELECT c.id, c.teacher_id, c.level_id, c.filiere FROM class_group c"
        " WHERE c.id = ?",
        (class_id,),
    ).fetchone()
    if row is None:
        return _academy_split(conn, academy_id)
    return resolve(
        conn,
        academy_id,
        class_id=row["id"],
        teacher_id=row["teacher_id"],
        level_id=row["level_id"],
        filiere=row["filiere"],
    )


def resolve(
    conn: sqlite3.Connection,
    academy_id: int,
    *,
    class_id: int | None = None,
    teacher_id: int | None = None,
    level_id: int | None = None,
    filiere: str | None = None,
) -> ResolvedSplit:
    """The winning rule, for a class that exists OR is being created.

    The creation form can therefore show what will apply before the class
    exists -- without duplicating the precedence order in the interface,
    where it would eventually drift away from this one.
    """
    keys = {"class": class_id, "teacher": teacher_id, "level": level_id}
    for scope in PRECEDENCE:
        found = (
            _by_text(conn, "filiere", filiere)
            if scope == "filiere"
            else _by_id(conn, scope, keys.get(scope))
        )
        if found is not None:
            return found
    return _academy_split(conn, academy_id)


def _by_id(
    conn: sqlite3.Connection, scope: str, ref_id: int | None
) -> ResolvedSplit | None:
    if ref_id is None:
        return None
    return _found(
        conn,
        "SELECT r.venue_bp, r.owner_bp, r.name FROM split_assignment a"
        " JOIN split_rule r ON r.id = a.rule_id"
        " WHERE a.scope = ? AND a.ref_id = ?",
        (scope, ref_id),
        scope,
    )


def _by_text(
    conn: sqlite3.Connection, scope: str, ref_text: str | None
) -> ResolvedSplit | None:
    if not ref_text:
        return None
    return _found(
        conn,
        "SELECT r.venue_bp, r.owner_bp, r.name FROM split_assignment a"
        " JOIN split_rule r ON r.id = a.rule_id"
        " WHERE a.scope = ? AND a.ref_text = ?",
        (scope, ref_text),
        scope,
    )


def _found(
    conn: sqlite3.Connection, sql: str, params: tuple, origin: str
) -> ResolvedSplit | None:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    return ResolvedSplit(row["venue_bp"], row["owner_bp"], origin, row["name"])


def _academy_split(conn: sqlite3.Connection, academy_id: int) -> ResolvedSplit:
    """The bottom of the chain: the split from the settings."""
    row = conn.execute(
        "SELECT venue_bp, owner_bp FROM academy WHERE id = ?", (academy_id,)
    ).fetchone()
    if row is None:
        return ResolvedSplit(0, 0, "academy")
    return ResolvedSplit(row["venue_bp"], row["owner_bp"], "academy")
