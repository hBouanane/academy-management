"""UX v3 API additions — written first (TDD)."""

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.app import create_app
from app.services import clock

DH = 100


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def setup_level_class(client, level_name="Primaire", subject="Math", teacher="Ahmed"):
    levels = client.get("/api/levels").json()
    level = next(lv["id"] for lv in levels if lv["name"] == level_name)
    subject_id = client.post("/api/subjects", json={"name": subject}).json()["id"]
    teacher_id = client.post("/api/teachers", json={"name": teacher}).json()["id"]
    class_id = client.post(
        "/api/classes",
        json={"level_id": level, "subject_id": subject_id, "teacher_id": teacher_id},
    ).json()["id"]
    return level, class_id, teacher_id


def enroll_student(client, level, class_ids, name="Sami", month="2026-09", price=300):
    package = client.post(
        "/api/packages",
        json={
            "subject_count": len(class_ids),
            "monthly_price_centimes": price * DH,
            "level_id": level,
        },
    ).json()["id"]
    student = client.post(
        "/api/students", json={"name": name, "level_id": level}
    ).json()["id"]
    enrollment = client.post(
        "/api/enrollments",
        json={
            "student_id": student,
            "month": month,
            "package_id": package,
            "class_ids": class_ids,
        },
    ).json()["id"]
    return student, package, enrollment


class TestMotifs:
    def test_motifs_can_be_created_listed_renamed(self, client):
        motif = client.post("/api/motifs", json={"label": "Situation familiale"})
        assert motif.status_code == 201
        client.patch(
            f"/api/motifs/{motif.json()['id']}", json={"label": "Aide sociale"}
        )
        labels = [m["label"] for m in client.get("/api/motifs").json()]
        assert labels == ["Aide sociale"]

    def test_duplicate_motifs_are_rejected(self, client):
        client.post("/api/motifs", json={"label": "Aide"})
        assert client.post("/api/motifs", json={"label": "Aide"}).status_code == 409


class TestLevelPackages:
    def test_package_carries_its_level(self, client):
        level, _, _ = setup_level_class(client)
        package = client.post(
            "/api/packages",
            json={"subject_count": 1, "monthly_price_centimes": 100, "level_id": level},
        )
        assert package.status_code == 201
        (row,) = client.get("/api/packages").json()
        assert row["level_id"] == level
        assert row["level_name"] == "Primaire"

    def test_package_cannot_exceed_subjects_taught_at_level(self, client):
        level, _, _ = setup_level_class(client)  # one subject at Primaire
        response = client.post(
            "/api/packages",
            json={"subject_count": 4, "monthly_price_centimes": 100, "level_id": level},
        )
        assert response.status_code == 422
        assert "matière" in response.json()["detail"]


class TestAgendaMonths:
    def test_ensure_extends_previous_month_idempotently(self, client):
        level, class_id, _ = setup_level_class(client)
        enroll_student(client, level, [class_id], month="2026-09")
        first = client.post("/api/months/2026-10/ensure")
        assert first.status_code == 200
        assert first.json()["extended"] == 1
        again = client.post("/api/months/2026-10/ensure")
        assert again.json()["extended"] == 0
        (row,) = client.get("/api/months/2026-10/overview").json()
        assert row["enrollment"] is not None

    def test_ensure_refuses_past_months(self, client):
        assert client.post("/api/months/2026-08/ensure").status_code == 409

    def test_past_months_are_locked_for_structure_but_payable(
        self, client, monkeypatch
    ):
        level, class_id, _ = setup_level_class(client)
        # The enrollment was created back when August was the current month.
        monkeypatch.setattr(clock, "current_month", lambda: "2026-08")
        _, package, enrollment = enroll_student(
            client, level, [class_id], month="2026-08"
        )
        monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
        # New enrollment in a past month -> locked.
        student2 = client.post(
            "/api/students", json={"name": "Lina", "level_id": level}
        ).json()["id"]
        blocked = client.post(
            "/api/enrollments",
            json={
                "student_id": student2,
                "month": "2026-08",
                "package_id": package,
                "class_ids": [class_id],
            },
        )
        assert blocked.status_code == 409
        # Adjustments on a past month -> locked.
        blocked_adj = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={"kind": "amount", "value": 10 * DH},
        )
        assert blocked_adj.status_code == 409
        # Collecting the old debt -> allowed.
        paid = client.post("/api/payments", json={"enrollment_id": enrollment})
        assert paid.status_code == 201


class TestAdjustmentEdit:
    def test_adjustment_can_be_edited_in_place(self, client):
        level, class_id, teacher = setup_level_class(client)
        _, _, enrollment = enroll_student(client, level, [class_id])
        adjustment = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={"kind": "amount", "value": 50 * DH},
        ).json()["id"]
        edited = client.patch(
            f"/api/adjustments/{adjustment}",
            json={
                "kind": "percent",
                "value": 1000,  # 10% of 300 = 30 DH
                "reason": "Bourse",
                "bearers": [{"kind": "teacher", "ref_id": teacher}],
            },
        )
        assert edited.status_code == 200, edited.text
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        assert preview["net_centimes"] == 270 * DH
        (adj,) = preview["adjustments"]
        assert adj["resolved_centimes"] == 30 * DH
        assert adj["bearers"][0]["name"] == "Ahmed"

    def test_editing_beyond_price_is_refused_and_nothing_changes(self, client):
        level, class_id, _ = setup_level_class(client)
        _, _, enrollment = enroll_student(client, level, [class_id])
        adjustment = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={"kind": "amount", "value": 50 * DH},
        ).json()["id"]
        refused = client.patch(
            f"/api/adjustments/{adjustment}", json={"value": 400 * DH}
        )
        assert refused.status_code == 422
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        assert preview["net_centimes"] == 250 * DH  # unchanged

    def test_editing_on_a_paid_enrollment_is_refused(self, client):
        level, class_id, _ = setup_level_class(client)
        _, _, enrollment = enroll_student(client, level, [class_id])
        adjustment = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={"kind": "amount", "value": 50 * DH},
        ).json()["id"]
        client.post("/api/payments", json={"enrollment_id": enrollment})
        assert (
            client.patch(
                f"/api/adjustments/{adjustment}", json={"value": 10 * DH}
            ).status_code
            == 409
        )


class TestRowSplitAndHistory:
    def test_overview_rows_include_teacher_shares(self, client):
        level, class_id, _ = setup_level_class(client)
        enroll_student(client, level, [class_id])
        (row,) = client.get("/api/months/2026-09/overview").json()
        (teacher_line,) = [
            line for line in row["enrollment"]["split"] if line["kind"] == "teacher"
        ]
        assert teacher_line["name"] == "Ahmed"
        assert teacher_line["final_centimes"] == 180 * DH

    def test_history_returns_cash_and_counts_per_month(self, client, monkeypatch):
        level, class_id, _ = setup_level_class(client)
        monkeypatch.setattr(clock, "current_month", lambda: "2026-08")
        _, _package, enrollment = enroll_student(
            client, level, [class_id], month="2026-08"
        )
        monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
        client.post("/api/payments", json={"enrollment_id": enrollment})
        history = client.get(
            "/api/reports/history", params={"up_to_month": "2026-09", "months": 3}
        ).json()
        assert [entry["month"] for entry in history] == [
            "2026-07",
            "2026-08",
            "2026-09",
        ]
        august = history[1]
        assert august["cash_in"] == 300 * DH
        assert august["paid_count"] == 1
        assert august["unpaid_count"] == 0
