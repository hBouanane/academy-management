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

DH = 100


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


class TestTheDocumentsFolder:
    def test_it_is_the_only_one_to_configure(self, client, tmp_path):
        """Les sauvegardes de la base ne se reglent pas : elles se font
        toutes seules, et s'emportent a la demande sur une cle."""
        client.put(
            "/api/settings/folders/documents", json={"path": str(tmp_path / "aX")}
        )
        settings = client.get("/api/settings/folders").json()
        assert list(settings) == ["documents"]
        assert settings["documents"]["path"] == str(tmp_path / "aX")

    def test_a_folder_can_be_given_up(self, client, tmp_path):
        client.put(
            "/api/settings/folders/documents", json={"path": str(tmp_path / "aX")}
        )
        client.delete("/api/settings/folders/documents")
        assert client.get("/api/settings/folders").json()["documents"]["path"] is None

    def test_an_unknown_kind_is_refused(self, client, tmp_path):
        refused = client.put(
            "/api/settings/folders/photos", json={"path": str(tmp_path)}
        )
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
    """Ce qui vieillit, et ce qui ne vieillit pas.

    L'export Excel est l'etat d'un mois : payer un professeur, un impaye
    qui rentre — tout le deplace. La feuille d'absence liste les
    inscrits : un eleve de plus la perime.

    La fiche de paie, elle, est un RECU. Elle constate que l'argent est
    sorti ce jour-la, et rien de ce qui arrive ensuite ne rend cela
    faux.
    """

    def test_a_fresh_export_is_not_stale(self, client, tmp_path):
        level, class_id, _teacher, package = setup_base(client)
        enroll(client, level, package, class_id)
        client.put(
            "/api/settings/folders/documents", json={"path": str(tmp_path / "aX")}
        )
        client.post("/api/documents/file", json={"kind": "excel", "month": "2026-09"})
        assert stale(client) == []

    def test_money_moving_ages_the_month_export(self, client, tmp_path):
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.put(
            "/api/settings/folders/documents", json={"path": str(tmp_path / "aX")}
        )
        client.post("/api/documents/file", json={"kind": "excel", "month": "2026-09"})
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        aged = stale(client)
        assert [item["kind"] for item in aged] == ["excel"]
        assert (
            "excel" in aged[0]["label"].lower() or "export" in aged[0]["label"].lower()
        )

    def test_a_receipt_is_never_aged_by_anything(self, client, tmp_path):
        """Le professeur l'a signee : la regenerer produirait un second
        papier contredisant le premier."""
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        payout = client.post(
            "/api/payouts",
            json={"kind": "teacher", "ref_id": teacher, "month": "2026-09"},
        ).json()
        client.put(
            "/api/settings/folders/documents", json={"path": str(tmp_path / "aX")}
        )
        client.post(
            "/api/documents/file",
            json={
                "kind": "payslip",
                "month": "2026-09",
                "ref_id": teacher,
                "payout_id": payout["id"],
            },
        )
        client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={"kind": "amount", "value": 50 * DH},
        )
        assert [
            item["kind"] for item in stale(client) if item["kind"] == "payslip"
        ] == []

    def test_an_absence_sheet_ages_when_a_student_joins(self, client, tmp_path):
        level, class_id, _teacher, package = setup_base(client)
        client.put(
            "/api/settings/folders/documents", json={"path": str(tmp_path / "aX")}
        )
        client.post(
            "/api/documents/file",
            json={"kind": "absence", "month": "2026-09", "ref_id": class_id},
        )
        enroll(client, level, package, class_id)
        aged = stale(client)
        assert [(item["kind"], item["ref_id"]) for item in aged] == [
            ("absence", class_id)
        ]

    def test_a_document_never_filed_is_never_stale(self, client, tmp_path):
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        # Rien n'a ete sorti : il n'y a rien a regenerer.
        assert stale(client) == []

    def test_refiling_settles_the_warning(self, client, tmp_path):
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.put(
            "/api/settings/folders/documents", json={"path": str(tmp_path / "aX")}
        )
        body = {"kind": "excel", "month": "2026-09"}
        client.post("/api/documents/file", json=body)
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        assert len(stale(client)) == 1
        client.post("/api/documents/file", json=body)
        assert stale(client) == []

    def test_a_past_month_refreshes_itself(self, client, tmp_path):
        """La demande d'origine etait « dites-moi quel fichier
        retelecharger ». Mieux : il se refait tout seul, et il n'y a
        plus rien a dire."""
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id, month="2026-08")
        client.put(
            "/api/settings/folders/documents", json={"path": str(tmp_path / "aX")}
        )
        client.post("/api/documents/file", json={"kind": "excel", "month": "2026-08"})
        export = tmp_path / "aX" / "2026-08 Aout" / "rapports" / "paiements.xlsx"
        before = export.read_bytes()

        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-20"},
        )
        assert export.read_bytes() != before
        assert stale(client, "2026-08") == []

    def test_nothing_is_left_hanging_anywhere(self, client, tmp_path):
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id, month="2026-08")
        client.put(
            "/api/settings/folders/documents", json={"path": str(tmp_path / "aX")}
        )
        client.post("/api/documents/file", json={"kind": "excel", "month": "2026-08"})
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-20"},
        )
        assert client.get("/api/documents/stale").json() == []
