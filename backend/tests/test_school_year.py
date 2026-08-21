"""Round 26 : l'année scolaire — la saison, et le mois où elle s'arrête.

Une académie ne vit pas en mois, elle vit en rentrées. Sans borne, on
n'avait que douze bilans séparés et aucun bilan de saison.

Le passage d'une année à l'autre ne suppose rien : à la clôture, les
élèves sont archivés. On ne présume pas qu'ils reviendront — celui qui
revient est réinscrit comme d'habitude, et il retrouve sa place. Ce
qu'une famille doit, en revanche, la suit : l'argent dû ne s'efface pas
parce que le calendrier a tourné.
"""

import pytest
from fastapi.testclient import TestClient
from test_api_v4 import enroll, setup_base

from app.adapters.api.app import create_app
from app.domain.school_year import months_between, year_holding
from app.services import clock

DH = 100


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


class TestTheMonthsOfASeason:
    def test_a_school_year_runs_from_its_start_to_its_stop(self):
        assert months_between("2026-09", "2027-06") == [
            "2026-09",
            "2026-10",
            "2026-11",
            "2026-12",
            "2027-01",
            "2027-02",
            "2027-03",
            "2027-04",
            "2027-05",
            "2027-06",
        ]

    def test_a_single_month_year_is_that_month(self):
        assert months_between("2026-09", "2026-09") == ["2026-09"]

    def test_a_stop_before_the_start_holds_no_month(self):
        """Mieux vaut une saison vide qu'une boucle qui ne finit pas."""
        assert months_between("2026-09", "2026-06") == []

    def test_december_to_january_crosses_the_year(self):
        assert months_between("2026-12", "2027-01") == ["2026-12", "2027-01"]


class TestWhichSeasonAMonthBelongsTo:
    def test_a_month_inside_the_season_finds_it(self):
        seasons = [
            {"id": 1, "start_month": "2025-09", "end_month": "2026-06"},
            {"id": 2, "start_month": "2026-09", "end_month": "2027-06"},
        ]
        assert year_holding(seasons, "2026-11")["id"] == 2
        assert year_holding(seasons, "2025-10")["id"] == 1

    def test_a_month_in_the_summer_belongs_to_none(self):
        """Juillet ne s'invente pas une saison : il n'en a pas."""
        seasons = [{"id": 1, "start_month": "2026-09", "end_month": "2027-06"}]
        assert year_holding(seasons, "2026-07") is None


def make_year(client, start="2026-09", end="2027-06", name="2026-2027"):
    return client.post(
        "/api/school-years",
        json={"name": name, "start_month": start, "end_month": end},
    )


class TestTheSeasonHeDefines:
    def test_he_names_the_month_where_it_stops(self, client):
        made = make_year(client)
        assert made.status_code == 201, made.text
        assert made.json()["end_month"] == "2027-06"

    def test_a_season_that_stops_before_it_starts_is_refused(self, client):
        refused = make_year(client, start="2026-09", end="2026-06")
        assert refused.status_code == 422

    def test_he_can_move_the_stop_afterwards(self, client):
        year = make_year(client).json()["id"]
        client.patch(f"/api/school-years/{year}", json={"end_month": "2027-07"})
        listed = client.get("/api/school-years").json()
        assert [y["end_month"] for y in listed if y["id"] == year] == ["2027-07"]


class TestPassingToTheNextSeason:
    def test_closing_archives_every_student(self, client):
        level, class_id, _teacher, package = setup_base(client)
        enroll(client, level, package, class_id)
        year = make_year(client).json()["id"]

        client.post(f"/api/school-years/{year}/close", json={})

        listed = client.get("/api/students?month=2026-09").json()
        names = [s["name"] for s in listed]
        assert "Sami" not in names

    def test_the_archived_student_is_still_there_to_be_taken_back(self, client):
        """Archivé n'est pas supprimé : son histoire reste entière."""
        level, class_id, _teacher, package = setup_base(client)
        student, _ = enroll(client, level, package, class_id)
        year = make_year(client).json()["id"]
        client.post(f"/api/school-years/{year}/close", json={})

        again = client.patch(f"/api/students/{student}", json={"is_active": True})
        assert again.status_code == 200
        listed = client.get("/api/students?month=2026-09").json()
        assert "Sami" in [s["name"] for s in listed]

    def test_what_the_family_owes_survives_the_closing(self, client):
        """La dette suit l'élève. Une année qui se ferme ne solde
        personne : ce serait effacer de l'argent dû d'un coup de
        calendrier."""
        level, class_id, _teacher, package = setup_base(client)
        enroll(client, level, package, class_id)
        year = make_year(client).json()["id"]

        client.post(f"/api/school-years/{year}/close", json={})

        owing = client.get("/api/reports/arrears?up_to_month=2026-09").json()
        assert [(e["student_name"], e["total_owed"]) for e in owing] == [
            ("Sami", 300 * DH)
        ]

    def test_a_closed_season_says_so(self, client):
        year = make_year(client).json()["id"]
        client.post(f"/api/school-years/{year}/close", json={})
        listed = client.get("/api/school-years").json()
        assert next(y for y in listed if y["id"] == year)["closed_at"] is not None

    def test_closing_twice_changes_nothing(self, client):
        year = make_year(client).json()["id"]
        client.post(f"/api/school-years/{year}/close", json={})
        first = client.get("/api/school-years").json()
        client.post(f"/api/school-years/{year}/close", json={})
        assert client.get("/api/school-years").json() == first


