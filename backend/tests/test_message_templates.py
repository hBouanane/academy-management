"""Round 20 : ses messages à lui.

Nos trois modèles sont en français poli. Lui écrit à ses familles comme
il leur parle : en darija, court et direct. Un logiciel qui impose sa
façon de dire les choses finit inutilisé — il recopiera à la main, et se
trompera de montant.

Il écrit donc les siens, une fois, et les retrouve sur n'importe quel
élève. Les {repères} sont remplis au moment d'ouvrir WhatsApp.
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


def enrolled(client):
    level, class_id, _teacher, package = setup_base(client)
    student, _ = enroll(client, level, package, class_id)
    client.patch(
        f"/api/students/{student}",
        json={"phones": [{"tag": "Père", "number": "0661234567"}]},
    )
    return student


def messages(client, student_id, month="2026-09"):
    return client.get(f"/api/students/{student_id}/messages?month={month}").json()


class TestKeepingHisOwn:
    def test_a_fresh_install_has_none(self, client):
        assert client.get("/api/message-templates").json() == []

    def test_he_writes_one_and_finds_it_again(self, client):
        created = client.post(
            "/api/message-templates",
            json={"label": "Rappel darija", "body": "salam khouya {eleve}"},
        )
        assert created.status_code == 201, created.text
        kept = client.get("/api/message-templates").json()
        assert [(t["label"], t["body"]) for t in kept] == [
            ("Rappel darija", "salam khouya {eleve}")
        ]

    def test_he_can_correct_it(self, client):
        one = client.post(
            "/api/message-templates", json={"label": "Rappel", "body": "salam"}
        ).json()
        client.patch(
            f"/api/message-templates/{one['id']}",
            json={"body": "salam khouya {eleve}, had chhar makhallastich"},
        )
        assert "makhallastich" in client.get("/api/message-templates").json()[0]["body"]

    def test_he_can_throw_it_away(self, client):
        one = client.post(
            "/api/message-templates", json={"label": "Essai", "body": "x"}
        ).json()
        client.delete(f"/api/message-templates/{one['id']}")
        assert client.get("/api/message-templates").json() == []

    def test_an_empty_message_is_refused(self, client):
        refused = client.post(
            "/api/message-templates", json={"label": "Vide", "body": "   "}
        )
        assert refused.status_code == 422

    def test_they_keep_the_order_he_gave_them(self, client):
        for label in ("Premier", "Deuxieme", "Troisieme"):
            client.post("/api/message-templates", json={"label": label, "body": "x"})
        kept = client.get("/api/message-templates").json()
        assert [t["label"] for t in kept] == ["Premier", "Deuxieme", "Troisieme"]


class TestFillingThemIn:
    def test_the_student_name_lands_in_the_message(self, client):
        student = enrolled(client)
        client.post(
            "/api/message-templates",
            json={"label": "Rappel", "body": "salam khouya {eleve}"},
        )
        mine = [
            entry
            for entry in messages(client, student)["messages"]
            if entry["kind"].startswith("custom")
        ]
        assert mine[0]["text"] == "salam khouya Sami"

    def test_every_marker_is_filled(self, client):
        student = enrolled(client)
        client.post(
            "/api/message-templates",
            json={
                "label": "Complet",
                "body": "{eleve} · {mois} · {montant} · {classes} · {academie}",
            },
        )
        text = next(
            entry["text"]
            for entry in messages(client, student)["messages"]
            if entry["kind"].startswith("custom")
        )
        assert "Sami" in text
        assert "septembre" in text.lower()
        assert "300,00 DH" in text
        assert "Math" in text
        assert "{" not in text  # plus aucun repère en attente

    def test_an_unknown_marker_is_left_visible(self, client):
        """Mieux vaut qu'il voie « {truc} » dans l'aperçu que de le
        laisser croire qu'on a compris ce qu'il voulait dire."""
        student = enrolled(client)
        client.post(
            "/api/message-templates", json={"label": "Bizarre", "body": "{truc}"}
        )
        text = next(
            entry["text"]
            for entry in messages(client, student)["messages"]
            if entry["kind"].startswith("custom")
        )
        assert text == "{truc}"

    def test_his_templates_come_after_ours(self, client):
        student = enrolled(client)
        client.post("/api/message-templates", json={"label": "Sien", "body": "x"})
        kinds = [entry["kind"] for entry in messages(client, student)["messages"]]
        assert kinds.index("enrolled") < kinds.index("custom-1")

    def test_without_an_enrollment_his_templates_stay_hidden(self, client):
        """Rien à annoncer : ni les nôtres, ni les siens — le montant
        n'existerait pas."""
        level, *_ = setup_base(client)
        student = client.post(
            "/api/students", json={"name": "Nouveau", "level_id": level}
        ).json()["id"]
        client.post("/api/message-templates", json={"label": "Sien", "body": "x"})
        assert messages(client, student)["messages"] == []
