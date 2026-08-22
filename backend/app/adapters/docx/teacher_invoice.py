"""A teacher's payslip, in Word -- printable, signable, always one page.

It states what he earned class by class, what has already been paid to
him and what remains, then leaves two signature lines. What is owed
comes from ENROLLED students, paid or not: the teacher taught, so the
teacher is paid.

Produced AT THE MOMENT OF PAYING, it becomes a receipt: it carries the
payout -- its date and its amount -- at the top, before the breakdown.
That is the one to be signed, because it attests to what has just been
handed over.

THE LAYOUT IS FIXED-HEIGHT, and that is the whole point of it.

A receipt is signed and split: one half stays with the academie, the
other leaves with the teacher. One sheet, a line down the middle. But
with Word's defaults every extra class made the copy taller, so past
four or five classes the second copy slid onto page two and the pair
could no longer be cut apart.

So each copy lives inside a container whose row height is EXACT, and the
class table always holds the same number of rows: fewer classes are
padded with blank ones, more are collapsed into a final « + N autres
classes » line. The document is one page whatever the month held, and
the scissors always fall at the same millimetre -- which is what lets a
stack of them be cut at once.
"""

import sqlite3
from io import BytesIO

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from app.adapters.docx.labels import annee_label, month_label

FONT = "Calibri"
# The class table always has this many rows, so its height never moves.
# Twelve of them are real classes; the thirteenth collapses the rest.
MAX_ROWS = 13
MAX_CHARS_CLASS = 22
MAX_CHARS_LEVEL = 24

# A4. Use 12240 x 15840 for US Letter.
PAGE_W, PAGE_H = 11906, 16838
MARGIN_V = 397
MARGIN_H = 624

# The vertical budget of ONE copy, in twips (1440 = one inch). Two copies
# plus the cut line have to stay inside the page.
# Two copies plus the cut line must stay under 16044 - 300 twips, so each
# one has 7872 to live in. Thirteen rows need 3230 of the body, so 250 is
# borrowed from the signature block, which only uses 900 of its own.
H_BODY = 6600
H_SIGNATURE = 1250

GREY = RGBColor(0x6B, 0x6B, 0x6B)
BLACK = RGBColor(0x1A, 0x1A, 0x1A)


def _dh(centimes: int) -> str:
    return f"{centimes / 100:,.2f} DH".replace(",", " ").replace(".", ",")


# --- low-level XML helpers -------------------------------------------------
def _el(tag, **attrs):
    element = OxmlElement(tag)
    for key, value in attrs.items():
        element.set(qn("w:" + key), str(value))
    return element


def _table_borders(table, top=None, bottom=None, inside=None, frame=None) -> None:
    """Borders only where asked for.

    The class table is ruled: on paper, a breakdown with no lines reads as
    floating text, and the reserved empty rows look like a mistake rather
    than room left for more classes. On screen Word draws its own guides
    over everything, which is why this only showed up in the PDF.
    """
    properties = table._tbl.tblPr
    for old in properties.findall(qn("w:tblBorders")):
        properties.remove(old)
    borders = OxmlElement("w:tblBorders")
    wanted = {
        "top": top,
        "bottom": bottom,
        "left": frame,
        "right": frame,
        "insideH": inside,
        "insideV": inside,
    }
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        size = wanted.get(side)
        if size:
            borders.append(
                _el("w:" + side, val="single", sz=size, space=0, color="BFBFBF")
            )
        else:
            borders.append(_el("w:" + side, val="nil"))
    properties.append(borders)


def _row_bottom_border(row, size=6, colour="999999") -> None:
    for cell in row.cells:
        properties = cell._tc.get_or_add_tcPr()
        for old in properties.findall(qn("w:tcBorders")):
            properties.remove(old)
        borders = OxmlElement("w:tcBorders")
        borders.append(_el("w:bottom", val="single", sz=size, space=0, color=colour))
        properties.append(borders)


def _cell_margins(table, top=0, bottom=0, left=60, right=60) -> None:
    margins = OxmlElement("w:tblCellMar")
    for side, value in (
        ("top", top),
        ("left", left),
        ("bottom", bottom),
        ("right", right),
    ):
        margins.append(_el("w:" + side, w=value, type="dxa"))
    table._tbl.tblPr.append(margins)


def _exact_height(row, twips: int) -> None:
    """« exact », not « at least »: a long class name must not be able to
    push a row taller and shift everything below it."""
    properties = row._tr.get_or_add_trPr()
    for old in properties.findall(qn("w:trHeight")):
        properties.remove(old)
    properties.append(_el("w:trHeight", val=twips, hRule="exact"))
    properties.append(OxmlElement("w:cantSplit"))


