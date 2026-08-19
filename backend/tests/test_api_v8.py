"""Round 8: user-managed niveaux with teaching structure — TDD first."""

import pytest
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


class TestCustomLevels:
    def test_seeded_levels_declare_their_teaching_structure(self, client):
        levels = {
            lv["name"]: lv["teaching_annees"] for lv in client.get("/api/levels").json()
        }
        assert levels == {"Primaire": 0, "Collège": 3, "Lycée": 3, "Formation": 0}

    def test_the_client_can_add_a_niveau(self, client):
        created = client.post(
            "/api/levels", json={"name": "Soutien", "teaching_annees": 0}
        )
        assert created.status_code == 201, created.text
        created = client.post(
            "/api/levels", json={"name": "Langues", "teaching_annees": 4}
        )
        assert created.status_code == 201, created.text
        levels = client.get("/api/levels").json()
        assert [lv["name"] for lv in levels][-2:] == ["Soutien", "Langues"]
        assert levels[-1]["teaching_annees"] == 4

    def test_duplicate_niveau_names_are_refused_in_french(self, client):
        response = client.post(
            "/api/levels", json={"name": "Primaire", "teaching_annees": 0}
        )
        assert response.status_code == 422
        assert "existe déjà" in response.json()["detail"]


class TestSubjectsPerNiveau:
    def test_same_matiere_name_lives_once_per_niveau(self, client):
        levels = {lv["name"]: lv["id"] for lv in client.get("/api/levels").json()}
        first = client.post(
            "/api/subjects",
            json={"name": "Mathématique", "level_id": levels["Primaire"]},
        )
        assert first.status_code == 201, first.text
        second = client.post(
            "/api/subjects",
            json={"name": "Mathématique", "level_id": levels["Collège"]},
        )
        assert second.status_code == 201, second.text  # the copy IS a new row
        again = client.post(
            "/api/subjects",
            json={"name": "Mathématique", "level_id": levels["Primaire"]},
        )
        assert again.status_code == 409  # same niveau: already there
        rows = client.get("/api/subjects").json()
        assert [(row["name"], row["level_id"]) for row in rows] == [
            ("Mathématique", levels["Primaire"]),
            ("Mathématique", levels["Collège"]),
        ]
        assert rows[0]["level_name"] == "Primaire"


class TestRecurringAdjustments:
    def test_recurring_reduction_follows_the_next_month(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={"kind": "amount", "value": 50 * DH, "recurring": True},
        )
        monkeypatch_month(client, "2026-10")
        rows = client.get("/api/months/2026-10/overview").json()
        (row,) = [r for r in rows if r["enrollment"] is not None]
        assert row["enrollment"]["net_centimes"] == 250 * DH  # reduction followed
        preview = client.get(
            f"/api/enrollments/{row['enrollment']['id']}/preview"
        ).json()
        (adjustment,) = preview["adjustments"]
        assert adjustment["recurring"] == 1

    def test_one_shot_reduction_stays_in_its_month(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={"kind": "amount", "value": 50 * DH, "recurring": False},
        )
        monkeypatch_month(client, "2026-10")
        rows = client.get("/api/months/2026-10/overview").json()
        (row,) = [r for r in rows if r["enrollment"] is not None]
        assert row["enrollment"]["net_centimes"] == 300 * DH  # full price again

    def test_recurring_gift_keeps_paying_nobody(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={
                "kind": "percent",
                "value": 10_000,
                "category": "gift",
                "recurring": True,
            },
        )
        monkeypatch_month(client, "2026-10")
        rows = client.get("/api/months/2026-10/overview").json()
        (row,) = [r for r in rows if r["enrollment"] is not None]
        preview = client.get(
            f"/api/enrollments/{row['enrollment']['id']}/preview"
        ).json()
        assert preview["net_centimes"] == 0
        assert all(line["final_centimes"] == 0 for line in preview["lines"])


def monkeypatch_month(client, month):
    """Move the app's clock then extend the agenda like the dashboard does."""
    from app.services import clock as clock_module

    clock_module.current_month = lambda: month
    assert client.post(f"/api/months/{month}/ensure").status_code == 200


class TestOwnerCombinedProfile:
    def test_owner_teacher_profile_carries_both_incomes(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.patch(f"/api/teachers/{teacher}", json={"is_owner": True})
        client.post("/api/payments", json={"enrollment_id": enrollment})
        profile = client.get(
            f"/api/teachers/{teacher}/profile", params={"month": "2026-09"}
        ).json()
        assert profile["is_owner"] == 1
        assert profile["owner_earned"] == 30 * DH  # 10% of 300 as owner
        assert profile["history"][-1]["earned"] == 180 * DH  # as professor


class TestClassNameCollision:
    def test_same_teacher_same_matiere_in_two_annees(self, client):
        # The screenshot bug: UNIQUE(level, subject, teacher, name) exploded
        # when one prof opened the same matière in two années.
        levels = {lv["name"]: lv["id"] for lv in client.get("/api/levels").json()}
        subject = client.post(
            "/api/subjects",
            json={"name": "Mathématique", "level_id": levels["Collège"]},
        ).json()["id"]
        teacher = client.post("/api/teachers", json={"name": "Haitam"}).json()["id"]

        def open_class(annee, parcours=None):
            return client.post(
                "/api/classes",
                json={
                    "level_id": levels["Collège"],
                    "subject_id": subject,
                    "teacher_id": teacher,
                    "annee": annee,
                    "parcours": parcours,
                },
            )

        assert open_class(1).status_code == 201
        assert open_class(2).status_code == 201
        assert open_class(3, "Normal").status_code == 201
        assert open_class(3, "Râ'ida").status_code == 201
        assert len(client.get("/api/classes").json()) == 4
