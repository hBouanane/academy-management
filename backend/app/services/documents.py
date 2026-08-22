"""Documents that were produced, and what makes them stale.

A printed sheet is a photograph: it ages the moment the figures move.
This module keeps two registers -- what was produced, and when each
thing last moved -- and compares them.

Scope is the whole point. Announcing "September changed" would mark
every sheet of the month stale for a single payment; after two weeks the
warning would go unread. Each write therefore says WHO it touches, and
only the affected documents surface.
"""

import sqlite3
from dataclasses import dataclass

# datetime('now') stops at the second: two actions within the same
# second would compare equal, and a sheet made stale immediately after
# being produced would pass for fresh.
_NOW = "strftime('%Y-%m-%d %H:%M:%f', 'now')"

# One drawer per kind of document, one folder per month: the filing the
# owner would do by hand, done for him.
DRAWERS = {
    "payslip": "fiches-de-paie",
    "absence": "absences",
    "excel": "rapports",
}

# What each kind of document attaches to.
SCOPES = {"payslip": "teacher", "absence": "class", "excel": "month"}

LABELS = {
    "payslip": "Fiche de paie",
    "absence": "Feuille d'absence",
    "excel": "Export Excel",
}


@dataclass(frozen=True)
class StaleDocument:
    kind: str
    month: str
    scope: str
    ref_id: int
    path: str
    generated_at: str
    touched_at: str
    label: str


def touch(conn: sqlite3.Connection, month: str, scopes: list[tuple[str, int]]) -> None:
    """Record that something moved, and for whom.

    The whole month is always marked alongside the precise scope:
    l'export Excel, lui, regarde tout le mois.
    """
    marks = {("month", 0), *scopes}
    conn.executemany(
        "INSERT INTO document_touch (month, scope, ref_id, touched_at)"
        f" VALUES (?, ?, ?, {_NOW})"
        " ON CONFLICT(month, scope, ref_id)"
        f" DO UPDATE SET touched_at = {_NOW}",
        [(month, scope, ref_id) for scope, ref_id in marks],
    )


def scopes_of_enrollment(
    conn: sqlite3.Connection, enrollment_id: int
) -> list[tuple[str, int]]:
    """Ce qu'une inscription touche : ses classes, et leurs professeurs.

    The teacher is concerned even without a payment -- what he is owed is
    counted on ENROLLED students. One more student changes his sheet.
    """
    rows = conn.execute(
        "SELECT c.id AS class_id, c.teacher_id FROM enrollment_class ec"
        " JOIN class_group c ON c.id = ec.class_id"
        " WHERE ec.enrollment_id = ?",
        (enrollment_id,),
    ).fetchall()
    scopes: list[tuple[str, int]] = []
    for row in rows:
        scopes.append(("class", row["class_id"]))
        if row["teacher_id"] is not None:
            scopes.append(("teacher", row["teacher_id"]))
    return scopes


def record_export(
    conn: sqlite3.Connection,
    kind: str,
    month: str,
    ref_id: int,
    path: str,
    payout_id: int | None = None,
) -> None:
    """Remember where a document was filed.

    A receipt is keyed by its payout: two payouts to the same teacher in
    one month are two papers, and the second does not replace the first.
    Everything else keeps one row per month and scope.
    """
    if payout_id is not None:
        conn.execute(
            "INSERT INTO exported_document (kind, month, scope, ref_id,"
            f" payout_id, path, generated_at) VALUES (?, ?, ?, ?, ?, ?, {_NOW})"
            # A PARTIAL index only matches an upsert whose conflict target
            # repeats its predicate.
            " ON CONFLICT(payout_id) WHERE payout_id IS NOT NULL DO UPDATE SET"
            " path = excluded.path, generated_at = excluded.generated_at",
            (kind, month, SCOPES[kind], ref_id, payout_id, path),
        )
    else:
        conn.execute(
            "INSERT INTO exported_document (kind, month, scope, ref_id, path,"
            f" generated_at) VALUES (?, ?, ?, ?, ?, {_NOW})"
            " ON CONFLICT(kind, month, scope, ref_id) WHERE payout_id IS NULL"
            " DO UPDATE SET"
            " path = excluded.path, generated_at = excluded.generated_at",
            (kind, month, SCOPES[kind], ref_id, path),
        )
    conn.commit()