def _widths(table, columns: list[int]) -> None:
    table.autofit = False
    properties = table._tbl.tblPr
    properties.append(_el("w:tblW", w=sum(columns), type="dxa"))
    properties.append(_el("w:tblLayout", type="fixed"))
    for row in table.rows:
        for cell, width in zip(row.cells, columns, strict=True):
            cell.width = Pt(width / 20)


# --- text helpers ----------------------------------------------------------
def _text(
    parent,
    content,
    size=8,
    bold=False,
    colour=BLACK,
    align=None,
    leading=None,
    before=0,
    after=0,
    paragraph=None,
):
    p = paragraph if paragraph is not None else parent.add_paragraph()
    fmt = p.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    if leading:
        fmt.line_spacing = Pt(leading)
    if align is not None:
        p.alignment = align
    if content:
        run = p.add_run(content)
        run.font.name = FONT
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = colour
    return p


def _cell_text(cell, content, size=8, bold=False, align=None, colour=BLACK) -> None:
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    _text(
        None,
        content,
        size=size,
        bold=bold,
        colour=colour,
        align=align,
        leading=9,
        paragraph=cell.paragraphs[0],
    )


def _clip(value, limit: int) -> str:
    """Truncated rather than wrapped: wrapping is what broke the height."""
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


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

    rows = []
    for entry in profile["classes"]:
        amount = per_class.get(entry["id"], 0)
        if amount == 0 and entry["enrolled_count"] == 0:
            continue
        rows.append(
            {
                "classe": entry["subject_name"],
                "niveau": _segment(entry),
                "inscrits": str(entry["enrolled_count"]),
                "montant": amount,
            }
        )

    data = {
        "mois": month_label(month),
        "academie": academy["name"],
        "professeur": profile["name"],
        "telephone": profile["phone"] or "",
        "date": payout["paid_on"] if payout else None,
        "verse": _dh(payout["amount_centimes"]) if payout else None,
        "note": payout["note"] if payout else None,
        "du": _dh(due),
        "deja_verse": _dh(paid),
        "reste": _dh(max(due - paid, 0)),
        "classes": rows,
    }

    document = Document()
    style = document.styles["Normal"]
    style.font.name = FONT
    style.font.size = Pt(8)
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.line_spacing = Pt(10)

    section = document.sections[0]
    section.page_width, section.page_height = Pt(PAGE_W / 20), Pt(PAGE_H / 20)
    section.top_margin = section.bottom_margin = Pt(MARGIN_V / 20)
    section.left_margin = section.right_margin = Pt(MARGIN_H / 20)
    usable = PAGE_W - 2 * MARGIN_H

    # A receipt is signed and split, so it is printed twice on one sheet.
    # The plain monthly sheet is not signed: one copy is enough.
    if payout:
        _copy(document, data, "Exemplaire académie", usable)
        _text(
            document,
            "✂ " + "- " * 60,
            size=7,
            colour=GREY,
            leading=11,
            before=2,
            after=2,
        )
        _copy(document, data, "Exemplaire professeur", usable)
    else:
        _copy(document, data, None, usable)

    # Word's trailing paragraph is enough to tip the page over on its own.
    last = document.add_paragraph()
    last.paragraph_format.line_spacing = Pt(1)
    last.paragraph_format.space_before = Pt(0)
    last.paragraph_format.space_after = Pt(0)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _copy(doc, data, marker: str | None, usable: int) -> None:
    """One copy, inside a container of exactly H_BODY + H_SIGNATURE."""
    container = doc.add_table(rows=2, cols=1)
    _widths(container, [usable])
    _table_borders(container)
    _cell_margins(container, left=0, right=0)

    _exact_height(container.rows[0], H_BODY)
    _body(container.rows[0].cells[0], data, marker, usable)

    _exact_height(container.rows[1], H_SIGNATURE)
    _signatures(container.rows[1].cells[0], usable)


def _body(cell, data, marker: str | None, usable: int) -> None:
    cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    first = cell.paragraphs[0]
    if marker:
        _text(
            None,
            marker.upper(),
            size=7,
            bold=True,
            colour=GREY,
            leading=9,
            paragraph=first,
        )

    title = ("Reçu de versement — " if data["verse"] else "Fiche de paie — ") + data[
        "mois"
    ]
    _text(cell, title, size=13, bold=True, leading=16, before=1)
    _text(cell, data["academie"], size=8, colour=GREY, leading=10)
    _text(
        cell,
        f"Professeur : {data['professeur']}"
        + (f"    Téléphone : {data['telephone']}" if data["telephone"] else ""),
        size=8,
        leading=10,
    )

    # What has just been handed to him, before anything else: it is the
    # reason the paper he signs exists.
    if data["verse"]:
        _text(
            cell,
            f"Versé ce jour ({data['date']}) : {data['verse']}",
            size=11,
            bold=True,
            leading=14,
            before=4,
            after=3,
        )
        if data["note"]:
            _text(cell, data["note"], size=7.5, colour=GREY, leading=9)

    _class_table(cell, data["classes"], usable)

    _text(
        cell, f"Dû pour le mois : {data['du']}", size=9, bold=True, leading=12, before=5
    )
    _text(cell, f"Déjà versé : {data['deja_verse']}", size=9, leading=12)
    _text(cell, f"Reste à verser : {data['reste']}", size=9, bold=True, leading=12)

    _text(
        cell,
        "Le détail par classe suit les élèves inscrits du mois — un élève qui"
        " n'a pas encore payé ne change rien à ce qui est dû au professeur.",
        size=6.5,
        colour=GREY,
        leading=8,
        before=4,
    )
    if data["verse"]:
        _text(
            cell,
            "Reçu pour solde de ce versement. Le reste à verser, s'il y en a,"
            " fera l'objet d'un autre reçu.",
            size=6.5,
            colour=GREY,
            leading=8,
        )


