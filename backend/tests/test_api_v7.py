"""Round 7: class taxonomy, capabilities, succession money, profiles — TDD first."""

import io

import pytest
from docx import Document
from fastapi.testclient import TestClient
from test_api_v4 import enroll, setup_base

from app.adapters.api.app import create_app
from app.services import clock

DH = 100


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def teacher_totals(client, month):
    report = client.get("/api/reports/monthly", params={"month": month}).json()
    return {
        total["name"]: total["total"]
        for total in report["totals"]
        if total["kind"] == "teacher"
    }


class TestTaxonomy:
    def test_formation_niveau_is_seeded(self, client):
        names = [level["name"] for level in client.get("/api/levels").json()]
        assert names == ["Primaire", "Collège", "Lycée", "Formation"]

    def test_class_carries_annee_filiere_parcours(self, client):
        levels = {lv["name"]: lv["id"] for lv in client.get("/api/levels").json()}
        subject = client.post(
            "/api/subjects",
            json={"name": "Math", "level_id": levels["Collège"]},
        ).json()["id"]
        teacher = client.post("/api/teachers", json={"name": "Ahmed"}).json()["id"]
        created = client.post(
            "/api/classes",
            json={
                "level_id": levels["Collège"],
                "subject_id": subject,
                "teacher_id": teacher,
                "annee": 3,
                "parcours": "Râ'ida",
            },
        )
        assert created.status_code == 201, created.text
        (row,) = client.get("/api/classes").json()
        assert row["annee"] == 3
        assert row["parcours"] == "Râ'ida"
        assert row["filiere"] is None

    def test_student_parcours_reaches_the_overview(self, client):
        level, class_id, _, package = setup_base(client)
        student = client.post(
            "/api/students",
            json={
                "name": "Sami2",
                "level_id": level,
                "annee": 3,
                "parcours": "Râ'ida",
                "filiere": "Sciences Maths",
            },
        ).json()["id"]
        client.post(
            "/api/enrollments",
            json={
                "student_id": student,
                "month": "2026-09",
                "package_id": package,
                "class_ids": [class_id],
            },
        )
        rows = client.get("/api/months/2026-09/overview").json()
        row = next(r for r in rows if r["student_id"] == student)
        assert row["annee"] == 3
        assert row["parcours"] == "Râ'ida"
        assert row["filiere"] == "Sciences Maths"

    def test_teachers_carry_their_creation_date(self, client):
        client.post("/api/teachers", json={"name": "Ahmed"})
        (row,) = client.get("/api/teachers").json()
        assert row["created_at"] is not None


class TestCapabilities:
    def test_capabilities_replace_and_list(self, client):
        levels = {lv["name"]: lv["id"] for lv in client.get("/api/levels").json()}
        subject = client.post(
            "/api/subjects",
            json={"name": "Math", "level_id": levels["Collège"]},
        ).json()["id"]
        teacher = client.post("/api/teachers", json={"name": "Ahmed"}).json()["id"]
        put = client.put(
            f"/api/teachers/{teacher}/capabilities",
            json={
                "items": [
                    {"level_id": levels["Primaire"], "subject_id": subject},
                    {
                        "level_id": levels["Collège"],
                        "annee": 3,
                        "parcours": "Râ'ida",
                        "subject_id": subject,
                    },
                ]
            },
        )
        assert put.status_code == 200, put.text
        rows = client.get("/api/capabilities").json()
        assert len(rows) == 2
        assert all(row["teacher_id"] == teacher for row in rows)

    def test_creating_a_class_records_the_capability(self, client):
        # A class someone teaches is proof of capability — no double entry.
        setup_base(client)
        (row,) = client.get("/api/capabilities").json()
        assert row["annee"] is None  # Primaire class, whole-niveau capability


