"""Round 25b : un mois à moitié payé reste dû pour le reste.

Défaut trouvé en écrivant le message de relance : la liste des impayés
ne retenait que les mois où RIEN n'avait été versé. Une famille qui
règle 100 DH sur 300 disparaissait de la liste — et les 200 restants
avec elle.

Or l'avance existe précisément pour ça : on encaisse une partie, le
reste est dû. « Impayés cumulés » doit le compter, sinon le
propriétaire réclame moins que ce qu'on lui doit.
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


def owed_by(client, name, month="2026-09"):
    listed = client.get(f"/api/reports/arrears?up_to_month={month}").json()
    entry = next((row for row in listed if row["student_name"] == name), None)
    return entry["total_owed"] if entry else 0


class TestWhatIsStillOwed:
    def test_a_month_never_paid_is_owed_whole(self, client):
        level, class_id, _teacher, package = setup_base(client)
        enroll(client, level, package, class_id)
        assert owed_by(client, "Sami") == 300 * DH

    def test_a_month_half_paid_owes_the_rest(self, client):
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            "/api/payments",
            json={
                "enrollment_id": enrollment,
                "paid_on": "2026-09-03",
                "amount_centimes": 100 * DH,
            },
        )
        assert owed_by(client, "Sami") == 200 * DH

    def test_a_month_fully_paid_owes_nothing(self, client):
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        assert owed_by(client, "Sami") == 0

    def test_completing_the_advance_clears_it(self, client):
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        posted = client.post(
            "/api/payments",
            json={
                "enrollment_id": enrollment,
                "paid_on": "2026-09-03",
                "amount_centimes": 100 * DH,
            },
        ).json()
        client.post(f"/api/payments/{posted['payment_id']}/complete", json={})
        assert owed_by(client, "Sami") == 0

    def test_a_reversed_payment_puts_the_whole_month_back(self, client):
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        posted = client.post(
            "/api/payments",
            json={
                "enrollment_id": enrollment,
                "paid_on": "2026-09-03",
                "amount_centimes": 100 * DH,
            },
        ).json()
        client.post(
            f"/api/payments/{posted['payment_id']}/reverse", json={"reason": "erreur"}
        )
        assert owed_by(client, "Sami") == 300 * DH
