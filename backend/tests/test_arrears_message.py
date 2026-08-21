"""Round 25 : le message pour une famille qui doit plusieurs mois.

Le rappel ordinaire parle d'un mois. Mais une famille qui traîne depuis
la rentrée en doit trois, et lui écrire trois fois serait ridicule —
comme lui réclamer 300 DH quand elle en doit 900.

Un modèle de plus, deux repères de plus : le total dû et la liste des
mois. Il ne se propose que quand il y a vraiment plusieurs mois en
retard, sinon le rappel du mois suffit.
"""

import pytest
from fastapi.testclient import TestClient
from test_api_v4 import enroll, setup_base

from app.adapters.api.app import create_app
from app.services import clock

DH = 100


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "current_month", lambda: "2026-11")
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def owing(client, months):
    """Un élève inscrit ces mois-là, et qui n'a rien payé."""
    level, class_id, _teacher, package = setup_base(client)
    student = client.post(
        "/api/students", json={"name": "Sami", "level_id": level}
    ).json()["id"]
    for month in months:
        client.post(
            "/api/enrollments",
            json={
                "student_id": student,
                "month": month,
                "package_id": package,
                "class_ids": [class_id],
            },
        )
    client.patch(
        f"/api/students/{student}",
        json={"phones": [{"tag": "Père", "number": "0661234567"}]},
    )
    return student


def offered(client, student_id, month="2026-11"):
    return client.get(f"/api/students/{student_id}/messages?month={month}").json()[
        "messages"
    ]


def with_template(client, body, when="arrears"):
    made = client.post(
        "/api/message-templates",
        json={"label": "Relance", "body": body, "shown_when": when},
    )
    assert made.status_code == 201, made.text


class TestWhenItAppears:
    def test_three_unpaid_months_bring_it_out(self, client):
        student = owing(client, ["2026-09", "2026-10", "2026-11"])
        with_template(client, "{eleve} doit {impayes}")
        assert "Relance" in [entry["label"] for entry in offered(client, student)]

    def test_a_single_unpaid_month_does_not(self, client):
        """Le rappel du mois suffit : deux messages pour la même dette
        se contrediraient."""
        student = owing(client, ["2026-11"])
        with_template(client, "{eleve} doit {impayes}")
        assert "Relance" not in [entry["label"] for entry in offered(client, student)]

    def test_a_family_up_to_date_never_sees_it(self, client):
        level, class_id, _teacher, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id, month="2026-11")
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-11-03"},
        )
        with_template(client, "{eleve} doit {impayes}")
        assert "Relance" not in [entry["label"] for entry in offered(client, student)]


class TestWhatItSays:
    def test_the_total_covers_every_month_owed(self, client):
        student = owing(client, ["2026-09", "2026-10", "2026-11"])
        with_template(client, "{eleve} doit {impayes}")
        text = next(
            entry["text"]
            for entry in offered(client, student)
            if entry["label"] == "Relance"
        )
        # Trois mois à 300 DH.
        assert "900,00 DH" in text
        assert "Sami" in text

    def test_it_can_name_the_months(self, client):
        student = owing(client, ["2026-09", "2026-10", "2026-11"])
        with_template(client, "Mois en retard : {mois_impayes}")
        text = next(
            entry["text"]
            for entry in offered(client, student)
            if entry["label"] == "Relance"
        )
        assert "septembre" in text.lower()
        assert "octobre" in text.lower()
        assert "novembre" in text.lower()

    def test_a_partly_paid_month_counts_only_what_is_left(self, client):
        student = owing(client, ["2026-09", "2026-10", "2026-11"])
        overview = client.get("/api/months/2026-09/overview").json()
        enrollment = next(
            row["enrollment"]["id"]
            for row in overview
            if row["student_id"] == student and row["enrollment"]
        )
        client.post(
            "/api/payments",
            json={
                "enrollment_id": enrollment,
                "paid_on": "2026-09-03",
                "amount_centimes": 100 * DH,
            },
        )
        with_template(client, "{impayes}")
        text = next(
            entry["text"]
            for entry in offered(client, student)
            if entry["label"] == "Relance"
        )
        # 900 dus, 100 verses : il reste 800.
        assert "800,00 DH" in text

    def test_the_ordinary_markers_still_work(self, client):
        student = owing(client, ["2026-09", "2026-10", "2026-11"])
        with_template(client, "{eleve} · {academie} · {impayes}")
        text = next(
            entry["text"]
            for entry in offered(client, student)
            if entry["label"] == "Relance"
        )
        assert "{" not in text


class TestTheTemplateHeGetsForFree:
    """Il ne doit pas avoir à l'écrire lui-même pour découvrir qu'il existe."""

    def test_a_ready_made_arrears_template_is_installed(self, client):
        listed = client.get("/api/message-templates").json()
        arrears = [t for t in listed if t["shown_when"] == "arrears"]
        assert len(arrears) == 1

    def test_it_speaks_of_the_whole_debt_not_one_month(self, client):
        listed = client.get("/api/message-templates").json()
        (ready,) = [t for t in listed if t["shown_when"] == "arrears"]
        assert "{impayes}" in ready["body"]
        assert "{mois_impayes}" in ready["body"]
