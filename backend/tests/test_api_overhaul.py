"""API additions for the UX overhaul — written first (TDD)."""

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.app import create_app

DH = 100


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def setup_enrollment(client, price_dh=300, with_discount=0):
    levels = client.get("/api/levels").json()
    primaire = next(level["id"] for level in levels if level["name"] == "Primaire")
    subject = client.post("/api/subjects", json={"name": "Math"}).json()["id"]
    teacher = client.post("/api/teachers", json={"name": "Ahmed"}).json()["id"]
    class_id = client.post(
        "/api/classes",
        json={"level_id": primaire, "subject_id": subject, "teacher_id": teacher},
    ).json()["id"]
    package = client.post(
        "/api/packages",
        json={"subject_count": 1, "monthly_price_centimes": price_dh * DH},
    ).json()["id"]
    student = client.post(
        "/api/students", json={"name": "Sami", "level_id": primaire}
    ).json()["id"]
    enrollment = client.post(
        "/api/enrollments",
        json={
            "student_id": student,
            "month": "2026-09",
            "package_id": package,
            "class_ids": [class_id],
        },
    ).json()["id"]
    if with_discount:
        client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={"kind": "amount", "value": with_discount * DH, "reason": "aide"},
        )
    return enrollment, teacher


class TestPaymentPreview:
    def test_preview_shows_the_split_before_paying(self, client):
        enrollment, _ = setup_enrollment(client)
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        assert preview["price_centimes"] == 300 * DH
        assert preview["net_centimes"] == 300 * DH
        lines = {line["name"]: line for line in preview["lines"]}
        assert lines["Salle principale"]["final_centimes"] == 90 * DH
        assert lines["Mon académie"]["final_centimes"] == 30 * DH
        assert lines["Ahmed"]["final_centimes"] == 180 * DH
        assert sum(line["final_centimes"] for line in preview["lines"]) == 300 * DH

    def test_preview_reflects_adjustments_with_their_ids(self, client):
        enrollment, _ = setup_enrollment(client, with_discount=50)
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        assert preview["net_centimes"] == 250 * DH
        (adjustment,) = preview["adjustments"]
        assert adjustment["resolved_centimes"] == 50 * DH
        assert adjustment["reason"] == "aide"
        assert adjustment["id"] > 0
        lines = {line["name"]: line for line in preview["lines"]}
        assert lines["Mon académie"]["final_centimes"] == -20 * DH  # owner bears it
        assert sum(line["final_centimes"] for line in preview["lines"]) == 250 * DH

    def test_bearer_specific_adjustment_reduces_that_share(self, client):
        enrollment, teacher = setup_enrollment(client)
        client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={
                "kind": "amount",
                "value": 30 * DH,
                "bearers": [{"kind": "teacher", "ref_id": teacher}],
            },
        )
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        lines = {line["name"]: line for line in preview["lines"]}
        assert lines["Ahmed"]["final_centimes"] == 150 * DH  # 180 - 30
        assert lines["Mon académie"]["final_centimes"] == 30 * DH  # untouched

    def test_preview_of_unknown_enrollment_is_404(self, client):
        assert client.get("/api/enrollments/404/preview").status_code == 404

    def test_preview_fails_loudly_when_a_bearer_lost_its_allocation(self, client):
        # Manual teacher-borne reduction, then the class changes teacher:
        # the preview must 422 like posting would, never show a false split.
        enrollment, teacher = setup_enrollment(client)
        client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={
                "kind": "amount",
                "value": 30 * DH,
                "bearers": [{"kind": "teacher", "ref_id": teacher}],
            },
        )
        other = client.post("/api/teachers", json={"name": "Sara"}).json()["id"]
        (class_row,) = client.get("/api/classes").json()
        client.patch(f"/api/classes/{class_row['id']}", json={"teacher_id": other})
        assert client.get(f"/api/enrollments/{enrollment}/preview").status_code == 422

    def test_clearing_a_phone_actually_clears_it(self, client):
        teacher = client.post(
            "/api/teachers", json={"name": "Ahmed", "phone": "0600112233"}
        ).json()["id"]
        client.patch(f"/api/teachers/{teacher}", json={"phone": ""})
        (row,) = client.get("/api/teachers").json()
        assert row["phone"] is None


class TestEntityLifecycle:
    @pytest.mark.parametrize(
        ("collection", "create_body", "patch_body"),
        [
            # Matières left this list on purpose: they can no longer be
            # archived — only renamed, or deleted while class-free (v9).
            (
                "teachers",
                {"name": "Ahmed"},
                {"name": "Ahmed B.", "phone": "0600112233"},
            ),
            (
                "packages",
                {"subject_count": 1, "monthly_price_centimes": 100},
                {"monthly_price_centimes": 200},
            ),
        ],
    )
    def test_entities_can_be_renamed_and_archived(
        self, client, collection, create_body, patch_body
    ):
        entity_id = client.post(f"/api/{collection}", json=create_body).json()["id"]
        patched = client.patch(f"/api/{collection}/{entity_id}", json=patch_body)
        assert patched.status_code == 200, patched.text

        archived = client.patch(
            f"/api/{collection}/{entity_id}", json={"is_active": False}
        )
        assert archived.status_code == 200
        assert client.get(f"/api/{collection}").json() == []
        everyone = client.get(
            f"/api/{collection}", params={"include_inactive": True}
        ).json()
        assert len(everyone) == 1
        assert everyone[0]["is_active"] == 0

    def test_classes_can_be_archived(self, client):
        _, _ = setup_enrollment(client)
        (row,) = client.get("/api/classes").json()
        archived = client.patch(f"/api/classes/{row['id']}", json={"is_active": False})
        assert archived.status_code == 200
        assert client.get("/api/classes").json() == []

    def test_patching_unknown_entity_is_404(self, client):
        assert client.patch("/api/subjects/999", json={"name": "X"}).status_code == 404


class TestLevelData:
    def test_overview_rows_carry_the_student_level_id(self, client):
        setup_enrollment(client)
        (row,) = client.get("/api/months/2026-09/overview").json()
        levels = client.get("/api/levels").json()
        primaire = next(level["id"] for level in levels if level["name"] == "Primaire")
        assert row["level_id"] == primaire
