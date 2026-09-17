"""Round 35: solder le prof — mais LESQUELS, et combien chacun.

Un élève à trois matières a souvent trois professeurs. Le calcul les
servait tous depuis le début ; c'est l'écran qui n'annonçait qu'un seul
montant et ne disait « le professeur » qu'au singulier. Le propriétaire
lisait donc qu'il soldait un homme, alors qu'il en soldait trois.

Ce qui est montré doit être ce qui sera posé — la proposition et
l'écriture passent par le même partage, sinon l'écran annonce une
répartition et le registre en enregistre une autre.
"""

import pytest
from fastapi.testclient import TestClient
from test_api_v4 import setup_base

from app.adapters.api.app import create_app
from app.services import clock

DH = 100


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def three_teachers(client):
    """Un élève, trois matières, trois professeurs — le cas qui a dérouté."""
    level, first_class, first_teacher, _ = setup_base(client)
    classes = [first_class]
    teachers = [first_teacher]
    for name in ("Physique", "Arabe"):
        subject = client.post(
            "/api/subjects", json={"name": name, "level_id": level}
        ).json()["id"]
        teacher = client.post("/api/teachers", json={"name": f"Prof {name}"}).json()[
            "id"
        ]
        classes.append(
            client.post(
                "/api/classes",
                json={
                    "level_id": level,
                    "subject_id": subject,
                    "teacher_id": teacher,
                },
            ).json()["id"]
        )
        teachers.append(teacher)
    package = client.post(
        "/api/packages",
        json={
            "subject_count": 3,
            "monthly_price_centimes": 600 * DH,
            "level_id": level,
        },
    ).json()["id"]
    student = client.post(
        "/api/students", json={"name": "Yassine", "level_id": level}
    ).json()["id"]
    enrollment = client.post(
        "/api/enrollments",
        json={
            "student_id": student,
            "month": "2026-09",
            "package_id": package,
            "class_ids": classes,
        },
    ).json()["id"]
    return enrollment, teachers


class TestTheProposalNamesEveryone:
    def test_three_subjects_propose_three_professors(self, client):
        enrollment, teachers = three_teachers(client)

        proposal = client.get(f"/api/enrollments/{enrollment}/guarantee").json()

        assert len(proposal["teachers"]) == 3
        assert {line["teacher_id"] for line in proposal["teachers"]} == set(teachers)

    def test_each_one_is_named(self, client):
        """« 7 » ne se reconnaît pas ; « Prof Arabe » si. Sans le nom,
        l'écran n'a d'autre choix que de parler du « professeur »."""
        enrollment, _ = three_teachers(client)

        proposal = client.get(f"/api/enrollments/{enrollment}/guarantee").json()

        assert {line["name"] for line in proposal["teachers"]} == {
            "Ahmed",
            "Prof Physique",
            "Prof Arabe",
        }

    def test_the_parts_add_up_to_the_suggestion(self, client):
        enrollment, _ = three_teachers(client)

        proposal = client.get(f"/api/enrollments/{enrollment}/guarantee").json()

        assert (
            sum(line["amount_centimes"] for line in proposal["teachers"])
            == proposal["suggested_centimes"]
        )


class TestWhatIsShownIsWhatIsPosted:
    def test_a_chosen_amount_is_shown_split_across_them_all(self, client):
        enrollment, _ = three_teachers(client)

        proposal = client.get(
            f"/api/enrollments/{enrollment}/guarantee?amount_centimes={100 * DH}"
        ).json()

        assert sum(line["amount_centimes"] for line in proposal["teachers"]) == 100 * DH
        assert len(proposal["teachers"]) == 3

    def test_the_shown_split_is_the_one_recorded(self, client):
        """La garantie posée doit donner à chacun exactement ce que l'écran
        avait annoncé."""
        enrollment, _ = three_teachers(client)
        shown = client.get(
            f"/api/enrollments/{enrollment}/guarantee?amount_centimes={100 * DH}"
        ).json()["teachers"]

        posted = client.post(
            f"/api/enrollments/{enrollment}/guarantee",
            json={"amount_centimes": 100 * DH},
        ).json()["shares"]

        assert {line["teacher_id"]: line["amount_centimes"] for line in shown} == {
            line["teacher_id"]: line["amount_centimes"] for line in posted
        }

    def test_an_odd_amount_still_lands_exactly(self, client):
        """Trois parts sur 100,01 DH : le centime perdu au plancher revient
        au plus grand reste, et la somme retombe juste."""
        enrollment, _ = three_teachers(client)

        proposal = client.get(
            f"/api/enrollments/{enrollment}/guarantee?amount_centimes=10001"
        ).json()

        assert sum(line["amount_centimes"] for line in proposal["teachers"]) == 10001

    def test_nobody_is_paid_when_nothing_is_given(self, client):
        enrollment, _ = three_teachers(client)

        proposal = client.get(
            f"/api/enrollments/{enrollment}/guarantee?amount_centimes=0"
        ).json()

        assert proposal["teachers"] == []