def receipt_path(conn: sqlite3.Connection, payout_id: int) -> str | None:
    """The file already filed for this payout, if there is one.

    This is what makes a receipt a receipt: asked for a second time, the
    paper that was signed comes back -- not a fresh one describing a month
    that has moved on since.
    """
    row = conn.execute(
        "SELECT path FROM exported_document WHERE payout_id = ?", (payout_id,)
    ).fetchone()
    return row["path"] if row else None


def cancel_receipt(conn: sqlite3.Connection, payout_id: int) -> str | None:
    """Rename a cancelled payout's receipt, and say where it went.

    Not deleted: the professor may already hold the signed sheet, and
    removing our copy does not retrieve his. A file marked « annule »
    makes the mismatch visible instead of silent.
    """
    from pathlib import Path as FsPath

    path = receipt_path(conn, payout_id)
    if path is None:
        return None
    source = FsPath(path)
    conn.execute("DELETE FROM exported_document WHERE payout_id = ?", (payout_id,))
    conn.commit()
    if not source.exists():
        return None
    target = source.with_name(f"{source.stem} - annule{source.suffix}")
    try:
        source.replace(target)
    except OSError:
        return None
    return str(target)


def stale_documents(
    conn: sqlite3.Connection, month: str | None = None
) -> list[StaleDocument]:
    """What was produced before the figures moved.

    What was never produced does not appear: we do not demand a document
    nobody asked for.
    """
    # A payslip is not a report: it is a RECEIPT. It states that
    # 265,16 DH left the till that day, and nothing that happens
    # afterwards makes that false. Offering to "regenerate" it would
    # produce a second sheet contradicting the one the teacher signed.
    sql = (
        "SELECT d.kind, d.month, d.scope, d.ref_id, d.path, d.generated_at,"
        " t.touched_at FROM exported_document d"
        " JOIN document_touch t ON t.month = d.month AND t.scope = d.scope"
        "   AND t.ref_id = d.ref_id"
        " WHERE t.touched_at > d.generated_at AND d.kind <> 'payslip'"
    )
    params: tuple = ()
    if month is not None:
        sql += " AND d.month = ?"
        params = (month,)
    return [
        StaleDocument(
            kind=row["kind"],
            month=row["month"],
            scope=row["scope"],
            ref_id=row["ref_id"],
            path=row["path"],
            generated_at=row["generated_at"],
            touched_at=row["touched_at"],
            label=f"{LABELS[row['kind']]} — {_who(conn, row['scope'], row['ref_id'])}",
        )
        for row in conn.execute(sql + " ORDER BY d.month DESC, d.kind", params)
    ]


def _who(conn: sqlite3.Connection, scope: str, ref_id: int) -> str:
    """The name behind the scope -- « Moulay Idris » beats « 3 »."""
    if scope == "teacher":
        row = conn.execute(
            "SELECT name FROM teacher WHERE id = ?", (ref_id,)
        ).fetchone()
        return row["name"] if row else "professeur inconnu"
    if scope == "class":
        row = conn.execute(
            "SELECT s.name AS subject, t.name AS teacher FROM class_group c"
            " JOIN subject s ON s.id = c.subject_id"
            " LEFT JOIN teacher t ON t.id = c.teacher_id WHERE c.id = ?",
            (ref_id,),
        ).fetchone()
        if not row:
            return "classe inconnue"
        teacher = row["teacher"]
        return row["subject"] + (f" · {teacher}" if teacher else "")
    return "le mois entier"
