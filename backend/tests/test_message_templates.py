"""Round 20 : les messages, tous modifiables.

Trois modèles sont posés à l'installation — confirmation, reçu, rappel.
Ce ne sont pas des messages du logiciel : ce sont les SIENS dès le
premier jour. Il les reprend à son goût, les traduit en darija, les
jette, en ajoute d'autres.

Chacun dit quand il sert. Proposer « vous n'avez pas payé » à une
famille qui vient de régler serait le meilleur moyen de faire
désinstaller l'application.
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


def enrolled(client, paid=False):
    level, class_id, _teacher, package = setup_base(client)
    student, enrollment = enroll(client, level, package, class_id)
    client.patch(
        f"/api/students/{student}",
        json={"phones": [{"tag": "Père", "number": "0661234567"}]},
    )
    if paid:
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
    return student


def offered(client, student_id, month="2026-09"):
    return client.get(f"/api/students/{student_id}/messages?month={month}").json()[
        "messages"
    ]


class TestWhatComesInTheBox:
    def test_a_fresh_install_already_has_three(self, client):
        kept = client.get("/api/message-templates").json()
        assert [entry["label"] for entry in kept] == [
            "Confirmation d'inscription",
            "Reçu de paiement",
            "Rappel de paiement",
        ]

    def test_they_say_when_they_serve(self, client):
        kept = client.get("/api/message-templates").json()
        assert [entry["shown_when"] for entry in kept] == ["always", "paid", "unpaid"]

    def test_they_are_written_with_markers_he_can_move(self, client):
        confirmation = client.get("/api/message-templates").json()[0]
        assert "{eleve}" in confirmation["body"]
        assert "{montant}" in confirmation["body"]

    def test_he_can_rewrite_one_of_ours(self, client):
        rappel = client.get("/api/message-templates").json()[2]
        client.patch(
            f"/api/message-templates/{rappel['id']}",
            json={"body": "salam khouya {eleve}, had chhar makhallastich"},
        )
        assert (
            client.get("/api/message-templates").json()[2]["body"]
            == "salam khouya {eleve}, had chhar makhallastich"
        )

    def test_he_can_throw_one_of_ours_away(self, client):
        first = client.get("/api/message-templates").json()[0]
        client.delete(f"/api/message-templates/{first['id']}")
        assert len(client.get("/api/message-templates").json()) == 2


class TestAddingHisOwn:
    def test_his_join_the_list_at_the_end(self, client):
        client.post(
            "/api/message-templates",
            json={"label": "Rappel darija", "body": "salam {eleve}"},
        )
        assert [
            entry["label"] for entry in client.get("/api/message-templates").json()
        ][-1] == "Rappel darija"

    def test_he_says_when_his_own_serves(self, client):
        client.post(
            "/api/message-templates",
            json={
                "label": "Rappel darija",
                "body": "makhallastich",
                "shown_when": "unpaid",
            },
        )
        mine = client.get("/api/message-templates").json()[-1]
        assert mine["shown_when"] == "unpaid"

    def test_an_empty_message_is_refused(self, client):
        refused = client.post(
            "/api/message-templates", json={"label": "Vide", "body": "   "}
        )
        assert refused.status_code == 422


class TestChoosingWhatToShow:
    def test_an_unpaid_month_gets_the_reminder_not_the_receipt(self, client):
        student = enrolled(client)
        labels = [entry["label"] for entry in offered(client, student)]
        assert "Rappel de paiement" in labels
        assert "Reçu de paiement" not in labels

    def test_a_paid_month_gets_the_receipt_not_the_reminder(self, client):
        student = enrolled(client, paid=True)
        labels = [entry["label"] for entry in offered(client, student)]
        assert "Reçu de paiement" in labels
        assert "Rappel de paiement" not in labels

    def test_his_darija_reminder_follows_the_same_rule(self, client):
        """Le sien doit se taire aussi quand la famille a payé."""
        client.post(
            "/api/message-templates",
            json={
                "label": "Rappel darija",
                "body": "salam {eleve}, makhallastich",
                "shown_when": "unpaid",
            },
        )
        assert "Rappel darija" in [
            entry["label"] for entry in offered(client, enrolled(client))
        ]

    def test_without_an_enrollment_nothing_is_offered(self, client):
        level, *_ = setup_base(client)
        student = client.post(
            "/api/students", json={"name": "Nouveau", "level_id": level}
        ).json()["id"]
        assert offered(client, student) == []


class TestFillingThemIn:
    def test_every_marker_is_filled(self, client):
        client.post(
            "/api/message-templates",
            json={
                "label": "Complet",
                "body": "{eleve} · {mois} · {montant} · {classes} · {academie}",
            },
        )
        text = next(
            entry["text"]
            for entry in offered(client, enrolled(client))
            if entry["label"] == "Complet"
        )
        assert "Sami" in text
        assert "septembre" in text.lower()
        assert "300,00 DH" in text
        assert "Math" in text
        assert "{" not in text  # plus aucun repère en attente

    def test_an_unknown_marker_is_left_visible(self, client):
        """Mieux vaut qu'il voie « {truc} » dans l'aperçu que de le
        laisser croire qu'on a compris ce qu'il voulait dire."""
        client.post(
            "/api/message-templates", json={"label": "Bizarre", "body": "{truc}"}
        )
        text = next(
            entry["text"]
            for entry in offered(client, enrolled(client))
            if entry["label"] == "Bizarre"
        )
        assert text == "{truc}"

    def test_the_default_reminder_carries_the_real_amount(self, client):
        text = next(
            entry["text"]
            for entry in offered(client, enrolled(client))
            if entry["label"] == "Rappel de paiement"
        )
        assert "300,00 DH" in text
        assert "Sami" in text
