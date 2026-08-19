"""Round 14 : les documents et leur péremption.

Une fiche de paie sortie le 5 devient fausse si un impayé rentre le 20.
Le client veut être prévenu — mais prévenu JUSTE : dire « septembre a
changé » signalerait toutes les fiches du mois alors qu'une seule est
concernée, et un avertissement qui crie au loup finit ignoré.

D'où la portée. Chaque écriture dit qui elle touche, et seuls les
documents de cette portée-là remontent.

Le dossier de sauvegarde va avec : plutôt que de choisir un
emplacement à chaque téléchargement, le propriétaire désigne une fois
un dossier, et l'application y range elle-même — un sous-dossier par
mois, un par sorte de document.
"""

import pytest
from fastapi.testclient import TestClient
from test_api_v4 import enroll, setup_base

from app.adapters.api.app import create_app
from app.services import clock


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def stale(client, month="2026-09"):
    response = client.get(f"/api/documents/stale?month={month}")
    assert response.status_code == 200, response.text
    return response.json()


class TestBackupFolder:
    def test_no_folder_chosen_yet(self, client):
        assert client.get("/api/settings/backup-root").json()["path"] is None

    def test_choosing_a_folder_sticks(self, client, tmp_path):
        root = tmp_path / "academX"
        saved = client.put("/api/settings/backup-root", json={"path": str(root)})
        assert saved.status_code == 200, saved.text
        assert client.get("/api/settings/backup-root").json()["path"] == str(root)

    def test_the_folder_is_created_if_it_does_not_exist(self, client, tmp_path):
        root = tmp_path / "academX"
        client.put("/api/settings/backup-root", json={"path": str(root)})
        assert root.is_dir()

    def test_a_file_cannot_serve_as_a_folder(self, client, tmp_path):
        intruder = tmp_path / "pas-un-dossier.txt"
        intruder.write_text("x")
        refused = client.put("/api/settings/backup-root", json={"path": str(intruder)})
        assert refused.status_code == 422


class TestFiling:
    def test_a_payslip_lands_in_its_month_and_its_drawer(self, client, tmp_path):
        level, class_id, teacher, package = setup_base(client)
        enroll(client, level, package, class_id)
        client.put("/api/settings/backup-root", json={"path": str(tmp_path / "aX")})
        filed = client.post(
            "/api/documents/file",
            json={"kind": "payslip", "month": "2026-09", "ref_id": teacher},
        )
        assert filed.status_code == 201, filed.text
        written = tmp_path / "aX" / "2026-09 Septembre" / "fiches-de-paie"
        assert [item.suffix for item in written.iterdir()] == [".docx"]

    def test_an_absence_sheet_has_its_own_drawer(self, client, tmp_path):
        level, class_id, _teacher, package = setup_base(client)
        enroll(client, level, package, class_id)
        client.put("/api/settings/backup-root", json={"path": str(tmp_path / "aX")})
        client.post(
            "/api/documents/file",
            json={"kind": "absence", "month": "2026-09", "ref_id": class_id},
        )
        assert (tmp_path / "aX" / "2026-09 Septembre" / "absences").is_dir()

    def test_filing_needs_a_folder_first(self, client):
        *_, teacher, _package = setup_base(client)
        refused = client.post(
            "/api/documents/file",
            json={"kind": "payslip", "month": "2026-09", "ref_id": teacher},
        )
        assert refused.status_code == 409
        assert "dossier" in refused.json()["detail"]

    def test_filing_again_replaces_rather_than_piles_up(self, client, tmp_path):
        level, class_id, teacher, package = setup_base(client)
        enroll(client, level, package, class_id)
        client.put("/api/settings/backup-root", json={"path": str(tmp_path / "aX")})
        body = {"kind": "payslip", "month": "2026-09", "ref_id": teacher}
        client.post("/api/documents/file", json=body)
        client.post("/api/documents/file", json=body)
        drawer = tmp_path / "aX" / "2026-09 Septembre" / "fiches-de-paie"
        assert len(list(drawer.iterdir())) == 1


