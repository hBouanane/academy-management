"""Round 35: le journal — ce qui a bougé, et quand.

Une erreur de saisie se corrige. Mais une correction silencieuse est pire
que l'erreur : six mois plus tard, devant une famille qui conteste, « le
paiement de septembre était sur octobre » doit rester répondable.

Le journal n'est pas un log technique. Il ne retient que ce qui déplace de
l'argent ou change ce qu'un mois affirme d'un élève -- un journal qui
contient « a ouvert le tableau de bord » est un journal que personne ne
lit, et donc un journal qui ne sert à rien le jour où il faudrait.
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


def journal(client, **params):
    return client.get("/api/journal", params=params).json()["entries"]


def actions(client, **params):
    return [entry["action"] for entry in journal(client, **params)]


class TestWhatGetsWrittenDown:
    def test_taking_money_is_written_down(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)

        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )

        entry = journal(client)[0]
        assert entry["action"] == "payment_in"
        assert entry["amount_centimes"] == 300 * DH
        assert entry["month"] == "2026-09"
        assert entry["subject_label"] == "Sami"

    def test_reversing_adds_a_line_and_keeps_the_first(self, client):
        """Une contre-passation n'efface pas l'encaissement : les deux ont
        eu lieu, et le journal montre les deux."""
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        payment = client.post(
            "/api/payments", json={"enrollment_id": enrollment}
        ).json()["payment_id"]

        client.post(f"/api/payments/{payment}/reverse", json={})

        assert actions(client)[:2] == ["payment_reversed", "payment_in"]

    def test_paying_a_teacher_and_cancelling_both_appear(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        payout = client.post(
            "/api/payouts",
            json={"kind": "teacher", "ref_id": teacher, "month": "2026-09"},
        ).json()["id"]

        client.delete(f"/api/payouts/{payout}")

        assert actions(client)[:2] == ["payout_cancelled", "payout"]
        assert journal(client)[0]["subject_label"] == "Ahmed"

    def test_settling_a_teacher_on_an_unpaid_month_is_written_down(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)

        client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": 50 * DH},
        )

        entry = journal(client)[0]
        assert entry["action"] == "guarantee"
        assert entry["amount_centimes"] == 50 * DH

    def test_enrolling_and_un_enrolling_are_written_down(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)

        client.delete(f"/api/enrollments/{enrollment}")

        assert actions(client)[:2] == ["enrollment_deleted", "enrollment"]


class TestWhatIsDeliberatelyNotWrittenDown:
    """Le bruit tue le journal. Les réglages n'y entrent pas."""

    def test_setting_up_the_academy_leaves_the_journal_empty(self, client):
        setup_base(client)

        assert journal(client) == []

    def test_reading_the_journal_does_not_write_to_it(self, client):
        level, class_id, _, package = setup_base(client)
        enroll(client, level, package, class_id)

        first = journal(client)
        second = journal(client)

        assert len(first) == len(second) == 1


class TestTheJournalDoesNotRewriteItself:
    def test_the_name_is_frozen_at_the_moment_of_writing(self, client):
        """Renommer un élève ne réécrit pas l'histoire : la ligne dit ce qui
        était affiché ce jour-là."""
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})

        client.patch(f"/api/students/{student}", json={"name": "Sami Bennis"})

        assert journal(client)[0]["subject_label"] == "Sami"

    def test_a_refused_deletion_leaves_no_line(self, client):
        """La ligne s'écrit APRES : une inscription qu'on n'a pas pu
        supprimer ne doit pas figurer au journal comme supprimée.

        Le bloqueur est ici un professeur soldé — une décision sur ce qui a
        été enseigné. Un paiement contre-passé ne bloque plus : son
        empreinte est nulle, il ne reste qu'une frappe à effacer."""
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": 50 * DH},
        )

        refused = client.delete(f"/api/enrollments/{enrollment}")

        assert refused.status_code == 409
        assert "enrollment_deleted" not in actions(client)

    def test_a_refused_action_leaves_no_line(self, client):
        """Une ligne présente a forcément eu lieu : l'écriture partage la
        transaction de l'action qu'elle décrit."""
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        before = len(journal(client))

        # Déjà encaissé : la garantie n'a rien à garantir.
        refused = client.post(
            f"/api/enrollments/{enrollment}/guarantee", json={"never_came": True}
        )

        assert refused.status_code == 409
        assert len(journal(client)) == before


class TestFindingOneThingAgain:
    """Le journal sert le jour où il faut retrouver UNE ligne."""

    def test_it_can_be_narrowed_to_one_month(self, client):
        level, class_id, _, package = setup_base(client)
        _, september = enroll(client, level, package, class_id)
        _, october = enroll(
            client, level, package, class_id, name="Nadia", month="2026-10"
        )
        client.post("/api/payments", json={"enrollment_id": september})
        client.post("/api/payments", json={"enrollment_id": october})

        assert len(journal(client, month="2026-10")) == 2
        assert {entry["month"] for entry in journal(client, month="2026-10")} == {
            "2026-10"
        }

    def test_it_can_be_narrowed_to_one_student(self, client):
        level, class_id, _, package = setup_base(client)
        sami, first = enroll(client, level, package, class_id)
        _, second = enroll(client, level, package, class_id, name="Nadia")
        client.post("/api/payments", json={"enrollment_id": first})
        client.post("/api/payments", json={"enrollment_id": second})

        narrowed = journal(client, subject_kind="student", subject_id=sami)

        assert [entry["subject_label"] for entry in narrowed] == ["Sami", "Sami"]

    def test_the_next_page_starts_where_the_previous_stopped(self, client):
        level, class_id, _, package = setup_base(client)
        for index in range(5):
            enroll(client, level, package, class_id, name=f"Eleve {index}")

        first = client.get("/api/journal?limit=2").json()
        second = client.get(
            f"/api/journal?limit=2&before_id={first['next_before_id']}"
        ).json()

        assert [entry["id"] for entry in first["entries"]] == [5, 4]
        assert [entry["id"] for entry in second["entries"]] == [3, 2]

    def test_the_most_recent_comes_first(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})

        ids = [entry["id"] for entry in journal(client)]

        assert ids == sorted(ids, reverse=True)
