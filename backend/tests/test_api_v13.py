"""Round 14 : la répartition entre professeurs devient contrôlable.

Par défaut elle suit les jours enseignés. Le propriétaire peut la fixer
lui-même — en pourcentages, seuls valables quand les prix des élèves
diffèrent — et revenir à l'automatique quand il veut.
"""

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


def teacher_totals(client, month="2026-09"):
    report = client.get(f"/api/reports/monthly?month={month}").json()
    return {
        total["name"]: total["total"]
        for total in report["totals"]
        if total["kind"] == "teacher"
    }


def handover(client, class_id, successor, date="2026-09-21"):
    response = client.post(
        f"/api/classes/{class_id}/replace-teacher",
        json={"date": date, "successor_id": successor},
    )
    assert response.status_code == 200, response.text


class TestShareControl:
    def test_by_default_the_split_follows_the_days_taught(self, client):
        _, class_id, teacher, _ = setup_base(client)
        sara = client.post("/api/teachers", json={"name": "Sara"}).json()["id"]
        handover(client, class_id, sara)
        data = client.get(f"/api/classes/{class_id}/share?month=2026-09").json()
        assert data["manual"] is False
        assert {row["teacher_id"]: row["share_bp"] for row in data["shares"]} == {
            teacher: 6667,  # 20 jours sur 30
            sara: 3333,
        }

    def test_the_owner_can_fix_the_split_himself(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        sara = client.post("/api/teachers", json={"name": "Sara"}).json()["id"]
        handover(client, class_id, sara)
        saved = client.put(
            f"/api/classes/{class_id}/share",
            json={
                "month": "2026-09",
                "shares": [
                    {"teacher_id": teacher, "share_bp": 4000},
                    {"teacher_id": sara, "share_bp": 6000},
                ],
            },
        )
        assert saved.status_code == 200, saved.text
        client.post("/api/payments", json={"enrollment_id": enrollment})
        # 180 DH de part professeur : 40% / 60%.
        assert teacher_totals(client) == {"Ahmed": 72 * DH, "Sara": 108 * DH}
        data = client.get(f"/api/classes/{class_id}/share?month=2026-09").json()
        assert data["manual"] is True

    def test_the_whole_month_can_go_to_the_one_who_left(self, client):
        # Il a préparé le trimestre : le propriétaire lui laisse tout.
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        sara = client.post("/api/teachers", json={"name": "Sara"}).json()["id"]
        handover(client, class_id, sara)
        client.put(
            f"/api/classes/{class_id}/share",
            json={
                "month": "2026-09",
                "shares": [
                    {"teacher_id": teacher, "share_bp": 10000},
                    {"teacher_id": sara, "share_bp": 0},
                ],
            },
        )
        client.post("/api/payments", json={"enrollment_id": enrollment})
        assert teacher_totals(client) == {"Ahmed": 180 * DH}

    def test_an_archived_professor_keeps_his_agreed_share(self, client):
        # Archivé ne veut pas dire oublié : ce qu'on lui a promis reste dû.
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        sara = client.post("/api/teachers", json={"name": "Sara"}).json()["id"]
        handover(client, class_id, sara)
        client.put(
            f"/api/classes/{class_id}/share",
            json={
                "month": "2026-09",
                "shares": [
                    {"teacher_id": teacher, "share_bp": 5000},
                    {"teacher_id": sara, "share_bp": 5000},
                ],
            },
        )
        assert (
            client.patch(f"/api/teachers/{teacher}", json={"is_active": False})
        ).status_code == 200
        client.post("/api/payments", json={"enrollment_id": enrollment})
        assert teacher_totals(client) == {"Ahmed": 90 * DH, "Sara": 90 * DH}

    def test_the_shares_must_make_a_whole(self, client):
        _, class_id, teacher, _ = setup_base(client)
        sara = client.post("/api/teachers", json={"name": "Sara"}).json()["id"]
        handover(client, class_id, sara)
        refused = client.put(
            f"/api/classes/{class_id}/share",
            json={
                "month": "2026-09",
                "shares": [
                    {"teacher_id": teacher, "share_bp": 4000},
                    {"teacher_id": sara, "share_bp": 4000},
                ],
            },
        )
        assert refused.status_code == 422
        assert "100" in refused.json()["detail"]

    def test_going_back_to_automatic(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        sara = client.post("/api/teachers", json={"name": "Sara"}).json()["id"]
        handover(client, class_id, sara)
        client.put(
            f"/api/classes/{class_id}/share",
            json={
                "month": "2026-09",
                "shares": [
                    {"teacher_id": teacher, "share_bp": 10000},
                    {"teacher_id": sara, "share_bp": 0},
                ],
            },
        )
        removed = client.delete(f"/api/classes/{class_id}/share?month=2026-09")
        assert removed.status_code == 200, removed.text
        assert (
            client.get(f"/api/classes/{class_id}/share?month=2026-09").json()["manual"]
            is False
        )
        client.post("/api/payments", json={"enrollment_id": enrollment})
        assert teacher_totals(client) == {"Ahmed": 120 * DH, "Sara": 60 * DH}

    def test_an_override_stays_in_its_own_month(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, september = enroll(client, level, package, class_id)
        _, october = enroll(
            client, level, package, class_id, name="Lina", month="2026-10"
        )
        sara = client.post("/api/teachers", json={"name": "Sara"}).json()["id"]
        handover(client, class_id, sara)
        client.put(
            f"/api/classes/{class_id}/share",
            json={
                "month": "2026-09",
                "shares": [
                    {"teacher_id": teacher, "share_bp": 10000},
                    {"teacher_id": sara, "share_bp": 0},
                ],
            },
        )
        client.post("/api/payments", json={"enrollment_id": september})
        client.post("/api/payments", json={"enrollment_id": october})
        assert teacher_totals(client, "2026-09") == {"Ahmed": 180 * DH}
        # Octobre : Sara enseigne seule, l'accord de septembre ne la suit pas.
        assert teacher_totals(client, "2026-10") == {"Sara": 180 * DH}

    def test_the_share_view_says_who_taught_how_many_days(self, client):
        _, class_id, teacher, _ = setup_base(client)
        sara = client.post("/api/teachers", json={"name": "Sara"}).json()["id"]
        handover(client, class_id, sara)
        data = client.get(f"/api/classes/{class_id}/share?month=2026-09").json()
        by_id = {row["teacher_id"]: row for row in data["shares"]}
        assert by_id[teacher]["days"] == 20
        assert by_id[sara]["days"] == 10
        assert by_id[teacher]["teacher_name"] == "Ahmed"


class TestTeacherInvoice:
    def test_the_invoice_states_what_is_due_and_what_was_paid(self, client):
        import io

        from docx import Document

        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        client.post(
            "/api/payouts",
            json={
                "kind": "teacher",
                "ref_id": teacher,
                "month": "2026-09",
                "amount_centimes": 100 * DH,
            },
        )
        response = client.get(f"/api/teachers/{teacher}/invoice.docx?month=2026-09")
        assert response.status_code == 200, response.text
        assert "paie-2026-09.docx" in response.headers["content-disposition"]
        text = "\n".join(
            p.text for p in Document(io.BytesIO(response.content)).paragraphs
        )
        assert "Fiche de paie — septembre 2026" in text
        assert "Ahmed" in text
        assert "Dû pour le mois : 180,00 DH" in text
        assert "Déjà versé : 100,00 DH" in text
        assert "Reste à verser : 80,00 DH" in text

    def test_the_invoice_lists_the_classes(self, client):
        import io

        from docx import Document

        level, class_id, teacher, package = setup_base(client)
        enroll(client, level, package, class_id)
        response = client.get(f"/api/teachers/{teacher}/invoice.docx?month=2026-09")
        document = Document(io.BytesIO(response.content))
        rows = [[cell.text for cell in row.cells] for row in document.tables[0].rows]
        assert rows[0] == ["Classe", "Niveau", "Inscrits", "Montant"]
        assert rows[1][0] == "Math"
        assert rows[1][2] == "1"  # inscrit, même s'il n'a pas encore payé

    def test_an_unknown_teacher_is_404(self, client):
        assert (
            client.get("/api/teachers/999/invoice.docx?month=2026-09").status_code
            == 404
        )
