"""Round 26 : l'avance versée au prof compte pour sa classe.

Quand on solde un professeur avant que la famille ait payé, l'écriture
n'a pas de paiement — il n'existe pas encore. Elle porte l'inscription.

Le détail par classe ne retenait que les lignes passées par un paiement.
L'avance disparaissait donc du tableau, mais son annulation, elle, y
restait : la colonne « Gagné » affichait 145,16 DH de moins que le total
du mois affiché juste au-dessus. Deux chiffres qui se contredisent sur
la même page font douter des deux.
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


def profile(client, teacher, month="2026-09"):
    return client.get(f"/api/teachers/{teacher}/profile?month={month}").json()


def classes_total(page):
    return sum(row["earned_centimes"] for row in page["classes"])


def month_total(page, month="2026-09"):
    return next(e["earned"] for e in page["history"] if e["month"] == month)


class TestTheAdvanceCountsForItsClass:
    def test_an_advance_alone_lands_on_the_class(self, client):
        """Rien n'est encore paye : l'avance est tout ce qu'il a touche."""
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": 120 * DH},
        )
        page = profile(client, teacher)
        assert classes_total(page) == 120 * DH

    def test_the_two_totals_agree(self, client):
        """Le total des classes et le total du mois disent la meme chose."""
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": 120 * DH},
        )
        page = profile(client, teacher)
        assert classes_total(page) == month_total(page)

    def test_they_still_agree_once_the_family_pays(self, client):
        """L'avance s'annule, le vrai partage arrive : toujours d'accord."""
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": 120 * DH},
        )
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        page = profile(client, teacher)
        assert classes_total(page) == month_total(page)

    def test_an_ordinary_payment_is_untouched(self, client):
        """Le cas courant ne bouge pas : c'est le plus important."""
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        page = profile(client, teacher)
        assert classes_total(page) == month_total(page)
        assert classes_total(page) > 0
