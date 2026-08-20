"""Quelle répartition suit une classe, et d'où elle la tient.

L'académie avait une répartition unique. Elle reste la référence — mais
un professeur chevronné ne se paie pas comme un débutant, et le
primaire ne coûte pas ce que coûte le lycée.

La règle la plus PRÉCISE gagne. On remonte du particulier au général et
on s'arrête à la première trouvée : sans cela, il faudrait deviner
laquelle de deux règles applicables l'emporte, et ce genre de devinette
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
    #  D'où elle vient : « class », « teacher », « filiere », « level »
    #  ou « academy ». Le dire évite la question « pourquoi ce chiffre ? »
    origin: str
    rule_name: str | None = None


def split_for_class(
    conn: sqlite3.Connection, class_id: int, academy_id: int
) -> ResolvedSplit:
    """La répartition qui s'applique à cette classe, aujourd'hui."""
    row = conn.execute(
        "SELECT c.id, c.teacher_id, c.level_id, c.filiere FROM class_group c"
        " WHERE c.id = ?",
        (class_id,),
    ).fetchone()
    if row is None:
        return _academy_split(conn, academy_id)
    keys = {
        "class": row["id"],
        "teacher": row["teacher_id"],
        "level": row["level_id"],
    }
    for scope in PRECEDENCE:
        found = (
            _by_text(conn, "filiere", row["filiere"])
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
    """Le fond de la chaîne : la répartition des réglages."""
    row = conn.execute(
        "SELECT venue_bp, owner_bp FROM academy WHERE id = ?", (academy_id,)
    ).fetchone()
    if row is None:
        return ResolvedSplit(0, 0, "academy")
    return ResolvedSplit(row["venue_bp"], row["owner_bp"], "academy")
