"""Round 13 : le verrou.

Le risque n'est pas qu'on lise les chiffres, c'est qu'on les CHANGE — un
élève qui passe derrière le comptoir et s'offre le mois. L'application
demande donc un code, et se reverrouille toute seule quand personne ne
s'en sert : c'est le moment où le portable reste ouvert sur le bureau
qui est dangereux, pas le démarrage.

Tant qu'aucun code n'est posé, rien n'est fermé : une installation neuve
s'ouvre, et c'est le propriétaire qui décide d'en poser un.

Hors ligne, personne ne peut réinitialiser un mot de passe oublié. La
pose du code rend donc UNE FOIS une phrase de secours, à noter sur
papier — sans elle, un code oublié emmure l'académie.
"""

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def set_code(client, code="1234"):
    response = client.post("/api/lock", json={"code": code})
    assert response.status_code == 201, response.text
    return response.json()["recovery_phrase"]


def unlock(client, code="1234"):
    response = client.post("/api/lock/unlock", json={"code": code})
    assert response.status_code == 200, response.text
    return response.json()["token"]


class TestLock:
    def test_a_fresh_install_is_open(self, client):
        assert client.get("/api/lock").json()["configured"] is False
        assert client.get("/api/teachers").status_code == 200

    def test_setting_a_code_closes_the_door(self, client):
        set_code(client)
        assert client.get("/api/lock").json()["configured"] is True
        assert client.get("/api/teachers").status_code == 401

    def test_the_right_code_opens_it(self, client):
        set_code(client)
        token = unlock(client)
        opened = client.get("/api/teachers", headers={"X-Session-Token": token})
        assert opened.status_code == 200

    def test_the_wrong_code_hands_out_nothing(self, client):
        set_code(client)
        refused = client.post("/api/lock/unlock", json={"code": "0000"})
        assert refused.status_code == 401
        assert "token" not in refused.json()

    def test_a_made_up_token_does_not_pass(self, client):
        set_code(client)
        refused = client.get("/api/teachers", headers={"X-Session-Token": "pas-le-bon"})
        assert refused.status_code == 401

    def test_the_lock_itself_stays_reachable_while_locked(self, client):
        # Sinon on ne pourrait jamais déverrouiller.
        set_code(client)
        assert client.get("/api/lock").status_code == 200

    def test_a_second_code_cannot_be_posed_over_the_first(self, client):
        set_code(client)
        refused = client.post("/api/lock", json={"code": "9999"})
        assert refused.status_code == 409

    def test_the_recovery_phrase_poses_a_new_code(self, client):
        phrase = set_code(client)
        recovered = client.post(
            "/api/lock/recover", json={"phrase": phrase, "code": "5678"}
        )
        assert recovered.status_code == 200
        assert client.post("/api/lock/unlock", json={"code": "5678"}).status_code == 200
        assert client.post("/api/lock/unlock", json={"code": "1234"}).status_code == 401

    def test_a_wrong_phrase_changes_nothing(self, client):
        set_code(client)
        refused = client.post(
            "/api/lock/recover", json={"phrase": "chat-chien-oiseau-42", "code": "5678"}
        )
        assert refused.status_code == 401
        assert client.post("/api/lock/unlock", json={"code": "1234"}).status_code == 200

    def test_the_phrase_is_worth_writing_down(self, client):
        # Quatre mots et un nombre : lisible à l'oreille, recopiable à la main.
        phrase = set_code(client)
        assert len(phrase.split("-")) >= 4

    def test_changing_the_code_needs_the_current_one(self, client):
        set_code(client)
        token = unlock(client)
        headers = {"X-Session-Token": token}
        refused = client.patch(
            "/api/lock", json={"code": "0000", "new_code": "5678"}, headers=headers
        )
        assert refused.status_code == 401
        changed = client.patch(
            "/api/lock", json={"code": "1234", "new_code": "5678"}, headers=headers
        )
        assert changed.status_code == 200
        assert client.post("/api/lock/unlock", json={"code": "5678"}).status_code == 200

    def test_the_auto_lock_delay_is_the_owners_call(self, client):
        set_code(client)
        headers = {"X-Session-Token": unlock(client)}
        # Par défaut, court : c'est le portable laissé ouvert qui est le risque.
        assert client.get("/api/lock").json()["auto_lock_minutes"] == 5
        client.patch("/api/lock", json={"auto_lock_minutes": 20}, headers=headers)
        assert client.get("/api/lock").json()["auto_lock_minutes"] == 20

    def test_locking_again_burns_the_token(self, client):
        set_code(client)
        token = unlock(client)
        headers = {"X-Session-Token": token}
        assert client.post("/api/lock/lock", headers=headers).status_code == 200
        assert client.get("/api/teachers", headers=headers).status_code == 401

    def test_a_download_link_carries_no_header_so_it_gets_a_cookie(self, client):
        """Un `<a download>` ne peut porter aucun en-tête, et on ne met
        pas un jeton dans une adresse : l'ouverture pose donc un cookie."""
        set_code(client)
        opened = client.post("/api/lock/unlock", json={"code": "1234"})
        assert "academy_session" in opened.cookies
        # Le client garde le cookie : l'appel suivant passe sans en-tête.
        assert client.get("/api/teachers").status_code == 200
        client.post("/api/lock/lock")
        assert client.get("/api/teachers").status_code == 401

    def test_guessing_gets_slower(self, client):
        """Un code court se devine en une minute si l'on peut essayer sans
        fin. Après quelques échecs, chaque essai attend — y compris sur la
        phrase de secours, qui ouvre tout autant."""
        set_code(client)
        for _ in range(4):
            client.post("/api/lock/unlock", json={"code": "0000"})
        assert client.post("/api/lock/unlock", json={"code": "1234"}).status_code == 429
        assert (
            client.post(
                "/api/lock/recover", json={"phrase": "a-b-c-d-1", "code": "5678"}
            ).status_code
            == 429
        )

    def test_the_health_check_stays_open(self, client):
        """La fenêtre attend que le serveur réponde sur /api/health avant
        de s'ouvrir. Fermer cette porte rendrait l'application
        impossible à lancer des qu'un code est posé — elle attendrait
        vingt secondes puis annoncerait un serveur mort."""
        set_code(client)
        assert client.get("/api/health").status_code == 200

    def test_the_code_is_never_stored_as_typed(self, client, tmp_path):
        set_code(client, "monsecret")
        assert "monsecret" not in (tmp_path / "test.db").read_bytes().decode("latin-1")
