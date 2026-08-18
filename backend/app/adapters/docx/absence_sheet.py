"""Printable attendance sheet (liste d'absence) as a Word document.

Title and class facts on top, then a bordered table: one row per enrolled
student, blank session columns for handwritten marks.
"""

import sqlite3
from io import BytesIO

from docx import Document
from docx.shared import Pt

from app.adapters.docx.labels import annee_label, month_label

SESSION_COLUMNS = 8


def absence_sheet(conn: sqlite3.Connection, class_id: int, month: str) -> bytes:
    facts = conn.execute(
        """
        SELECT cg.name AS group_name, cg.annee, cg.filiere, cg.parcours,
               sub.name AS subject_name, sl.name AS level_name,
               t.name AS teacher_name
        FROM class_group cg
        JOIN subject sub ON sub.id = cg.subject_id
        JOIN school_level sl ON sl.id = cg.level_id
        LEFT JOIN teacher t ON t.id = cg.teacher_id
        WHERE cg.id = ?
        """,
        (class_id,),
    ).fetchone()
    if facts is None:
        raise LookupError(f"no class_group {class_id}")
    students = conn.execute(
        """
        SELECT s.name, s.first_name, s.phone
        FROM enrollment e
        JOIN enrollment_class ec ON ec.enrollment_id = e.id
        JOIN student s ON s.id = e.student_id
        WHERE ec.class_id = ? AND e.month = ?
        ORDER BY s.name, s.first_name
        """,
        (class_id, month),
    ).fetchall()

    document = Document()
    # Pas de « Groupe A » : une classe se nomme par sa matière et son
    # créneau, ses jumelles se distinguent par leur professeur.
    document.add_heading(f"Liste d'absence — {facts['subject_name']}", level=1)
    document.add_paragraph(_segment_line(facts))
    document.add_paragraph(
        f"Professeur : {facts['teacher_name'] or 'Sans professeur'}"
        f"    Mois : {month_label(month)}"
    )

    table = document.add_table(rows=1, cols=3 + SESSION_COLUMNS)
    table.style = "Table Grid"
    header = table.rows[0].cells
    for index, title in enumerate(
        ["N°", "Étudiant", "Téléphone"] + ["" for _ in range(SESSION_COLUMNS)]
    ):
        run = header[index].paragraphs[0].add_run(title)
        run.bold = True
        run.font.size = Pt(10)
    for position, student in enumerate(students, start=1):
        cells = table.add_row().cells
        cells[0].text = str(position)
        cells[1].text = " ".join(
            part for part in (student["first_name"], student["name"]) if part
        )
        cells[2].text = student["phone"] or ""

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _segment_line(facts: sqlite3.Row) -> str:
    parts = [f"Niveau : {facts['level_name']}"]
    annee = annee_label(facts["level_name"], facts["annee"])
    if annee:
        parts.append(annee)
    if facts["parcours"]:
        parts.append(f"parcours {facts['parcours']}")
    if facts["filiere"]:
        parts.append(facts["filiere"])
    return "    ".join(parts)
