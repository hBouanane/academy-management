"""Round 27 : un document déjà demandé reste à jour, même en cours de mois.

Le rangement automatique laissait le mois EN COURS tranquille — son
export changerait tous les jours. Bonne règle pour ne rien créer sans
qu'on le demande : personne ne veut voir son dossier se remplir de
fichiers qu'il n'a pas réclamés.

Mais le bandeau, lui, réclamait ces documents-là. « 2 document(s) à
régénérer » restait affiché pour août pendant tout le mois d'août, et
rien n'allait jamais l'éteindre : le rangement avait justement décidé
de ne pas y toucher. Le bandeau demandait un geste que l'application
s'était interdit de faire.

Ce qu'il a demandé une fois, on le tient à jour — y compris pendant le
mois en cours. Ce qu'il n'a jamais demandé, on ne le crée toujours pas.
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


def with_folder(client, tmp_path):
    client.put("/api/settings/folders/documents", json={"path": str(tmp_path / "aX")})
    return tmp_path / "aX"


def stale(client):
    return client.get("/api/documents/stale").json()


def filed(root, month_folder, drawer):
    place = root / month_folder / drawer
    return sorted(item.name for item in place.iterdir()) if place.is_dir() else []


def running_month_setup(client, tmp_path):
    """Un élève inscrit CE mois-ci, et un dossier configuré."""
    level, class_id, _teacher, package = setup_base(client)
    student, enrollment = enroll(client, level, package, class_id, month="2026-09")
    root = with_folder(client, tmp_path)
    return root, student, enrollment


class TestWhatHeAskedForStaysFresh:
    def test_an_export_he_asked_for_is_redone_by_itself(self, client, tmp_path):
        root, _student, enrollment = running_month_setup(client, tmp_path)
        client.post("/api/documents/file", json={"kind": "excel", "month": "2026-09"})
        assert filed(root, "2026-09 Septembre", "rapports") != []

        # Les chiffres bougent : un paiement rentre.
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )

        assert stale(client) == []

    def test_the_banner_no_longer_asks_for_what_we_refuse_to_do(self, client, tmp_path):
        """Le bandeau ne doit rien réclamer que l'application s'interdise."""
        _root, _student, enrollment = running_month_setup(client, tmp_path)
        client.post("/api/documents/file", json={"kind": "excel", "month": "2026-09"})
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        assert [item["kind"] for item in stale(client)] == []


class TestWhatHeNeverAskedForIsStillNotCreated:
    def test_nothing_appears_on_its_own_for_a_running_month(self, client, tmp_path):
        """Son dossier ne se remplit pas de fichiers qu'il n'a pas voulus."""
        root, _student, enrollment = running_month_setup(client, tmp_path)
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        assert filed(root, "2026-09 Septembre", "rapports") == []


class TestTheClosedMonthKeepsItsRule:
    def test_a_finished_month_still_files_itself(self, client, tmp_path):
        level, class_id, _teacher, package = setup_base(client)
        enroll(client, level, package, class_id, month="2026-08")
        root = with_folder(client, tmp_path)
        client.post("/api/documents/reconcile")
        assert filed(root, "2026-08 Aout", "rapports") == ["paiements.xlsx"]


class TestTheReceiptIsNeverTouched:
    def test_a_payslip_is_not_regenerated(self, client, tmp_path):
        """Une fiche de paie constate ce qui est sorti de la caisse ce
        jour-là. La refaire produirait un second papier contredisant
        celui que le professeur a signé."""
        _root, _student, enrollment = running_month_setup(client, tmp_path)
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        assert [
            item["kind"] for item in stale(client) if item["kind"] == "payslip"
        ] == []
