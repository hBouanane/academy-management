"""Round 19 : avancer au professeur ce qu'on décide, et une seule fois.

Quand un élève ne paie pas, l'académie avance quand même au professeur.
Le montant proposé vient des jours enseignés — mais c'est le
propriétaire qui décide : il peut donner moins ce mois-ci, ou davantage.

La règle qui compte vient après. Si l'élève finit par payer, le
professeur ne doit PAS être payé deux fois : il reçoit seulement ce
qu'il n'a pas encore touché. Et si on lui avait donné plus que sa part,
on ne lui reprend rien — un cadeau reste un cadeau.
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


def teacher_due(client, teacher_id, month="2026-09"):
    """Ce que la caisse dit devoir à ce professeur pour le mois."""
    caisse = client.get(f"/api/caisse?month={month}").json()
    line = next(
        entry
        for entry in caisse["lines"]
        if entry["kind"] == "teacher" and entry["ref_id"] == teacher_id
    )
    return line["due_centimes"]


def _line(client, teacher_id, month="2026-09"):
    caisse = client.get(f"/api/caisse?month={month}").json()
    return next(
        entry
        for entry in caisse["lines"]
        if entry["kind"] == "teacher" and entry["ref_id"] == teacher_id
    )


def _paid(client, teacher_id):
    return _line(client, teacher_id)["paid_centimes"]


def _remaining(client, teacher_id):
    return _line(client, teacher_id)["remaining_centimes"]


def setup_unpaid(client):
    level, class_id, teacher, package = setup_base(client)
    _, enrollment = enroll(client, level, package, class_id)
    return teacher, enrollment


class TestDecidingTheAmount:
    def test_the_proposed_amount_is_what_the_days_say(self, client):
        teacher, enrollment = setup_unpaid(client)
        proposal = client.get(f"/api/enrollments/{enrollment}/guarantee")
        assert proposal.status_code == 200, proposal.text
        # Le mois entier enseigné : la totalité de sa part.
        assert proposal.json()["suggested_centimes"] == teacher_due(client, teacher)

    def test_the_owner_can_give_less(self, client):
        _teacher, enrollment = setup_unpaid(client)
        posted = client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": 100 * DH},
        )
        assert posted.status_code == 200, posted.text
        assert posted.json()["amount_centimes"] == 100 * DH

    def test_the_owner_can_give_more(self, client):
        _teacher, enrollment = setup_unpaid(client)
        posted = client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": 250 * DH},
        )
        assert posted.json()["amount_centimes"] == 250 * DH

    def test_nothing_at_all_is_allowed(self, client):
        """« Il n'est jamais venu » : on n'avance rien, et le mois reste
        un impayé comme avant."""
        _teacher, enrollment = setup_unpaid(client)
        posted = client.post(
            f"/api/enrollments/{enrollment}/guarantee", json={"amount_centimes": 0}
        )
        assert posted.status_code == 200
        assert posted.json()["amount_centimes"] == 0

    def test_more_than_the_month_is_refused(self, client):
        _teacher, enrollment = setup_unpaid(client)
        refused = client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": 5000 * DH},
        )
        assert refused.status_code == 422
        assert "300,00" in refused.json()["detail"]

    def test_a_negative_amount_is_refused(self, client):
        _teacher, enrollment = setup_unpaid(client)
        refused = client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": -1},
        )
        assert refused.status_code == 422


class TestNeverPayingTwice:
    """Le cœur de la demande : l'élève finit par payer APRÈS l'avance."""

    def test_the_professor_only_receives_the_difference(self, client):
        teacher, enrollment = setup_unpaid(client)
        full = teacher_due(client, teacher)
        client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": 100 * DH},
        )
        # Il a déjà touché 100 DH d'avance.
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-10"},
        )
        # Après encaissement, son dû du mois reste sa part totale : il a
        # touché 100 en avance, le reste vient du paiement.
        assert teacher_due(client, teacher) == full

    def test_the_academy_takes_its_advance_back(self, client):
        _teacher, enrollment = setup_unpaid(client)
        client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": 100 * DH},
        )
        before = client.get("/api/caisse?month=2026-09").json()
        owner_before = next(e for e in before["lines"] if e["kind"] == "owner")[
            "due_centimes"
        ]
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-10"},
        )
        after = client.get("/api/caisse?month=2026-09").json()
        owner_after = next(e for e in after["lines"] if e["kind"] == "owner")[
            "due_centimes"
        ]
        # L'académie avait avancé 100 DH ; elle les récupère sur
        # l'encaissement, en plus de sa part habituelle.
        assert owner_after > owner_before

    def test_the_whole_story_end_to_end(self, client):
        """Le scénario complet, celui qui compte : on avance une partie,
        on la verse, puis l'élève paie. Le professeur ne doit toucher la
        même somme qu'une seule fois."""
        teacher, enrollment = setup_unpaid(client)
        full = teacher_due(client, teacher)  # 180 DH gagnés sur le mois

        # 1. On décide de n'avancer que 100 DH.
        client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": 100 * DH},
        )
        assert teacher_due(client, teacher) == 100 * DH

        # 2. On les lui verse : il ne reste rien à sortir.
        client.post(
            "/api/payouts",
            json={"kind": "teacher", "ref_id": teacher, "month": "2026-09"},
        )
        assert _remaining(client, teacher) == 0

        # 3. L'élève finit par payer : le professeur retrouve son dû
        #    complet, mais on ne lui redonne QUE la différence.
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-10"},
        )
        assert teacher_due(client, teacher) == full
        assert _paid(client, teacher) == 100 * DH
        assert _remaining(client, teacher) == full - 100 * DH

    def test_guaranteeing_twice_is_refused(self, client):
        _teacher, enrollment = setup_unpaid(client)
        client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": 50 * DH},
        )
        again = client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": 50 * DH},
        )
        assert again.status_code == 409
