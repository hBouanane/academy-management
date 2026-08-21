"""La fiche de paie d'un professeur, en Word — imprimable et signable.

Elle dit ce qu'il a gagné classe par classe, ce qui lui a déjà été versé
et ce qui reste, puis laisse deux lignes de signature. Le dû vient des
élèves INSCRITS (payés ou non) : le professeur a enseigné, il est payé.

Sortie AU MOMENT DE PAYER, elle devient un reçu : elle porte alors le
versement — sa date et son montant — en haut, avant le détail. C'est
celle-là qu'on fait signer, parce qu'elle atteste de ce qui vient
d'être remis.
"""

import sqlite3
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from app.adapters.docx.labels import annee_label, month_label


def _dh(centimes: int) -> str:
    return f"{centimes / 100:,.2f} DH".replace(",", " ").replace(".", ",")


def teacher_invoice(
    conn: sqlite3.Connection,
    teacher_id: int,
    month: str,
    payout_id: int | None = None,
) -> bytes:
    from app.adapters.sqlite.crud import (
        caisse_summary,
        teacher_class_dues,
        teacher_profile,
    )

    academy = conn.execute(
        "SELECT id, name FROM academy ORDER BY id LIMIT 1"
    ).fetchone()
    profile = teacher_profile(conn, teacher_id, month)
    if profile is None:
        raise LookupError(f"no teacher {teacher_id}")
    line = next(
        (
            entry
            for entry in caisse_summary(conn, academy["id"], month)["lines"]
            if entry["kind"] == "teacher" and entry["ref_id"] == teacher_id
        ),
        None,
    )
    due = line["due_centimes"] if line else 0
    paid = line["paid_centimes"] if line else 0
    payout = _payout(conn, payout_id, teacher_id) if payout_id else None
    # Le détail vient de la MÊME source que le total : ce qui est dû,
    # classe par classe. Deux calculs différents donneraient deux vérités.
    per_class = teacher_class_dues(conn, academy["id"], teacher_id, month)

    document = Document()

    # Un reçu se signe et se partage : une moitié reste à l'académie,
    # l'autre part avec le professeur. Une seule feuille, un trait au
    # milieu — c'est ce qu'on fait au comptoir, et ça évite d'imprimer
    # deux fois. La fiche du mois, elle, ne se signe pas : un exemplaire
    # suffit.
    copies = ("Exemplaire académie", "Exemplaire professeur") if payout else (None,)
    for index, whose in enumerate(copies):
        if index:
            _cut_line(document)
        if whose:
            marker = document.add_paragraph(whose)
            marker.runs[0].font.size = Pt(8)
            marker.runs[0].font.bold = True
        _one_copy(document, profile, month, academy, payout, per_class, due, paid)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _cut_line(doc) -> None:
    """Là où passent les ciseaux."""
    doc.add_paragraph()
    line = doc.add_paragraph("\u2702 " + "- " * 40)
    line.runs[0].font.size = Pt(8)
    doc.add_paragraph()


def _one_copy(doc, profile, month, academy, payout, per_class, due, paid) -> None:
    """Le contenu, écrit une fois — et imprimé deux quand on le signe."""
    doc.add_heading(
        ("Reçu de versement — " if payout else "Fiche de paie — ") + month_label(month),
        level=1,
    )
    doc.add_paragraph(academy["name"])
    doc.add_paragraph(
        f"Professeur : {profile['name']}"
        + (f"    Téléphone : {profile['phone']}" if profile["phone"] else "")
    )

    # Ce qu'on vient de lui remettre, avant tout le reste : c'est la
    # raison d'être du papier qu'il signe.
    if payout:
        doc.add_paragraph()
        paragraph = doc.add_paragraph()
        run = paragraph.add_run(
            f"Versé ce jour ({payout['paid_on']}) : {_dh(payout['amount_centimes'])}"
        )
        run.font.bold = True
        run.font.size = Pt(14)
        if payout["note"]:
            doc.add_paragraph(payout["note"]).runs[0].font.size = Pt(9)

    doc.add_paragraph()
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    for cell, title in zip(
        table.rows[0].cells,
        ("Classe", "Niveau", "Inscrits", "Montant"),
        strict=True,
    ):
        cell.text = title
        cell.paragraphs[0].runs[0].font.bold = True

    for entry in profile["classes"]:
        amount = per_class.get(entry["id"], 0)
        if amount == 0 and entry["enrolled_count"] == 0:
            continue
        cells = table.add_row().cells
        cells[0].text = entry["subject_name"]
        cells[1].text = _segment(entry)
        cells[2].text = str(entry["enrolled_count"])
        cells[3].text = _dh(amount)
        cells[3].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

    doc.add_paragraph()
    for label, amount, bold in (
        ("Dû pour le mois", due, True),
        ("Déjà versé", paid, False),
        ("Reste à verser", max(due - paid, 0), True),
    ):
        paragraph = doc.add_paragraph()
        run = paragraph.add_run(f"{label} : {_dh(amount)}")
        run.font.bold = bold
        run.font.size = Pt(12)

    doc.add_paragraph()
    doc.add_paragraph(
        "Le détail par classe suit les élèves inscrits du mois — un élève qui"
        " n'a pas encore payé ne change rien à ce qui est dû au professeur."
    ).runs[0].font.size = Pt(8)
    doc.add_paragraph()
    if payout:
        doc.add_paragraph(
            "Reçu pour solde de ce versement. Le reste à verser, s'il y en"
            " a, fera l'objet d'un autre reçu."
        ).runs[0].font.size = Pt(8)
    signatures = doc.add_table(rows=2, cols=2)
    signatures.rows[0].cells[0].text = "Signature du professeur"
    signatures.rows[0].cells[1].text = "Signature de l'académie"
    for cell in signatures.rows[1].cells:
        cell.text = "\n\n"


def _payout(conn: sqlite3.Connection, payout_id: int, teacher_id: int) -> dict:
    """Le versement designe — et il doit bien avoir ete fait A CE
    professeur : un recu atteste, il ne se recopie pas d'un autre."""
    row = conn.execute(
        "SELECT amount_centimes, paid_on, note FROM payout"
        " WHERE id = ? AND beneficiary_kind = 'teacher' AND beneficiary_id = ?",
        (payout_id, teacher_id),
    ).fetchone()
    if row is None:
        raise LookupError(f"no payout {payout_id} for teacher {teacher_id}")
    return dict(row)


def _segment(entry: dict) -> str:
    parts = [entry["level_name"]]
    annee = annee_label(entry["level_name"], entry["annee"])
    if annee:
        parts.append(annee)
    if entry["parcours"]:
        parts.append(entry["parcours"])
    if entry["filiere"]:
        parts.append(entry["filiere"])
    return " · ".join(parts)
