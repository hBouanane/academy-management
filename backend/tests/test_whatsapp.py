"""Round 18 : prévenir la famille par WhatsApp.

Le propriétaire recopie à la main, dans WhatsApp, ce que l'application
sait déjà : qui est inscrit, qui a payé, qui doit encore. Recopier, c'est
se tromper de montant un jour sur dix.

L'application prépare donc le message et ouvre WhatsApp dessus. Elle
n'envoie RIEN toute seule : c'est lui qui relit et qui appuie. Un
logiciel qui écrit aux familles sans qu'on ait vu le texte est un
logiciel dont on se méfie.

Le numéro se choisit — l'élève a le sien, le père le sien, et ce n'est
pas au collégien qu'on réclame un impayé.
"""

import pytest
from fastapi.testclient import TestClient
from test_api_v4 import enroll, setup_base

from app.adapters.api.app import create_app
from app.domain.contact import whatsapp_number
from app.services import clock

DH = 100


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def with_phones(client, student_id, phones):
    response = client.patch(f"/api/students/{student_id}", json={"phones": phones})
    assert response.status_code == 200, response.text


def messages(client, student_id, month="2026-09"):
    response = client.get(f"/api/students/{student_id}/messages?month={month}")
    assert response.status_code == 200, response.text
    return response.json()


class TestTheNumberItself:
    def test_a_local_number_becomes_international(self):
        # WhatsApp ne connaît pas les 0 nationaux.
        assert whatsapp_number("0661234567") == "212661234567"

    def test_spaces_and_dashes_are_forgiven(self):
        assert whatsapp_number("06 61-23 45 67") == "212661234567"

    def test_an_international_number_is_left_alone(self):
        assert whatsapp_number("+212661234567") == "212661234567"
        assert whatsapp_number("212661234567") == "212661234567"

    def test_a_foreign_number_keeps_its_country(self):
        assert whatsapp_number("+33612345678") == "33612345678"

    def test_something_that_is_not_a_number_gives_nothing(self):
        assert whatsapp_number("à demander") is None
        assert whatsapp_number("") is None


class TestWhatThereIsToSay:
    def test_an_enrolled_student_gets_a_confirmation(self, client):
        level, class_id, _teacher, package = setup_base(client)
        student, _ = enroll(client, level, package, class_id)
        with_phones(client, student, [{"tag": "Père", "number": "0661234567"}])
        offer = messages(client, student)
        kinds = [entry["kind"] for entry in offer["messages"]]
        assert "enrolled" in kinds
        confirmation = next(e for e in offer["messages"] if e["kind"] == "enrolled")
        assert "Sami" in confirmation["text"]
        assert "septembre" in confirmation["text"].lower()

    def test_an_unpaid_month_offers_a_reminder_with_the_amount(self, client):
        level, class_id, _teacher, package = setup_base(client)
        student, _ = enroll(client, level, package, class_id)
        with_phones(client, student, [{"tag": "Père", "number": "0661234567"}])
        reminder = next(
            e for e in messages(client, student)["messages"] if e["kind"] == "unpaid"
        )
        assert "300,00 DH" in reminder["text"]

    def test_a_paid_month_offers_a_receipt_and_no_reminder(self, client):
        level, class_id, _teacher, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id)
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        with_phones(client, student, [{"tag": "Père", "number": "0661234567"}])
        kinds = [e["kind"] for e in messages(client, student)["messages"]]
        assert "paid" in kinds
        assert "unpaid" not in kinds

    def test_a_student_with_no_month_has_nothing_to_announce(self, client):
        level, *_ = setup_base(client)
        student = client.post(
            "/api/students", json={"name": "Nouveau", "level_id": level}
        ).json()["id"]
        assert messages(client, student)["messages"] == []

    def test_every_number_is_offered_with_its_tag(self, client):
        level, class_id, _teacher, package = setup_base(client)
        student, _ = enroll(client, level, package, class_id)
        with_phones(
            client,
            student,
            [
                {"tag": "Père", "number": "0661234567"},
                {"tag": "Étudiant", "number": "0770000000"},
            ],
        )
        offer = messages(client, student)
        assert [(p["tag"], p["whatsapp"]) for p in offer["phones"]] == [
            ("Père", "212661234567"),
            ("Étudiant", "212770000000"),
        ]

    def test_a_stored_number_is_always_usable(self, client):
        """La fiche refuse deja tout ce qui n'est pas dix chiffres : ce
        qui est enregistre se convertit forcement."""
        level, class_id, _teacher, package = setup_base(client)
        student, _ = enroll(client, level, package, class_id)
        refused = client.patch(
            f"/api/students/{student}",
            json={"phones": [{"tag": "Père", "number": "à demander"}]},
        )
        assert refused.status_code == 422
        with_phones(client, student, [{"tag": "Père", "number": "0661234567"}])
        assert messages(client, student)["phones"][0]["whatsapp"] is not None


class TestOpeningWhatsApp:
    def test_it_hands_back_the_address_it_opened(self, client, monkeypatch):
        opened = []
        from app.adapters.api import routes

        monkeypatch.setattr(routes, "_open_outside", opened.append)
        done = client.post(
            "/api/whatsapp", json={"phone": "212661234567", "text": "Bonjour"}
        )
        assert done.status_code == 200
        assert done.json()["url"].startswith("https://wa.me/212661234567?text=")
        assert opened == [done.json()["url"]]

    def test_the_text_survives_accents_and_line_breaks(self, client, monkeypatch):
        from app.adapters.api import routes

        monkeypatch.setattr(routes, "_open_outside", lambda url: None)
        done = client.post(
            "/api/whatsapp",
            json={"phone": "212661234567", "text": "Réglé : 300,00 DH\nMerci"},
        )
        url = done.json()["url"]
        assert "%C3%A9" in url  # le é encodé
        assert " " not in url

    def test_an_unusable_number_is_refused(self, client):
        refused = client.post(
            "/api/whatsapp", json={"phone": "à demander", "text": "Bonjour"}
        )
        assert refused.status_code == 422
