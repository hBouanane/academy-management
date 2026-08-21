"""A teacher's payslip, in Word -- printable and signable.

It states what he earned class by class, what has already been paid to
him and what remains, then leaves two signature lines. What is owed
comes from ENROLLED students, paid or not: the teacher taught, so the
teacher is paid.

Produced AT THE MOMENT OF PAYING, it becomes a receipt: it then carries
the payout -- its date and its amount -- at the top, before the
breakdown. That is the one to be signed, because it attests to what has
just been handed over.
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
    # The breakdown comes from the SAME source as the total: what is
    # owed, class by class. Two separate computations would give two
    # truths.
    per_class = teacher_class_dues(conn, academy["id"], teacher_id, month)

    document = Document()

    # A receipt is signed and split: one half stays with the academie,
    # the other leaves with the teacher. One sheet, a line down the
    # middle -- that is what happens at the counter, and it avoids
    # printing twice. The plain monthly sheet is not signed: one copy is
    # enough.
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
    """Where the scissors go."""
    doc.add_paragraph()
    line = doc.add_paragraph("\u2702 " + "- " * 40)
    line.runs[0].font.size = Pt(8)
    doc.add_paragraph()


def _one_copy(doc, profile, month, academy, payout, per_class, due, paid) -> None:
    """The content, written once -- and printed twice when it is signed."""
    doc.add_heading(
        ("Reçu de versement — " if payout else "Fiche de paie — ") + month_label(month),
        level=1,
    )
    doc.add_paragraph(academy["name"])
    doc.add_paragraph(
        f"Professeur : {profile['name']}"
        + (f"    Téléphone : {profile['phone']}" if profile["phone"] else "")
    )

    # What has just been handed to him, before anything else: it is the
    # reason the paper he signs exists.
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