class TestSuccession:
    def test_money_follows_who_taught_each_month(self, client):
        level, class_id, _, package = setup_base(client)
        _, august = enroll(client, level, package, class_id, month="2026-08")
        _, september = enroll(
            client, level, package, class_id, name="Lina", month="2026-09"
        )
        sara = client.post("/api/teachers", json={"name": "Sara"}).json()["id"]
        replaced = client.post(
            f"/api/classes/{class_id}/replace-teacher",
            json={"date": "2026-09-21", "successor_ids": [sara]},
        )
        assert replaced.status_code == 200, replaced.text
        (class_row,) = client.get("/api/classes").json()
        assert class_row["teacher_id"] == sara
        # August was taught entirely by Ahmed — paying it now still pays HIM.
        client.post("/api/payments", json={"enrollment_id": august})
        assert teacher_totals(client, "2026-08") == {"Ahmed": 180 * DH}
        # September splits by days taught: Ahmed 20/30, Sara 10/30 of 180 DH.
        client.post("/api/payments", json={"enrollment_id": september})
        assert teacher_totals(client, "2026-09") == {
            "Ahmed": 120 * DH,
            "Sara": 60 * DH,
        }

    def test_replacement_by_two_co_teachers(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        sara = client.post("/api/teachers", json={"name": "Sara"}).json()["id"]
        karim = client.post("/api/teachers", json={"name": "Karim"}).json()["id"]
        client.post(
            f"/api/classes/{class_id}/replace-teacher",
            json={"date": "2026-09-01", "successor_ids": [sara, karim]},
        )
        client.post("/api/payments", json={"enrollment_id": enrollment})
        assert teacher_totals(client, "2026-09") == {
            "Sara": 90 * DH,
            "Karim": 90 * DH,
        }

    def test_direct_teacher_edit_is_a_correction_not_a_handover(self, client):
        # The pencil fixes a mistake: the new name applies to the whole past.
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        sara = client.post("/api/teachers", json={"name": "Sara"}).json()["id"]
        client.patch(f"/api/classes/{class_id}", json={"teacher_id": sara})
        client.post("/api/payments", json={"enrollment_id": enrollment})
        assert teacher_totals(client, "2026-09") == {"Sara": 180 * DH}


class TestGroups:
    def test_duplicate_creates_the_next_group(self, client):
        _, class_id, teacher, _ = setup_base(client)
        sara = client.post("/api/teachers", json={"name": "Sara"}).json()["id"]
        duplicated = client.post(
            f"/api/classes/{class_id}/duplicate", json={"teacher_id": sara}
        )
        assert duplicated.status_code == 201, duplicated.text
        rows = client.get("/api/classes").json()
        names = {row["name"]: row["teacher_id"] for row in rows}
        assert names == {"A": teacher, "B": sara}


class TestTeacherProfile:
    def test_profile_lists_classes_counts_and_earnings(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        profile = client.get(
            f"/api/teachers/{teacher}/profile", params={"month": "2026-09"}
        ).json()
        assert profile["name"] == "Ahmed"
        assert profile["created_at"] is not None
        (class_row,) = profile["classes"]
        assert class_row["enrolled_count"] == 1
        assert class_row["earned_centimes"] == 180 * DH
        assert profile["history"][-1] == {"month": "2026-09", "earned": 180 * DH}
        assert len(profile["capabilities"]) == 1


class TestAbsenceSheet:
    def test_absence_docx_lists_enrolled_students(self, client):
        level, class_id, _, package = setup_base(client)
        enroll(client, level, package, class_id)
        response = client.get(
            f"/api/classes/{class_id}/absence.docx", params={"month": "2026-09"}
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.wordprocessingml"
        )
        document = Document(io.BytesIO(response.content))
        table_text = "\n".join(
            cell.text
            for table in document.tables
            for row in table.rows
            for cell in row.cells
        )
        assert "Sami" in table_text
        titles = "\n".join(paragraph.text for paragraph in document.paragraphs)
        assert "Liste d'absence" in titles
        assert "Math" in titles