class TestTheSeasonReport:
    def test_it_adds_up_the_whole_season_not_one_month(self, client):
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        year = make_year(client).json()["id"]

        report = client.get(f"/api/reports/school-year/{year}").json()

        assert report["cash_in"] == 300 * DH
        assert report["months"] == 10

    def test_each_share_is_named_for_the_season(self, client):
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        year = make_year(client).json()["id"]

        report = client.get(f"/api/reports/school-year/{year}").json()

        assert sum(t["total"] for t in report["totals"]) == 300 * DH

    def test_a_teacher_is_counted_over_the_whole_season(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        year = make_year(client).json()["id"]

        report = client.get(f"/api/reports/school-year/{year}").json()

        mine = next(t for t in report["teachers"] if t["teacher_id"] == teacher)
        assert mine["earned"] > 0

    def test_a_season_with_nothing_in_it_reports_zero(self, client):
        year = make_year(client, start="2030-09", end="2031-06").json()["id"]
        report = client.get(f"/api/reports/school-year/{year}").json()
        assert report["cash_in"] == 0
        assert report["teachers"] == []


class TestChangingASeasonHeAlreadyHas:
    """Une année posée par l'application n'est pas gravée : c'est la
    sienne. Son nom, son début et sa fin se corrigent — et si elle ne
    lui sert à rien, elle s'efface."""

    def test_he_can_rename_it(self, client):
        year = make_year(client).json()["id"]
        client.patch(f"/api/school-years/{year}", json={"name": "Rentrée 2026"})
        listed = client.get("/api/school-years").json()
        assert next(y for y in listed if y["id"] == year)["name"] == "Rentrée 2026"

    def test_he_can_move_the_first_month(self, client):
        year = make_year(client).json()["id"]
        client.patch(f"/api/school-years/{year}", json={"start_month": "2026-10"})
        listed = client.get("/api/school-years").json()
        assert next(y for y in listed if y["id"] == year)["start_month"] == "2026-10"

    def test_a_start_pushed_past_the_end_is_refused(self, client):
        """Sinon la saison ne contiendrait aucun mois, et son bilan
        serait vide sans qu'il comprenne pourquoi."""
        year = make_year(client, start="2026-09", end="2027-06").json()["id"]
        refused = client.patch(
            f"/api/school-years/{year}", json={"start_month": "2027-09"}
        )
        assert refused.status_code == 422

    def test_he_can_delete_one(self, client):
        before = client.get("/api/school-years").json()
        year = make_year(client).json()["id"]

        client.delete(f"/api/school-years/{year}")

        after = client.get("/api/school-years").json()
        assert year not in [y["id"] for y in after]
        assert len(after) == len(before)

    def test_deleting_a_season_touches_no_money_and_no_student(self, client):
        """Une année n'est qu'une période : l'effacer ne défait aucun
        paiement et ne réveille personne."""
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        year = make_year(client).json()["id"]
        before = client.get("/api/reports/monthly?month=2026-09").json()

        client.delete(f"/api/school-years/{year}")

        assert client.get("/api/reports/monthly?month=2026-09").json() == before
        assert len(client.get("/api/students?month=2026-09").json()) == 1


class TestAFreshInstall:
    def test_it_opens_with_a_season_already_there(self, client):
        """Sans saison, le bilan d'année n'existe simplement pas à
        l'écran — et le nouveau propriétaire ne saurait pas qu'il faut
        d'abord en créer une pour le voir apparaître."""
        listed = client.get("/api/school-years").json()
        assert len(listed) == 1

    def test_that_season_holds_today(self, client):
        """Elle doit contenir le mois courant, sinon elle ne sert à rien
        le jour de l'installation."""
        (season,) = client.get("/api/school-years").json()
        assert season["start_month"] <= "2026-09" <= season["end_month"]

    def test_its_name_says_the_two_years(self, client):
        (season,) = client.get("/api/school-years").json()
        first = season["start_month"][:4]
        last = season["end_month"][:4]
        expected = first if first == last else f"{first} - {last}"
        assert season["name"] == expected
