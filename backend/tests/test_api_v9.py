"""Round 9: matière delete, class delete/archive, sans professeur,
remboursements, avance — TDD first.

Money rules under test:
  - impayé ⇒ no refund (you cannot return money never received);
  - the refund percentage applies to what the student ACTUALLY paid;
  - a teacherless class's days route the teacher share to the académie;
  - an avance pays every beneficiary in full, the owner fronts the shortfall.
"""

import pytest
from fastapi.testclient import TestClient
from test_api_v4 import enroll, setup_base
from test_api_v8 import monkeypatch_month

from app.adapters.api.app import create_app
from app.services import clock

DH = 100


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def level_id(client, name="Primaire"):
    return next(
        lv["id"] for lv in client.get("/api/levels").json() if lv["name"] == name
    )


def pay(client, enrollment_id, **extra):
    response = client.post(
        "/api/payments", json={"enrollment_id": enrollment_id, **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


def overview_row(client, month, student_id):
    rows = client.get(f"/api/months/{month}/overview").json()
    return next(r for r in rows if r["student_id"] == student_id)


def beneficiary_totals(client, month):
    report = client.get(f"/api/reports/monthly?month={month}").json()
    return {(t["kind"], t["ref_id"]): t["total"] for t in report["totals"]}


# --- 1. matière delete-with-guardrails ------------------------------------


class TestMatiereDelete:
    def test_unused_matiere_deletes_outright_with_its_capabilities(self, client):
        level = level_id(client)
        subject = client.post(
            "/api/subjects", json={"name": "Dessin", "level_id": level}
        ).json()["id"]
        teacher = client.post("/api/teachers", json={"name": "Nadia"}).json()["id"]
        client.put(
            f"/api/teachers/{teacher}/capabilities",
            json={"items": [{"level_id": level, "subject_id": subject}]},
        )
        response = client.delete(f"/api/subjects/{subject}")
        assert response.status_code == 200, response.text
        names = [s["name"] for s in client.get("/api/subjects").json()]
        assert "Dessin" not in names
        assert client.get("/api/capabilities").json() == []  # no ghost ✓ chips

    def test_matiere_with_classes_is_refused_in_french(self, client):
        setup_base(client)
        subject = client.get("/api/classes").json()[0]["subject_id"]
        response = client.delete(f"/api/subjects/{subject}")
        assert response.status_code == 409
        assert "classe" in response.json()["detail"]

    def test_archived_never_enrolled_classes_do_not_block_deletion(self, client):
        # The UI shows « aucune classe » (only active ones count there); a
        # leftover ARCHIVED class nobody was ever enrolled in must not turn
        # that into a mysterious refusal — it disappears with the matière.
        _, class_id, _, _ = setup_base(client)
        subject = client.get("/api/classes").json()[0]["subject_id"]
        client.post(
            f"/api/classes/{class_id}/archive",
            json={"date": "2026-09-15", "refunds": []},
        )
        response = client.delete(f"/api/subjects/{subject}")
        assert response.status_code == 200, response.text
        assert client.get("/api/classes?include_inactive=true").json() == []

    def test_archived_classes_with_history_still_block_deletion(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        pay(client, enrollment)
        subject = client.get("/api/classes").json()[0]["subject_id"]
        client.post(
            f"/api/classes/{class_id}/archive",
            json={"date": "2026-09-15", "refunds": []},
        )
        response = client.delete(f"/api/subjects/{subject}")
        assert response.status_code == 409
        assert "historique" in response.json()["detail"]

    def test_subject_listing_exposes_archived_class_count(self, client):
        _, class_id, _, _ = setup_base(client)
        client.post(
            f"/api/classes/{class_id}/archive",
            json={"date": "2026-09-15", "refunds": []},
        )
        row = client.get("/api/subjects").json()[0]
        assert row["class_count"] == 0
        assert row["archived_class_count"] == 1

    def test_matieres_can_no_longer_be_archived(self, client):
        level = level_id(client)
        subject = client.post(
            "/api/subjects", json={"name": "Dessin", "level_id": level}
        ).json()["id"]
        client.patch(f"/api/subjects/{subject}", json={"is_active": False})
        names = [s["name"] for s in client.get("/api/subjects").json()]
        assert "Dessin" in names  # the flag is dead: still visible


# --- 2. class delete-if-never-enrolled ------------------------------------


class TestClassDelete:
    def test_a_mistake_class_deletes_outright(self, client):
        _, class_id, _, _ = setup_base(client)
        response = client.delete(f"/api/classes/{class_id}")
        assert response.status_code == 200, response.text
        assert client.get("/api/classes?include_inactive=true").json() == []

    def test_a_class_with_any_enrollment_must_be_archived_instead(self, client):
        level, class_id, _, package = setup_base(client)
        enroll(client, level, package, class_id)
        response = client.delete(f"/api/classes/{class_id}")
        assert response.status_code == 409
        assert "archivez" in response.json()["detail"]


# --- 3. sans professeur ----------------------------------------------------


class TestSansProfesseur:
    def test_vacated_class_shows_no_teacher(self, client):
        _, class_id, _, _ = setup_base(client)
        response = client.post(
            f"/api/classes/{class_id}/vacate-teacher", json={"date": "2026-09-11"}
        )
        assert response.status_code == 200, response.text
        (row,) = client.get("/api/classes").json()
        assert row["teacher_id"] is None
        assert row["teacher_name"] is None

    def test_teacherless_days_route_the_teacher_share_to_the_academie(self, client):
        # 300 DH, venue 30% owner 10% → teacher slice 180 DH over 30 days.
        # Ahmed taught days 1-10 (60 DH), the 20 vacant days (120 DH) escrow
        # to the académie: owner ends at 30 + 120 = 150 DH.
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post(
            f"/api/classes/{class_id}/vacate-teacher", json={"date": "2026-09-11"}
        )
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        finals = {
            (line["kind"], line["ref_id"]): line["final_centimes"]
            for line in preview["lines"]
        }
        academy = client.get("/api/academies").json()[0]["id"]
        assert finals[("teacher", teacher)] == 60 * DH
        assert finals[("owner", academy)] == 150 * DH

    def test_replace_fills_a_vacant_class(self, client):
        _, class_id, _, _ = setup_base(client)
        client.post(
            f"/api/classes/{class_id}/vacate-teacher", json={"date": "2026-09-11"}
        )
        sara = client.post("/api/teachers", json={"name": "Sara"}).json()["id"]
        client.post(
            f"/api/classes/{class_id}/replace-teacher",
            json={"date": "2026-09-21", "successor_ids": [sara]},
        )
        (row,) = client.get("/api/classes").json()
        assert row["teacher_id"] == sara

    def test_archiving_a_teacher_who_still_teaches_is_refused(self, client):
        _, _, teacher, _ = setup_base(client)
        response = client.patch(f"/api/teachers/{teacher}", json={"is_active": False})
        assert response.status_code == 409
        assert "enseigne encore" in response.json()["detail"]

    def test_archiving_succeeds_once_his_classes_are_handled(self, client):
        _, class_id, teacher, _ = setup_base(client)
        client.post(
            f"/api/classes/{class_id}/vacate-teacher", json={"date": "2026-09-11"}
        )
        response = client.patch(f"/api/teachers/{teacher}", json={"is_active": False})
        assert response.status_code == 200, response.text


# --- 4. class archive + remboursements -------------------------------------


def two_class_setup(client):
    """Math (Ahmed) + PC (Karim), one 2-subject package at 700 DH."""
    level = level_id(client)
    math = client.post(
        "/api/subjects", json={"name": "Math", "level_id": level}
    ).json()["id"]
    pc = client.post("/api/subjects", json={"name": "PC", "level_id": level}).json()[
        "id"
    ]
    ahmed = client.post("/api/teachers", json={"name": "Ahmed"}).json()["id"]
    karim = client.post("/api/teachers", json={"name": "Karim"}).json()["id"]
    class_math = client.post(
        "/api/classes",
        json={"level_id": level, "subject_id": math, "teacher_id": ahmed},
    ).json()["id"]
    class_pc = client.post(
        "/api/classes",
        json={"level_id": level, "subject_id": pc, "teacher_id": karim},
    ).json()["id"]
    package = client.post(
        "/api/packages",
        json={
            "subject_count": 2,
            "monthly_price_centimes": 700 * DH,
            "level_id": level,
        },
    ).json()["id"]
    return level, class_math, class_pc, ahmed, karim, package


def enroll_student(client, level, package, class_ids, name):
    student = client.post(
        "/api/students", json={"name": name, "level_id": level}
    ).json()["id"]
    enrollment = client.post(
        "/api/enrollments",
        json={
            "student_id": student,
            "month": "2026-09",
            "package_id": package,
            "class_ids": class_ids,
        },
    ).json()["id"]
    return student, enrollment


class TestClassArchiveAndRefunds:
    def test_archive_creates_pending_refunds_for_paid_students_only(self, client):
        level, class_math, class_pc, *_, package = two_class_setup(client)
        _, paid_enrollment = enroll_student(
            client, level, package, [class_math, class_pc], "Salma"
        )
        pay(client, paid_enrollment)
        unpaid_student, _ = enroll_student(
            client, level, package, [class_math, class_pc], "Omar"
        )
        response = client.post(
            f"/api/classes/{class_math}/archive",
            json={
                "date": "2026-09-15",
                "refunds": [{"enrollment_id": paid_enrollment, "percent_bp": 7000}],
            },
        )
        assert response.status_code == 200, response.text
        # 70% of the Math slice of what Salma ACTUALLY paid: 700/2 × 70% = 245.
        (refund,) = client.get("/api/refunds").json()
        assert refund["student_name"] == "Salma"
        assert refund["amount_centimes"] == 245 * DH
        assert refund["status"] == "pending"
        # Omar never paid → no refund row, his dead class simply drops off.
        assert refund["enrollment_id"] == paid_enrollment
        omar = overview_row(client, "2026-09", unpaid_student)
        class_names = [c["subject_name"] for c in omar["enrollment"]["classes"]]
        assert class_names == ["PC"]

    def test_a_refund_for_an_unpaid_enrollment_is_refused(self, client):
        level, class_math, class_pc, *_, package = two_class_setup(client)
        _, enrollment = enroll_student(
            client, level, package, [class_math, class_pc], "Omar"
        )
        response = client.post(
            f"/api/classes/{class_math}/archive",
            json={
                "date": "2026-09-15",
                "refunds": [{"enrollment_id": enrollment, "percent_bp": 10000}],
            },
        )
        assert response.status_code == 422
        assert "impayé" in response.json()["detail"]

    def test_unpaid_single_class_student_is_fully_unenrolled(self, client):
        level, class_id, _, package = setup_base(client)
        student, _ = enroll(client, level, package, class_id)
        response = client.post(
            f"/api/classes/{class_id}/archive",
            json={"date": "2026-09-15", "refunds": []},
        )
        assert response.status_code == 200, response.text
        row = overview_row(client, "2026-09", student)
        assert row["enrollment"] is None  # no longer inscrit

    def test_settling_a_refund_moves_the_money(self, client):
        # Single class, 300 DH paid, 100% refund. Clawback mirrors the split:
        # venue -90, owner -30, teacher -180; cash_in drops by 300.
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        pay(client, enrollment)
        client.post(
            f"/api/classes/{class_id}/archive",
            json={
                "date": "2026-10-01",
                "refunds": [{"enrollment_id": enrollment, "percent_bp": 10000}],
            },
        )
        (refund,) = client.get("/api/refunds").json()
        assert refund["amount_centimes"] == 300 * DH
        settle = client.post(f"/api/refunds/{refund['id']}/settle")
        assert settle.status_code == 200, settle.text
        (settled,) = client.get("/api/refunds").json()
        assert settled["status"] == "settled"
        report = client.get("/api/reports/monthly?month=2026-09").json()
        assert report["cash_in"] == 0
        totals = beneficiary_totals(client, "2026-09")
        academy = client.get("/api/academies").json()[0]["id"]
        assert totals[("teacher", teacher)] == 0
        assert totals[("owner", academy)] == 0
        settle_again = client.post(f"/api/refunds/{refund['id']}/settle")
        assert settle_again.status_code == 409

    def test_extension_skips_archived_classes(self, client):
        level, class_math, class_pc, *_, package = two_class_setup(client)
        _, enrollment = enroll_student(
            client, level, package, [class_math, class_pc], "Salma"
        )
        pay(client, enrollment)
        solo_level, solo_class, _, solo_package = setup_base(client)
        _, solo_enrollment = enroll(client, solo_level, solo_package, solo_class)
        pay(client, solo_enrollment)
        client.post(
            f"/api/classes/{class_math}/archive",
            json={"date": "2026-09-30", "refunds": []},
        )
        client.post(
            f"/api/classes/{solo_class}/archive",
            json={"date": "2026-09-30", "refunds": []},
        )
        monkeypatch_month(client, "2026-10")
        rows = client.get("/api/months/2026-10/overview").json()
        by_name = {r["student_name"]: r for r in rows}
        # Salma keeps PC only; Sami's only class died → not extended at all.
        salma_classes = [
            c["subject_name"] for c in by_name["Salma"]["enrollment"]["classes"]
        ]
        assert salma_classes == ["PC"]
        assert by_name["Sami"]["enrollment"] is None


# --- 5. variantes de prix (Primaire) ---------------------------------------


class TestPriceVariants:
    def test_a_forfait_can_carry_an_optional_label(self, client):
        level = level_id(client)
        created = client.post(
            "/api/packages",
            json={
                "subject_count": 1,
                "monthly_price_centimes": 250 * DH,
                "level_id": level,
                "label": "1ère–4ème année",
            },
        )
        assert created.status_code == 201, created.text
        row = client.get("/api/packages").json()[0]
        assert row["label"] == "1ère–4ème année"
        client.patch(f"/api/packages/{row['id']}", json={"label": "Cas particulier"})
        assert client.get("/api/packages").json()[0]["label"] == "Cas particulier"

    def test_enrollment_takes_a_custom_price_when_no_variant_fits(self, client):
        # Full control: the owner can always type the price himself — the
        # enrollment snapshots it, and the whole money engine follows it.
        level, class_id, teacher, package = setup_base(client)
        student = client.post(
            "/api/students", json={"name": "Amine", "level_id": level}
        ).json()["id"]
        enrollment = client.post(
            "/api/enrollments",
            json={
                "student_id": student,
                "month": "2026-09",
                "package_id": package,
                "class_ids": [class_id],
                "price_centimes": 275 * DH,
            },
        ).json()["id"]
        posted = pay(client, enrollment)
        assert posted["net_centimes"] == 275 * DH
        totals = beneficiary_totals(client, "2026-09")
        assert totals[("teacher", teacher)] == int(275 * DH * 0.6)


# --- 6. avance ---------------------------------------------------------------


class TestAvance:
    def test_partial_payment_fronts_full_shares_from_the_owner(self, client):
        level, class_id, teacher, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id)
        posted = pay(client, enrollment, amount_centimes=100 * DH)
        assert posted["net_centimes"] == 300 * DH
        row = overview_row(client, "2026-09", student)
        assert row["enrollment"]["paid"] is True
        assert row["enrollment"]["remaining_centimes"] == 200 * DH
        report = client.get("/api/reports/monthly?month=2026-09").json()
        assert report["cash_in"] == 100 * DH  # only real cash counts
        totals = beneficiary_totals(client, "2026-09")
        academy = client.get("/api/academies").json()[0]["id"]
        assert totals[("teacher", teacher)] == 180 * DH  # paid in FULL
        assert totals[("owner", academy)] == 30 * DH - 200 * DH  # fronting

    def test_students_listing_says_avance_not_paye(self, client):
        # The Étudiants page must never claim « Payé » while money is still
        # owed: the listing carries the remaining amount.
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id)
        pay(client, enrollment, amount_centimes=100 * DH)
        row = next(
            r
            for r in client.get("/api/students?month=2026-09").json()
            if r["id"] == student
        )
        assert row["month_paid"] == 1
        assert row["month_remaining_centimes"] == 200 * DH

    def test_completing_the_avance_repays_the_owner(self, client):
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id)
        posted = pay(client, enrollment, amount_centimes=100 * DH)
        response = client.post(
            f"/api/payments/{posted['payment_id']}/complete", json={}
        )
        assert response.status_code == 200, response.text
        row = overview_row(client, "2026-09", student)
        assert row["enrollment"]["remaining_centimes"] == 0
        report = client.get("/api/reports/monthly?month=2026-09").json()
        assert report["cash_in"] == 300 * DH
        totals = beneficiary_totals(client, "2026-09")
        academy = client.get("/api/academies").json()[0]["id"]
        assert totals[("owner", academy)] == 30 * DH

    def test_completing_in_two_installments(self, client):
        level, class_id, _, package = setup_base(client)
        student, enrollment = enroll(client, level, package, class_id)
        posted = pay(client, enrollment, amount_centimes=100 * DH)
        client.post(
            f"/api/payments/{posted['payment_id']}/complete",
            json={"amount_centimes": 50 * DH},
        )
        row = overview_row(client, "2026-09", student)
        assert row["enrollment"]["remaining_centimes"] == 150 * DH
        over = client.post(
            f"/api/payments/{posted['payment_id']}/complete",
            json={"amount_centimes": 999 * DH},
        )
        assert over.status_code == 422

    def test_overpay_or_zero_at_posting_is_refused(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        assert (
            client.post(
                "/api/payments",
                json={"enrollment_id": enrollment, "amount_centimes": 400 * DH},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/payments",
                json={"enrollment_id": enrollment, "amount_centimes": 0},
            ).status_code
            == 422
        )

    def test_reversing_an_avance_wipes_everything_including_the_front(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        posted = pay(client, enrollment, amount_centimes=100 * DH)
        client.post(
            f"/api/payments/{posted['payment_id']}/complete",
            json={"amount_centimes": 50 * DH},
        )
        response = client.post(f"/api/payments/{posted['payment_id']}/reverse", json={})
        assert response.status_code == 200, response.text
        report = client.get("/api/reports/monthly?month=2026-09").json()
        assert report["cash_in"] == 0
        totals = beneficiary_totals(client, "2026-09")
        assert all(total == 0 for total in totals.values())
