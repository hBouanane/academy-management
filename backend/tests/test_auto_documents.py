"""Round 22 : les documents qui se rangent tout seuls.

L'export Excel est l'état d'un mois clos : il n'y a rien à décider, il
doit exister. Pareil pour la feuille d'absence. Demander un clic pour
un document que l'application sait produire, c'est demander au client
de se souvenir à notre place — et il oubliera.

Ils se produisent donc seuls dès que le mois est passé, et se
refont seuls quand les chiffres de ce mois bougent après coup. Le
bouton reste pour la feuille d'absence : celle-là, il la veut souvent
en cours de mois.

La fiche de paie, elle, ne se produit JAMAIS toute seule : c'est un
reçu, il se fait au moment où l'on paie.
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


def filed(root, month_folder, drawer):
    place = root / month_folder / drawer
    return sorted(item.name for item in place.iterdir()) if place.is_dir() else []


class TestAClosedMonthFilesItself:
    def test_the_export_appears_without_being_asked(self, client, tmp_path):
        level, class_id, _teacher, package = setup_base(client)
        enroll(client, level, package, class_id, month="2026-08")
        root = with_folder(client, tmp_path)
        # Août est passé : son export doit exister, sans qu'on l'ait demandé.
        client.post("/api/documents/reconcile")
        assert filed(root, "2026-08 Aout", "rapports") == ["paiements.xlsx"]

    def test_the_absence_sheets_too(self, client, tmp_path):
        level, class_id, _teacher, package = setup_base(client)
        enroll(client, level, package, class_id, month="2026-08")
        root = with_folder(client, tmp_path)
        client.post("/api/documents/reconcile")
        assert filed(root, "2026-08 Aout", "absences") != []

    def test_the_running_month_is_left_alone(self, client, tmp_path):
        """Septembre n'est pas fini : son export changerait tous les
        jours, et le ranger n'aurait aucun sens."""
        level, class_id, _teacher, package = setup_base(client)
        enroll(client, level, package, class_id, month="2026-09")
        root = with_folder(client, tmp_path)
        client.post("/api/documents/reconcile")
        assert filed(root, "2026-09 Septembre", "rapports") == []

    def test_a_month_with_nothing_in_it_produces_nothing(self, client, tmp_path):
        root = with_folder(client, tmp_path)
        client.post("/api/documents/reconcile")
        assert not (root / "2026-08 Aout").exists()

    def test_no_folder_means_nothing_happens(self, client):
        level, class_id, _teacher, package = setup_base(client)
        enroll(client, level, package, class_id, month="2026-08")
        # Aucun dossier choisi : on ne se plaint pas, on ne fait rien.
        assert client.post("/api/documents/reconcile").status_code == 200

    def test_payslips_are_never_produced_on_their_own(self, client, tmp_path):
        """Un reçu se fait au moment de payer, jamais tout seul."""
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id, month="2026-08")
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-08-03"},
        )
        client.post(
            "/api/payouts",
            json={"kind": "teacher", "ref_id": teacher, "month": "2026-08"},
        )
        root = with_folder(client, tmp_path)
        client.post("/api/documents/reconcile")
        assert filed(root, "2026-08 Aout", "fiches-de-paie") == []


class TestItRedoesThemWhenTheMonthMoves:
    def test_a_late_payment_refreshes_the_export(self, client, tmp_path):
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id, month="2026-08")
        root = with_folder(client, tmp_path)
        client.post("/api/documents/reconcile")
        before = (root / "2026-08 Aout" / "rapports" / "paiements.xlsx").read_bytes()

        # Un impayé d'août rentre en septembre.
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-20"},
        )
        client.post("/api/documents/reconcile")
        after = (root / "2026-08 Aout" / "rapports" / "paiements.xlsx").read_bytes()
        assert after != before

    def test_nothing_left_to_warn_about_afterwards(self, client, tmp_path):
        """Puisqu'ils se refont seuls, la liste « à regénérer » reste
        vide : elle ne servait qu'à réclamer un clic."""
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id, month="2026-08")
        with_folder(client, tmp_path)
        client.post("/api/documents/reconcile")
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-20"},
        )
        client.post("/api/documents/reconcile")
        assert client.get("/api/documents/stale").json() == []

    def test_an_untouched_month_is_not_rewritten(self, client, tmp_path):
        """Réécrire un fichier que rien n'a changé userait la clé USB
        pour rien, et brouillerait les dates."""
        level, class_id, _teacher, package = setup_base(client)
        enroll(client, level, package, class_id, month="2026-08")
        root = with_folder(client, tmp_path)
        client.post("/api/documents/reconcile")
        target = root / "2026-08 Aout" / "rapports" / "paiements.xlsx"
        stamp = target.stat().st_mtime_ns
        client.post("/api/documents/reconcile")
        assert target.stat().st_mtime_ns == stamp


class TestNobodyHasToAskForIt:
    """La demande exacte : « sans que l'utilisateur clique le bouton »."""

    def test_a_late_payment_refiles_on_its_own(self, client, tmp_path):
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id, month="2026-08")
        root = with_folder(client, tmp_path)
        client.post("/api/documents/reconcile")
        before = (root / "2026-08 Aout" / "rapports" / "paiements.xlsx").read_bytes()

        # Aucun appel a reconcile : le seul geste est l'encaissement.
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-20"},
        )
        after = (root / "2026-08 Aout" / "rapports" / "paiements.xlsx").read_bytes()
        assert after != before

    def test_a_new_enrollment_refiles_the_absence_sheet(self, client, tmp_path):
        level, class_id, _teacher, package = setup_base(client)
        enroll(client, level, package, class_id, month="2026-08")
        root = with_folder(client, tmp_path)
        client.post("/api/documents/reconcile")
        sheet = next((root / "2026-08 Aout" / "absences").iterdir())
        before = sheet.read_bytes()

        enroll(client, level, package, class_id, name="Karim", month="2026-08")
        assert sheet.read_bytes() != before

    def test_opening_the_application_catches_up(self, tmp_path, monkeypatch):
        """Deux mois sans ouvrir l'application : elle rattrape en
        s'ouvrant."""
        monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
        database = str(tmp_path / "test.db")
        app = create_app(database)
        with TestClient(app) as client:
            level, class_id, _teacher, package = setup_base(client)
            enroll(client, level, package, class_id, month="2026-08")
            with_folder(client, tmp_path)
        # Le dossier a ete choisi APRES coup : rien n'est encore range.
        assert not (tmp_path / "aX" / "2026-08 Aout").exists()

        # On rouvre : elle range ce qui manquait.
        with TestClient(create_app(database)):
            pass
        assert filed(tmp_path / "aX", "2026-08 Aout", "rapports") == ["paiements.xlsx"]