def _class_table(cell, classes: list[dict], usable: int) -> None:
    first = int(usable * 0.34)
    second = int(usable * 0.34)
    third = int(usable * 0.12)
    columns = [first, second, third, usable - first - second - third]

    lines = list(classes)
    if len(lines) > MAX_ROWS:
        # The extras collapse into one line -- CARRYING THEIR TOTAL, so the
        # money column still adds up to the figure below it. A « + 7 autres
        # classes » row with an empty amount would leave the reader of a
        # signed paper unable to check the sum.
        overflow = lines[MAX_ROWS - 1 :]
        lines = lines[: MAX_ROWS - 1]
        lines.append(
            {
                "classe": f"+ {len(overflow)} autres classes",
                "niveau": "",
                "inscrits": str(sum(int(item["inscrits"]) for item in overflow)),
                "montant": sum(item["montant"] for item in overflow),
            }
        )

    table = cell.add_table(rows=MAX_ROWS + 1, cols=4)
    _widths(table, columns)
    # Three lines and no more: one above the headings, one under them, and
    # one closing the table. A rule between every class turned a short list
    # into a grid to decipher, and boxed the reserved empty rows as though
    # they were missing data.
    _table_borders(table, top=8, bottom=8)
    _cell_margins(table, left=50, right=50)

    header = table.rows[0]
    _exact_height(header, 240)
    _row_bottom_border(header)
    headings = (
        ("Classe", None),
        ("Niveau", None),
        ("Inscrits", WD_ALIGN_PARAGRAPH.CENTER),
        ("Montant", WD_ALIGN_PARAGRAPH.RIGHT),
    )
    for index, (label, align) in enumerate(headings):
        _cell_text(
            header.cells[index], label, size=7.5, bold=True, align=align, colour=GREY
        )

    for index in range(MAX_ROWS):
        row = table.rows[index + 1]
        _exact_height(row, 230)
        if index >= len(lines):
            # A blank row: it reserves the height so the sheet cannot shrink.
            for blank in row.cells:
                _cell_text(blank, "", 8)
            continue
        item = lines[index]
        _cell_text(row.cells[0], _clip(item["classe"], MAX_CHARS_CLASS), 8)
        _cell_text(row.cells[1], _clip(item["niveau"], MAX_CHARS_LEVEL), 8, colour=GREY)
        _cell_text(row.cells[2], item["inscrits"], 8, align=WD_ALIGN_PARAGRAPH.CENTER)
        _cell_text(
            row.cells[3], _dh(item["montant"]), 8, align=WD_ALIGN_PARAGRAPH.RIGHT
        )


def _signatures(cell, usable: int) -> None:
    cell.vertical_alignment = WD_ALIGN_VERTICAL.BOTTOM
    half = usable // 2
    table = cell.add_table(rows=2, cols=2)
    _widths(table, [half, usable - half])
    _table_borders(table)
    _cell_margins(table, left=0, right=120)

    _exact_height(table.rows[0], 700)  # room to actually sign
    for blank in table.rows[0].cells:
        _cell_text(blank, "", 8)

    _exact_height(table.rows[1], 200)
    labels = ("Signature du professeur", "Signature de l'académie")
    for target, label in zip(table.rows[1].cells, labels, strict=True):
        properties = target._tc.get_or_add_tcPr()
        borders = OxmlElement("w:tcBorders")
        borders.append(_el("w:top", val="single", sz=6, space=0, color="777777"))
        properties.append(borders)
        _cell_text(target, label, size=7.5, colour=GREY)

    trailing = cell.add_paragraph()
    trailing.paragraph_format.space_before = Pt(0)
    trailing.paragraph_format.space_after = Pt(0)
    trailing.paragraph_format.line_spacing = Pt(1)


def _payout(conn: sqlite3.Connection, payout_id: int, teacher_id: int) -> dict:
    """The named payout -- and it must really have been made TO THIS
    teacher: a receipt attests, it is not copied from somebody else's."""
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
