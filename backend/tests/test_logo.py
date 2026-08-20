"""Round 27b : son logo, et son nom en haut de l'écran.

« Academy Management » en haut de la barre, c'est le nom de l'outil.
Lui ouvre l'application pour voir SON académie — et quand un parent
regarde par-dessus son épaule, c'est son enseigne qui doit être là, pas
la nôtre.

Le logo vit dans la base : il part donc avec les sauvegardes. Un logo
posé sur le bureau puis effacé laisserait un carré vide au prochain
démarrage.
"""

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.app import create_app
from app.services import clock

# Le plus petit PNG valide : un pixel rouge. Assez pour tout vérifier.
PIXEL = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4"
    "z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
)
PNG = f"data:image/png;base64,{PIXEL}"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


class TestHisMarkOnTheApp:
    def test_no_logo_at_the_start(self, client):
        assert client.get("/api/settings/logo").json()["logo"] is None

    def test_he_puts_his_logo_and_it_stays(self, client):
        client.put("/api/settings/logo", json={"logo": PNG})
        assert client.get("/api/settings/logo").json()["logo"] == PNG

    def test_he_can_take_it_off_again(self, client):
        client.put("/api/settings/logo", json={"logo": PNG})
        client.put("/api/settings/logo", json={"logo": None})
        assert client.get("/api/settings/logo").json()["logo"] is None

    def test_it_survives_in_the_database_not_on_the_desk(self, client, tmp_path):
        """Rangé dans la base, il part avec les sauvegardes."""
        client.put("/api/settings/logo", json={"logo": PNG})
        import sqlite3

        conn = sqlite3.connect(tmp_path / "test.db")
        stored = conn.execute(
            "SELECT value FROM app_setting WHERE key = 'logo'"
        ).fetchone()
        assert stored is not None and stored[0] == PNG


class TestWhatIsRefused:
    def test_something_that_is_not_an_image_is_refused(self, client):
        refused = client.put(
            "/api/settings/logo", json={"logo": "data:text/html;base64,PGI+"}
        )
        assert refused.status_code == 422

    def test_a_plain_string_is_refused(self, client):
        refused = client.put("/api/settings/logo", json={"logo": "mon-logo.png"})
        assert refused.status_code == 422

    def test_an_enormous_logo_is_refused(self, client):
        """Une photo de 8 Mo gonflerait chaque sauvegarde de 8 Mo."""
        huge = "data:image/png;base64," + "A" * (3 * 1024 * 1024)
        refused = client.put("/api/settings/logo", json={"logo": huge})
        assert refused.status_code == 422
