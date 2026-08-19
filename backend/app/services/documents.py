"""Les documents sortis, et ce qui les périme.

Un papier imprimé est une photographie : il vieillit dès que les
chiffres bougent. Ce module tient deux registres — ce qui a été sorti,
et quand chaque chose a bougé pour la dernière fois — et compare.

La portée est tout l'intérêt. Signaler « septembre a changé » marquerait
périmées toutes les fiches du mois pour un seul encaissement ; au bout
de deux semaines l'avertissement ne serait plus lu. Chaque écriture dit
donc QUI elle touche, et seuls les documents concernés remontent.
"""

import sqlite3
from dataclasses import dataclass

# datetime('now') s'arrete a la seconde : deux gestes dans la meme
# seconde se vaudraient, et une fiche perimee juste apres avoir ete
# sortie passerait pour fraiche.
_NOW = "strftime('%Y-%m-%d %H:%M:%f', 'now')"

# Un tiroir par sorte de document, un dossier par mois : le classement
# que le propriétaire ferait à la main, fait pour lui.
DRAWERS = {
    "payslip": "fiches-de-paie",
    "absence": "absences",
    "excel": "rapports",
}

# À quoi se rattache chaque sorte de document.
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
    """Dire que quelque chose a bougé, et pour qui.

    Le mois entier est toujours marqué en plus de la portée précise :
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

    Le professeur est concerné même sans paiement — son dû se compte sur
    les élèves INSCRITS. Un élève de plus change sa fiche.
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
    conn: sqlite3.Connection, kind: str, month: str, ref_id: int, path: str
) -> None:
    conn.execute(
        "INSERT INTO exported_document (kind, month, scope, ref_id, path,"
        f" generated_at) VALUES (?, ?, ?, ?, ?, {_NOW})"
        " ON CONFLICT(kind, month, scope, ref_id) DO UPDATE SET"
        " path = excluded.path, generated_at = excluded.generated_at",
        (kind, month, SCOPES[kind], ref_id, path),
    )
    conn.commit()


def stale_documents(
    conn: sqlite3.Connection, month: str | None = None
) -> list[StaleDocument]:
    """Ce qui a été sorti avant que les chiffres ne bougent.

    Ce qui n'a jamais été sorti n'apparaît pas : on ne réclame pas un
    document que personne n'a demandé.
    """
    sql = (
        "SELECT d.kind, d.month, d.scope, d.ref_id, d.path, d.generated_at,"
        " t.touched_at FROM exported_document d"
        " JOIN document_touch t ON t.month = d.month AND t.scope = d.scope"
        "   AND t.ref_id = d.ref_id"
        " WHERE t.touched_at > d.generated_at"
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
    """Le nom derrière la portée — « Moulay Idris » vaut mieux que « 3 »."""
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