class TestStaleness:
    def test_a_fresh_document_is_not_stale(self, client, tmp_path):
        level, class_id, teacher, package = setup_base(client)
        enroll(client, level, package, class_id)
        client.put("/api/settings/backup-root", json={"path": str(tmp_path / "aX")})
        client.post(
            "/api/documents/file",
            json={"kind": "payslip", "month": "2026-09", "ref_id": teacher},
        )
        assert stale(client) == []

    def test_money_moving_ages_the_payslip_it_concerns(self, client, tmp_path):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.put("/api/settings/backup-root", json={"path": str(tmp_path / "aX")})
        client.post(
            "/api/documents/file",
            json={"kind": "payslip", "month": "2026-09", "ref_id": teacher},
        )
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        aged = stale(client)
        assert [(item["kind"], item["ref_id"]) for item in aged] == [
            ("payslip", teacher)
        ]
        assert "fiche de paie" in aged[0]["label"].lower()

    def test_another_teachers_payslip_stays_quiet(self, client, tmp_path):
        """Le cœur de la demande : signaler JUSTE. Un professeur dont
        rien n'a bougé ne doit pas voir sa fiche marquée périmée."""
        level, class_id, teacher, package = setup_base(client)
        other = client.post("/api/teachers", json={"name": "Sara Alami"}).json()["id"]
        other_class = client.post(
            "/api/classes",
            json={
                "level_id": level,
                "subject_id": client.get("/api/subjects").json()[0]["id"],
                "teacher_id": other,
            },
        ).json()["id"]
        _, enrollment = enroll(client, level, package, class_id)
        client.put("/api/settings/backup-root", json={"path": str(tmp_path / "aX")})
        for who in (teacher, other):
            client.post(
                "/api/documents/file",
                json={"kind": "payslip", "month": "2026-09", "ref_id": who},
            )
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        aged = stale(client)
        assert [item["ref_id"] for item in aged] == [teacher]
        assert other_class is not None

    def test_a_document_never_filed_is_never_stale(self, client, tmp_path):
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        # Rien n'a été sorti : il n'y a rien à regénérer.
        assert stale(client) == []

    def test_refiling_settles_the_warning(self, client, tmp_path):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.put("/api/settings/backup-root", json={"path": str(tmp_path / "aX")})
        body = {"kind": "payslip", "month": "2026-09", "ref_id": teacher}
        client.post("/api/documents/file", json=body)
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        assert len(stale(client)) == 1
        client.post("/api/documents/file", json=body)
        assert stale(client) == []

    def test_an_enrollment_ages_the_absence_sheet(self, client, tmp_path):
        """La feuille d'absence liste les inscrits : un élève de plus la
        périme, même si personne n'a encore payé."""
        level, class_id, _teacher, package = setup_base(client)
        client.put("/api/settings/backup-root", json={"path": str(tmp_path / "aX")})
        client.post(
            "/api/documents/file",
            json={"kind": "absence", "month": "2026-09", "ref_id": class_id},
        )
        enroll(client, level, package, class_id)
        aged = stale(client)
        assert [(item["kind"], item["ref_id"]) for item in aged] == [
            ("absence", class_id)
        ]

    def test_a_past_month_is_the_one_that_needs_saying(self, client, tmp_path):
        """C'est la demande exacte : quand un mois PASSÉ change, il faut
        savoir quel fichier retélécharger."""
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id, month="2026-08")
        client.put("/api/settings/backup-root", json={"path": str(tmp_path / "aX")})
        client.post(
            "/api/documents/file",
            json={"kind": "payslip", "month": "2026-08", "ref_id": teacher},
        )
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-20"},
        )
        aged = stale(client, "2026-08")
        assert [item["kind"] for item in aged] == ["payslip"]
        assert aged[0]["month"] == "2026-08"

    def test_without_a_month_every_stale_document_shows(self, client, tmp_path):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id, month="2026-08")
        client.put("/api/settings/backup-root", json={"path": str(tmp_path / "aX")})
        client.post(
            "/api/documents/file",
            json={"kind": "payslip", "month": "2026-08", "ref_id": teacher},
        )
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-20"},
        )
        everything = client.get("/api/documents/stale").json()
        assert [item["month"] for item in everything] == ["2026-08"]
