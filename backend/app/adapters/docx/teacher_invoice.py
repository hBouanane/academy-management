"""La facture du mois d'un professeur, en Word — imprimable et signable.

Elle dit ce qu'il a gagné classe par classe, ce qui lui a déjà été versé et
ce qui reste, puis laisse deux lignes de signature. Le dû vient des élèves
INSCRITS (payés ou non) : le professeur a enseigné, il est payé.
"""

import sqlite3
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from app.adapters.docx.labels import annee_label, month_label


def _dh(centimes: int) -> str:
    return f"{centimes / 100:,.2f} DH".replace(",", " ").replace(".", ",")


def teacher_invoice(conn: sqlite3.Connection, teacher_id: int, month: str) -> bytes:
    from app.adapters.sqlite.crud import caisse_summary, teacher_profile

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

    document = Document()
    document.add_heading(f"Fiche de paie — {month_label(month)}", level=1)
    document.add_paragraph(academy["name"])
    document.add_paragraph(
        f"Professeur : {profile['name']}"
        + (f"    Téléphone : {profile['phone']}" if profile["phone"] else "")
    )

    document.add_paragraph()
    table = document.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    for cell, title in zip(
        table.rows[0].cells,
        ("Classe", "Niveau", "Inscrits", "Montant"),
        strict=True,
    ):
        cell.text = title
        cell.paragraphs[0].runs[0].font.bold = True

    for entry in profile["classes"]:
        if entry["earned_centimes"] == 0 and entry["enrolled_count"] == 0:
            continue
        cells = table.add_row().cells
        cells[0].text = entry["subject_name"]
        cells[1].text = _segment(entry)
        cells[2].text = str(entry["enrolled_count"])
        cells[3].text = _dh(entry["earned_centimes"])
        cells[3].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

    document.add_paragraph()
    for label, amount, bold in (
        ("Dû pour le mois", due, True),
        ("Déjà versé", paid, False),
        ("Reste à verser", max(due - paid, 0), True),
    ):
        paragraph = document.add_paragraph()
        run = paragraph.add_run(f"{label} : {_dh(amount)}")
        run.font.bold = bold
        run.font.size = Pt(12)

    document.add_paragraph()
    document.add_paragraph(
        "Le détail par classe suit les élèves inscrits du mois — un élève qui"
        " n'a pas encore payé ne change rien à ce qui est dû au professeur."
    ).runs[0].font.size = Pt(8)
    document.add_paragraph()
    signatures = document.add_table(rows=2, cols=2)
    signatures.rows[0].cells[0].text = "Signature du professeur"
    signatures.rows[0].cells[1].text = "Signature de l'académie"
    for cell in signatures.rows[1].cells:
        cell.text = "\n\n"

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


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
