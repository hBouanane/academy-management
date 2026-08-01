"""Round 6 (client feedback): student identity, profile, gift-zero — TDD first."""

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


class TestStudentIdentity:
    def test_student_carries_full_identity_and_tagged_phones(self, client):
        level = client.get("/api/levels").json()[0]["id"]
        response = client.post(
            "/api/students",
            json={
                "name": "Bouanane",
                "first_name": "Haitam",
                "level_id": level,
                "annee": 3,
                "filiere": "Sciences Maths",
                "school": "Lycée Al Khawarizmi",
                "phones": [
                    {"tag": "étudiant", "number": "06 61 23 45 67"},
                    {"tag": "père", "number": "0662334455"},
                ],
            },
        )
        assert response.status_code == 201, response.text
        (row,) = client.get("/api/students").json()
        assert row["first_name"] == "Haitam"
        assert row["annee"] == 3
        assert row["filiere"] == "Sciences Maths"
        assert row["school_name"] == "Lycée Al Khawarizmi"
        assert row["created_at"] is not None
        assert row["phone"] == "0661234567"  # primary phone stays denormalized

    def test_each_tagged_phone_is_validated(self, client):
        level = client.get("/api/levels").json()[0]["id"]
        response = client.post(
            "/api/students",
            json={
                "name": "Sami",
                "level_id": level,
                "phones": [{"tag": "mère", "number": "123"}],
            },
        )
        assert response.status_code == 422
        assert "10 chiffres" in response.text

    def test_schools_are_a_managed_list(self, client):
        level = client.get("/api/levels").json()[0]["id"]
        for name in ("Sami", "Lina"):
            client.post(
                "/api/students",
                json={"name": name, "level_id": level, "school": "École Atlas"},
            )
        schools = client.get("/api/schools").json()
        assert [school["name"] for school in schools] == ["École Atlas"]

    def test_profile_shows_identity_phones_and_month_history(self, client):
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id)
        client.patch(
            f"/api/students/{student}",
            json={"phones": [{"tag": "père", "number": "0663445566"}]},
        )
        client.post("/api/payments", json={"enrollment_id": enrollment})
        profile = client.get(f"/api/students/{student}/profile").json()
        assert profile["name"] == "Sami"
        assert profile["phones"] == [{"tag": "père", "number": "0663445566"}]
        (month,) = profile["months"]
        assert month["month"] == "2026-09"
        assert month["paid"] is True
        assert month["net_centimes"] == 300 * DH
        assert month["subjects"] == ["Math"]

    def test_profile_survives_archiving(self, client):
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        client.patch(f"/api/students/{student}", json={"is_active": False})
        profile = client.get(f"/api/students/{student}/profile").json()
        assert profile["is_active"] == 0
        assert len(profile["months"]) == 1  # history intact

    def test_filieres_used_become_reusable_suggestions(self, client):
        level = client.get("/api/levels").json()[-1]["id"]  # Lycée
        for name, filiere in (
            ("A", "Sciences Maths"),
            ("B", "Lettres"),
            ("C", "Sciences Maths"),
        ):
            client.post(
                "/api/students",
                json={"name": name, "level_id": level, "annee": 3, "filiere": filiere},
            )
        assert client.get("/api/filieres").json() == ["Lettres", "Sciences Maths"]

    def test_students_expose_the_pre_inscrit_state(self, client):
        level, class_id, _, package = setup_base(client)
        enroll(client, level, package, class_id)
        client.post("/api/students", json={"name": "Nora", "level_id": level})
        rows = {row["name"]: row for row in client.get("/api/students").json()}
        assert rows["Nora"]["ever_enrolled"] == 0  # pré-inscrit
        assert rows["Sami"]["ever_enrolled"] == 1


class TestPreviewMonth:
    def test_preview_names_the_month_being_paid(self, client):
        # The pay dialog must say WHICH month the money is for.
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id, month="2026-10")
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        assert preview["month"] == "2026-10"


class TestGiftZeroForEveryone:
    def test_gifted_month_pays_nobody(self, client):
        # Client rule: on a mois offert, professors, salle AND académie get 0.
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        gift = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={"kind": "percent", "value": 10_000, "category": "gift"},
        )
        assert gift.status_code == 201, gift.text
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        assert preview["net_centimes"] == 0
        assert all(line["final_centimes"] == 0 for line in preview["lines"])
        paid = client.post("/api/payments", json={"enrollment_id": enrollment})
        assert paid.status_code == 201, paid.text


class TestNegativeShareIsAWarningOnly:
    def test_over_cap_sponsor_part_is_accepted(self, client):
        # Client rule: warn in the UI, never block the money.
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        response = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={
                "kind": "amount",
                "value": 70 * DH,
                "bearers": [
                    {"kind": "owner", "ref_id": 1, "share_centimes": 50 * DH},
                    {"kind": "teacher", "ref_id": teacher, "share_centimes": 20 * DH},
                ],
            },
        )
        assert response.status_code == 201, response.text
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        owner = next(line for line in preview["lines"] if line["kind"] == "owner")
        assert owner["final_centimes"] == -20 * DH
        paid = client.post("/api/payments", json={"enrollment_id": enrollment})
        assert paid.status_code == 201, paid.text


class TestBackfill:
    def test_enrolling_a_past_month_is_allowed_and_owed(self, client):
        # Paper-lag reality: he really started in August, entered in September.
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id, month="2026-08")
        assert client.get(f"/api/enrollments/{enrollment}/preview").status_code == 200
        (entry,) = client.get(
            "/api/reports/arrears", params={"up_to_month": "2026-09"}
        ).json()
        assert entry["items"][0]["month"] == "2026-08"
