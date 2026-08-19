"""Round 15 : le dépannage par l'éditeur.

Le propriétaire peut tout perdre : son code ET la phrase notée sur
papier. Hors ligne, plus personne ne peut rien — sauf celui qui a écrit
le logiciel. Il lui faut donc une porte à lui, qu'il n'ouvre qu'au
téléphone.

Le principe : l'application affiche un défi, l'éditeur le SIGNE avec sa
clé privée, et renvoie la signature. Le défi change chaque jour, donc
la signature d'hier ne vaut plus rien.

Ce qui voyage dans la version livrée n'est que la clé PUBLIQUE : elle
sait vérifier une signature, jamais en produire. L'extraire de
l'exécutable ne donne donc aucun pouvoir — c'est toute la différence
avec un secret partagé.

Sans clé publique installée, cette porte n'existe pas du tout : elle ne
s'affiche pas et l'API ne répond rien.
"""

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from app.adapters.api import vendor
from app.adapters.api.app import create_app

# La paire de l'éditeur : la privée reste chez lui, la publique part
# dans la version livrée.
PRIVATE = Ed25519PrivateKey.generate()
PUBLIC = vendor.public_key_text(PRIVATE.public_key())


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(vendor, "vendor_key", lambda: PUBLIC)
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def keyless(tmp_path, monkeypatch):
    monkeypatch.setattr(vendor, "vendor_key", lambda: None)
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def set_code(client, code="1234"):
    response = client.post("/api/lock", json={"code": code})
    assert response.status_code == 201, response.text
    return response.json()["recovery_phrase"]


def answer_for(challenge: str) -> str:
    """Ce que l'éditeur signe de son côté, avec sa clé privée."""
    return base64.b64encode(PRIVATE.sign(challenge.encode())).decode()


class TestVendorRescue:
    def test_the_door_is_invisible_without_a_key(self, keyless):
        set_code(keyless)
        assert keyless.get("/api/lock/rescue").json()["available"] is False

    def test_no_key_means_no_rescue_at_all(self, keyless):
        set_code(keyless)
        refused = keyless.post(
            "/api/lock/rescue", json={"answer": "AAAA-BBBB", "code": "5678"}
        )
        assert refused.status_code == 404

    def test_the_challenge_is_shown_while_locked(self, client):
        set_code(client)
        offered = client.get("/api/lock/rescue").json()
        assert offered["available"] is True
        assert len(offered["challenge"]) >= 8

    def test_the_challenge_does_not_move_within_a_day(self, client):
        set_code(client)
        first = client.get("/api/lock/rescue").json()["challenge"]
        assert client.get("/api/lock/rescue").json()["challenge"] == first

    def test_the_right_answer_poses_a_new_code(self, client):
        set_code(client)
        challenge = client.get("/api/lock/rescue").json()["challenge"]
        rescued = client.post(
            "/api/lock/rescue",
            json={"answer": answer_for(challenge), "code": "5678"},
        )
        assert rescued.status_code == 200
        assert client.post("/api/lock/unlock", json={"code": "5678"}).status_code == 200

    def test_a_wrong_answer_changes_nothing(self, client):
        set_code(client)
        refused = client.post(
            "/api/lock/rescue",
            json={"answer": base64.b64encode(b"n" * 64).decode(), "code": "5678"},
        )
        assert refused.status_code == 401
        assert client.post("/api/lock/unlock", json={"code": "1234"}).status_code == 200

    def test_stray_spaces_and_line_breaks_do_not_matter(self, client):
        """Elle voyage par message : elle arrive souvent avec un retour
        à la ligne ou une espace collée."""
        set_code(client)
        challenge = client.get("/api/lock/rescue").json()["challenge"]
        sloppy = "  " + answer_for(challenge) + chr(10) + " "
        assert (
            client.post(
                "/api/lock/rescue", json={"answer": sloppy, "code": "5678"}
            ).status_code
            == 200
        )

    def test_the_shipped_key_cannot_forge_anything(self, client):
        """Le coeur de ce choix : ce qui voyage dans l'exécutable ne sait
        que vérifier. Personne ne peut en tirer une réponse."""
        assert "PUBLIC KEY" in PUBLIC
        assert "PRIVATE" not in PUBLIC

    def test_yesterdays_answer_is_worthless(self, client, monkeypatch):
        set_code(client)
        challenge = client.get("/api/lock/rescue").json()["challenge"]
        stale = answer_for(challenge)
        # Le lendemain, le défi a tourné.
        monkeypatch.setattr(vendor, "today_stamp", lambda: "99999")
        refused = client.post(
            "/api/lock/rescue", json={"answer": stale, "code": "5678"}
        )
        assert refused.status_code == 401

    def test_two_academies_do_not_share_an_answer(self, client, tmp_path, monkeypatch):
        """Le défi part de l'installation : dépanner l'un ne donne pas la
        clé de l'autre."""
        set_code(client)
        mine = client.get("/api/lock/rescue").json()["challenge"]
        monkeypatch.setattr(vendor, "vendor_key", lambda: PUBLIC)
        other_app = create_app(str(tmp_path / "autre.db"))
        with TestClient(other_app) as other:
            set_code(other)
            assert other.get("/api/lock/rescue").json()["challenge"] != mine

    def test_the_recovery_phrase_still_works_after_a_rescue(self, client):
        """Dépanner ne doit pas priver le propriétaire de sa propre
        porte : on lui rend une phrase neuve."""
        set_code(client)
        challenge = client.get("/api/lock/rescue").json()["challenge"]
        rescued = client.post(
            "/api/lock/rescue",
            json={"answer": answer_for(challenge), "code": "5678"},
        )
        phrase = rescued.json()["recovery_phrase"]
        assert len(phrase.split("-")) >= 4
        assert (
            client.post(
                "/api/lock/recover", json={"phrase": phrase, "code": "9012"}
            ).status_code
            == 200
        )

    def test_guessing_the_answer_gets_slower(self, client):
        set_code(client)
        wrong = base64.b64encode(b"n" * 64).decode()
        for _ in range(4):
            client.post("/api/lock/rescue", json={"answer": wrong, "code": "5678"})
        challenge = client.get("/api/lock/rescue").json()["challenge"]
        assert (
            client.post(
                "/api/lock/rescue",
                json={"answer": answer_for(challenge), "code": "5678"},
            ).status_code
            == 429
        )
