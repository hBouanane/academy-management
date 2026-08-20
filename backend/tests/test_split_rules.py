"""Round 24 : des répartitions nommées, et à qui elles s'appliquent.

L'académie avait UNE répartition, la même partout. Or un professeur
chevronné ne se paie pas comme un débutant, et le primaire ne coûte pas
ce que coûte le lycée.

Le propriétaire écrit donc ses règles et dit à qui chacune s'applique.
La plus précise gagne : la classe, puis le professeur, puis la filière,
puis le niveau, puis la répartition de l'académie.

Et ce qui est déjà encaissé ne bouge jamais.
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


def rule(client, name, venue_bp, owner_bp):
    made = client.post(
        "/api/split-rules",
        json={"name": name, "venue_bp": venue_bp, "owner_bp": owner_bp},
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


def applies(client, rule_id, scope, ref):
    key = "ref_text" if scope == "filiere" else "ref_id"
    done = client.post(
        f"/api/split-rules/{rule_id}/applies-to", json={"scope": scope, key: ref}
    )
    assert done.status_code == 200, done.text


def resolved(client, class_id):
    """Quelle répartition cette classe suit, et d'où elle la tient."""
    return client.get(f"/api/classes/{class_id}/split").json()


class TestWritingTheRules:
    def test_a_fresh_install_has_none(self, client):
        assert client.get("/api/split-rules").json() == []

    def test_he_writes_one(self, client):
        rule(client, "Prof senior", 3000, 1000)
        kept = client.get("/api/split-rules").json()
        assert [(r["name"], r["venue_bp"], r["owner_bp"]) for r in kept] == [
            ("Prof senior", 3000, 1000)
        ]

    def test_more_than_everything_is_refused(self, client):
        refused = client.post(
            "/api/split-rules",
            json={"name": "Impossible", "venue_bp": 7000, "owner_bp": 5000},
        )
        assert refused.status_code == 422

    def test_a_rule_can_be_thrown_away(self, client):
        made = rule(client, "Essai", 1000, 1000)
        client.delete(f"/api/split-rules/{made}")
        assert client.get("/api/split-rules").json() == []


class TestWhichOneWins:
    def test_without_a_rule_the_academy_split_applies(self, client):
        _level, class_id, _teacher, _package = setup_base(client)
        found = resolved(client, class_id)
        academy = client.get("/api/academies").json()[0]
        assert found["venue_bp"] == academy["venue_bp"]
        assert found["from"] == "academy"

    def test_the_level_rule_beats_the_academy(self, client):
        level, class_id, _teacher, _package = setup_base(client)
        applies(client, rule(client, "Primaire", 2000, 500), "level", level)
        found = resolved(client, class_id)
        assert (found["venue_bp"], found["owner_bp"]) == (2000, 500)
        assert found["from"] == "level"

    def test_the_teacher_rule_beats_the_level(self, client):
        level, class_id, teacher, _package = setup_base(client)
        applies(client, rule(client, "Niveau", 2000, 500), "level", level)
        applies(client, rule(client, "Senior", 3000, 1000), "teacher", teacher)
        found = resolved(client, class_id)
        assert (found["venue_bp"], found["owner_bp"]) == (3000, 1000)
        assert found["from"] == "teacher"

    def test_the_class_rule_beats_everything(self, client):
        level, class_id, teacher, _package = setup_base(client)
        applies(client, rule(client, "Niveau", 2000, 500), "level", level)
        applies(client, rule(client, "Senior", 3000, 1000), "teacher", teacher)
        applies(client, rule(client, "Ce cas-là", 4000, 2000), "class", class_id)
        found = resolved(client, class_id)
        assert (found["venue_bp"], found["owner_bp"]) == (4000, 2000)
        assert found["from"] == "class"

    def test_a_filiere_rule_sits_between_teacher_and_level(self, client):
        # Le lycée existe déjà : c'est lui qui porte les filières.
        level = next(
            entry["id"]
            for entry in client.get("/api/levels").json()
            if entry["name"] == "Lycée"
        )
        subject = client.post(
            "/api/subjects", json={"name": "Maths", "level_id": level}
        ).json()["id"]
        teacher = client.post("/api/teachers", json={"name": "Idris"}).json()["id"]
        class_id = client.post(
            "/api/classes",
            json={
                "level_id": level,
                "subject_id": subject,
                "teacher_id": teacher,
                "annee": 1,
                "filiere": "Sciences Maths",
            },
        ).json()["id"]
        applies(client, rule(client, "Lycée", 2000, 500), "level", level)
        applies(client, rule(client, "SM", 2500, 700), "filiere", "Sciences Maths")
        found = resolved(client, class_id)
        assert (found["venue_bp"], found["owner_bp"]) == (2500, 700)
        assert found["from"] == "filiere"


class TestItReachesTheMoney:
    def test_a_class_rule_changes_what_the_venue_takes(self, client):
        level, class_id, _teacher, package = setup_base(client)
        applies(client, rule(client, "Salle gourmande", 5000, 0), "class", class_id)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        caisse = client.get("/api/caisse?month=2026-09").json()
        venue = next(e for e in caisse["lines"] if e["kind"] == "venue")
        # Le mois vaut 300 DH : la salle en prend la moitié.
        assert venue["due_centimes"] == 150 * DH

    def test_a_settled_month_never_moves(self, client):
        """La règle change après coup : le mois déjà encaissé garde le
        partage applique le jour du paiement."""
        level, class_id, _teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        before = client.get("/api/caisse?month=2026-09").json()
        venue_before = next(e for e in before["lines"] if e["kind"] == "venue")[
            "due_centimes"
        ]

        applies(client, rule(client, "Tout à la salle", 9000, 0), "class", class_id)
        after = client.get("/api/caisse?month=2026-09").json()
        venue_after = next(e for e in after["lines"] if e["kind"] == "venue")[
            "due_centimes"
        ]
        assert venue_after == venue_before

    def test_two_classes_two_rules_in_one_month(self, client):
        """Un élève qui suit deux matières partagées différemment : chaque
        part suit sa propre règle."""
        level, first, teacher, package = setup_base(client)
        other_subject = client.post(
            "/api/subjects", json={"name": "SVT", "level_id": level}
        ).json()["id"]
        second = client.post(
            "/api/classes",
            json={
                "level_id": level,
                "subject_id": other_subject,
                "teacher_id": teacher,
            },
        ).json()["id"]
        applies(client, rule(client, "Rien à la salle", 0, 0), "class", first)
        applies(client, rule(client, "Tout à la salle", 10000, 0), "class", second)

        student = client.post(
            "/api/students", json={"name": "Sami", "level_id": level}
        ).json()["id"]
        enrollment = client.post(
            "/api/enrollments",
            json={
                "student_id": student,
                "month": "2026-09",
                "package_id": package,
                "class_ids": [first, second],
            },
        ).json()["id"]
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
        )
        caisse = client.get("/api/caisse?month=2026-09").json()
        venue = next(e for e in caisse["lines"] if e["kind"] == "venue")
        # 300 DH partagés en deux matières : la salle prend tout sur
        # l'une, rien sur l'autre.
        assert venue["due_centimes"] == 150 * DH
