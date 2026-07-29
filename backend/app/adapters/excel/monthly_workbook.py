"""Monthly Excel export mirroring the client's legacy workbook.

One sheet per school level (students, subjects, price, net, status), a
Répartition sheet (who receives what, from the ledger), and an Impayés
sheet. This file is the client's backup and his exit strategy: if he ever
abandons the app, this workbook is his old system back.
"""

import sqlite3
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

from app.adapters.sqlite import crud
from app.adapters.sqlite.reports import arrears, monthly_report

_BOLD = Font(bold=True)

KIND_LABEL = {"teacher": "Professeur", "owner": "Propriétaire", "venue": "Salle"}


def monthly_workbook(conn: sqlite3.Connection, academy_id: int, month: str) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    _level_sheets(workbook, conn, academy_id, month)
    _summary_sheet(workbook, conn, academy_id, month)
    _arrears_sheet(workbook, conn, academy_id, month)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _dh(centimes: int) -> float:
    return round(centimes / 100, 2)


def _level_sheets(
    workbook: Workbook, conn: sqlite3.Connection, academy_id: int, month: str
) -> None:
    enrolled = [
        row for row in crud.month_overview(conn, academy_id, month) if row["enrollment"]
    ]
    by_level: dict[str, list[dict]] = {}
    for row in enrolled:
        by_level.setdefault(row["level_name"], []).append(row)
    for level_name, rows in by_level.items():
        sheet = workbook.create_sheet(title=level_name[:31])
        _header(sheet, ["Étudiant", "Matières", "Prix (DH)", "Net (DH)", "Statut"])
        for row in rows:
            enrollment = row["enrollment"]
            sheet.append(
                [
                    row["student_name"],
                    ", ".join(c["subject_name"] for c in enrollment["classes"]),
                    _dh(enrollment["price_centimes"]),
                    _dh(enrollment["net_centimes"]),
                    "Payé" if enrollment["paid"] else "Impayé",
                ]
            )


def _summary_sheet(
    workbook: Workbook, conn: sqlite3.Connection, academy_id: int, month: str
) -> None:
    report = monthly_report(conn, academy_id, month)
    sheet = workbook.create_sheet(title="Répartition")
    sheet["A1"] = f"Encaissé {month} (DH)"
    sheet["A1"].font = _BOLD
    sheet["B1"] = _dh(report.cash_in)
    _append_totals(sheet, report.totals)
    for level in report.by_level:
        sheet.append([])
        title_row = sheet.max_row + 1
        sheet.cell(row=title_row, column=1, value=level.level_name).font = _BOLD
        _append_totals(sheet, level.totals, with_header=False)


def _append_totals(sheet: Worksheet, totals, with_header: bool = True) -> None:
    if with_header:
        row = sheet.max_row + 1
        for column, value in enumerate(
            ["Bénéficiaire", "Rôle", "Montant (DH)"], start=1
        ):
            sheet.cell(row=row, column=column, value=value).font = _BOLD
    for total in totals:
        sheet.append([total.name, KIND_LABEL[total.kind], _dh(total.total)])


def _arrears_sheet(
    workbook: Workbook, conn: sqlite3.Connection, academy_id: int, month: str
) -> None:
    sheet = workbook.create_sheet(title="Impayés")
    _header(sheet, ["Étudiant", "Niveau", "Mois", "Montant dû (DH)"])
    for entry in arrears(conn, academy_id, month):
        for item in entry.items:
            sheet.append(
                [entry.student_name, entry.level_name, item.month, _dh(item.owed)]
            )


def _header(sheet: Worksheet, titles: list[str]) -> None:
    sheet.append(titles)
    for cell in sheet[1]:
        cell.font = _BOLD
