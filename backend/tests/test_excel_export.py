"""Excel export tests: download through the API, re-open, assert — written first."""

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.adapters.api.app import create_app

DH = 100


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def build_month(client):
    levels = client.get("/api/levels").json()
    primaire = next(level["id"] for level in levels if level["name"] == "Primaire")
    subject = client.post(
        "/api/subjects", json={"name": "Math", "level_id": primaire}
    ).json()["id"]
    teacher = client.post("/api/teachers", json={"name": "Ahmed"}).json()["id"]
    class_id = client.post(
        "/api/classes",
        json={"level_id": primaire, "subject_id": subject, "teacher_id": teacher},
    ).json()["id"]
    package = client.post(
        "/api/packages", json={"subject_count": 1, "monthly_price_centimes": 300 * DH}
    ).json()["id"]

    def enroll(name, month):
        student = client.post(
            "/api/students", json={"name": name, "level_id": primaire}
        ).json()["id"]
        return client.post(
            "/api/enrollments",
            json={
                "student_id": student,
                "month": month,
                "package_id": package,
                "class_ids": [class_id],
            },
        ).json()["id"]

    paid = enroll("Sami", "2026-09")
    client.post(
        f"/api/enrollments/{paid}/adjustments",
        json={"kind": "amount", "value": 50 * DH},
    )
    client.post("/api/payments", json={"enrollment_id": paid})
    enroll("Lina", "2026-08")  # unpaid, previous month -> arrears


def download(client, month="2026-09"):
    response = client.get(f"/api/export/monthly.xlsx?month={month}")
    assert response.status_code == 200, response.text
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return load_workbook(io.BytesIO(response.content))


def test_workbook_has_level_summary_and_arrears_sheets(client):
    build_month(client)
    workbook = download(client)
    assert "Primaire" in workbook.sheetnames
    assert "Répartition" in workbook.sheetnames
    assert "Impayés" in workbook.sheetnames


def test_level_sheet_lists_students_with_net_and_status(client):
    build_month(client)
    sheet = download(client)["Primaire"]
    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    sami = next(row for row in rows if row[0] == "Sami")
    assert sami[1] == "Math"  # subjects
    assert sami[2] == 300  # price in DH
    assert sami[3] == 250  # net after the 50 DH discount
    assert sami[4] == "Payé"


def test_summary_sheet_matches_the_ledger(client):
    build_month(client)
    sheet = download(client)["Répartition"]
    values = {
        row[0]: row[2]
        for row in sheet.iter_rows(min_row=2, values_only=True)
        if row[0] is not None
    }
    # 300 base split: venue 90 / owner 30 / Ahmed 180; owner absorbs 50.
    assert values["Ahmed"] == 180
    assert values["Salle principale"] == 90
    assert values["Mon académie"] == -20
    assert sheet["B1"].value == 250  # cash-in in DH


def test_summary_sheet_aggregates_the_owner_teacher(client):
    # The owner also teaches math: one combined line shows their real income.
    build_month(client)
    (ahmed,) = [t for t in client.get("/api/teachers").json() if t["name"] == "Ahmed"]
    client.patch(f"/api/teachers/{ahmed['id']}", json={"is_owner": True})
    sheet = download(client)["Répartition"]
    values = {
        row[0]: row[2]
        for row in sheet.iter_rows(min_row=2, values_only=True)
        if row[0] is not None
    }
    # Ahmed wears both hats: 180 as teacher + (30 - 50) as owner = 160.
    assert values["Ahmed (propriétaire + professeur)"] == 160


def test_arrears_sheet_lists_who_owes(client):
    build_month(client)
    sheet = download(client)["Impayés"]
    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    assert rows[0][0] == "Lina"
    assert rows[0][2] == "2026-08"
    assert rows[0][3] == 300


def test_export_of_empty_month_still_produces_a_workbook(client):
    workbook = download(client, month="2026-01")
    assert "Répartition" in workbook.sheetnames


def test_deactivated_student_still_appears_on_past_month_export(client):
    build_month(client)
    (sami,) = [s for s in client.get("/api/students").json() if s["name"] == "Sami"]
    client.patch(f"/api/students/{sami['id']}", json={"is_active": False})
    sheet = download(client)["Primaire"]
    names = [row[0] for row in sheet.iter_rows(min_row=2, values_only=True)]
    assert "Sami" in names  # archival record must not rewrite history


def test_sheet_titles_are_excel_safe():
    from app.adapters.excel.monthly_workbook import _sheet_title

    assert _sheet_title("CE1/CE2") == "CE1-CE2"
    assert _sheet_title("Répartition") == "Répartition (niveau)"
    assert len(_sheet_title("N" * 40)) == 31
