"""Sponsors, proration and table aggregates — written first (TDD)."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.app import create_app
from app.services import clock

DH = 100


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


def setup_base(client):
    levels = client.get("/api/levels").json()
    level = next(lv["id"] for lv in levels if lv["name"] == "Primaire")
    subject = client.post("/api/subjects", json={"name": "Math"}).json()["id"]
    teacher = client.post("/api/teachers", json={"name": "Ahmed"}).json()["id"]
    class_id = client.post(
        "/api/classes",
        json={"level_id": level, "subject_id": subject, "teacher_id": teacher},
    ).json()["id"]
    package = client.post(
        "/api/packages",
        json={
            "subject_count": 1,
            "monthly_price_centimes": 300 * DH,
            "level_id": level,
        },
    ).json()["id"]
    return level, class_id, teacher, package


def enroll(client, level, package, class_id, name="Sami", month="2026-09", **extra):
    student = client.post(
        "/api/students", json={"name": name, "level_id": level}
    ).json()["id"]
    response = client.post(
        "/api/enrollments",
        json={
            "student_id": student,
            "month": month,
            "package_id": package,
            "class_ids": [class_id],
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return student, response.json()["id"]


class TestSponsorShares:
    def test_sponsors_cover_explicit_parts_of_the_total(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        response = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={
                "kind": "amount",
                "value": 100 * DH,
                "bearers": [
                    {"kind": "owner", "ref_id": 1, "share_centimes": 30 * DH},
                    {"kind": "teacher", "ref_id": teacher, "share_centimes": 70 * DH},
                ],
            },
        )
        assert response.status_code == 201, response.text
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        lines = {line["name"]: line for line in preview["lines"]}
        assert lines["Mon académie"]["final_centimes"] == 0  # 30 - 30
        assert lines["Ahmed"]["final_centimes"] == 110 * DH  # 180 - 70
        assert preview["net_centimes"] == 200 * DH

    def test_sponsor_shares_may_be_percentages_of_the_total(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        response = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={
                "kind": "amount",
                "value": 100 * DH,
                "bearers": [
                    {"kind": "owner", "ref_id": 1, "share_bp": 2500},
                    {"kind": "teacher", "ref_id": teacher, "share_bp": 7500},
                ],
            },
        )
        assert response.status_code == 201, response.text
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        (adjustment,) = preview["adjustments"]
        shares = {b["name"]: b["share_centimes"] for b in adjustment["bearers"]}
        assert shares == {"Mon académie": 25 * DH, "Ahmed": 75 * DH}

    def test_mismatched_sponsor_parts_are_refused(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        response = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={
                "kind": "amount",
                "value": 100 * DH,
                "bearers": [
                    {"kind": "owner", "ref_id": 1, "share_centimes": 30 * DH},
                    {"kind": "teacher", "ref_id": teacher, "share_centimes": 30 * DH},
                ],
            },
        )
        assert response.status_code == 422
        assert "somme" in response.json()["detail"].lower()


class TestReviewFixes:
    def test_percent_thirds_land_exactly_on_the_reduction(self, client):
        # Flooring loss is given back to the largest % shares — thirds work.
        # 89,99 DH keeps every third under its bearer's cap (owner gets 30 DH).
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        response = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={
                "kind": "amount",
                "value": 8999,  # 89,99 DH
                "bearers": [
                    {"kind": "owner", "ref_id": 1, "share_bp": 3333},
                    {"kind": "venue", "ref_id": 1, "share_bp": 3333},
                    {"kind": "teacher", "ref_id": teacher, "share_bp": 3334},
                ],
            },
        )
        assert response.status_code == 201, response.text
        (adjustment,) = client.get(f"/api/enrollments/{enrollment}/preview").json()[
            "adjustments"
        ]
        assert sum(b["share_centimes"] for b in adjustment["bearers"]) == 8999

    def test_duplicate_sponsors_are_refused_in_french(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        response = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={
                "kind": "amount",
                "value": 100 * DH,
                "bearers": [
                    {"kind": "owner", "ref_id": 1, "share_centimes": 50 * DH},
                    {"kind": "owner", "ref_id": 1, "share_centimes": 50 * DH},
                ],
            },
        )
        assert response.status_code == 422
        assert "sponsor" in response.json()["detail"].lower()

    def test_negative_shares_are_refused(self, client):
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        response = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={
                "kind": "amount",
                "value": 100 * DH,
                "bearers": [
                    {"kind": "owner", "ref_id": 1, "share_centimes": -50 * DH},
                    {"kind": "teacher", "ref_id": teacher, "share_centimes": 150 * DH},
                ],
            },
        )
        assert response.status_code == 422

    def test_impossible_arrival_dates_are_refused(self, client):
        level, class_id, _, package = setup_base(client)
        student = client.post(
            "/api/students", json={"name": "Lina", "level_id": level}
        ).json()["id"]
        response = client.post(
            "/api/enrollments",
            json={
                "student_id": student,
                "month": "2026-09",
                "package_id": package,
                "class_ids": [class_id],
                "arrival_date": "2026-09-31",  # September has 30 days
            },
        )
        assert response.status_code == 422

    def test_extension_reprices_prorated_months_from_the_package(
        self, client, monkeypatch
    ):
        # The blocker: a prorated arrival must NOT ride into next month.
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(
            client, level, package, class_id, arrival_date="2026-09-25"
        )
        assert (
            client.get(f"/api/enrollments/{enrollment}/preview").json()[
                "price_centimes"
            ]
            == 9900  # 33% of 300 DH
        )
        monkeypatch.setattr(clock, "current_month", lambda: "2026-10")
        client.post("/api/months/2026-10/ensure")
        (row,) = client.get("/api/months/2026-10/overview").json()
        assert row["enrollment"]["price_centimes"] == 300 * DH  # full again


class TestSponsorCaps:
    def test_sponsor_part_beyond_their_share_is_refused(self, client):
        # The owner receives 30 DH of a 300 DH package — they cannot cover 50.
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        response = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={
                "kind": "amount",
                "value": 70 * DH,
                "bearers": [
                    {"kind": "owner", "ref_id": 1, "share_centimes": 50 * DH},
                    {"kind": "teacher", "ref_id": teacher, "share_centimes": 20 * DH},
                ],
            },
        )
        assert response.status_code == 422
        assert "négative" in response.json()["detail"]

    def test_stacked_sponsor_parts_cannot_cross_zero(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)

        def cover(amount):
            return client.post(
                f"/api/enrollments/{enrollment}/adjustments",
                json={
                    "kind": "amount",
                    "value": amount,
                    "bearers": [
                        {"kind": "owner", "ref_id": 1, "share_centimes": amount}
                    ],
                },
            )

        assert cover(20 * DH).status_code == 201  # owner: 30 -> 10
        assert cover(20 * DH).status_code == 422  # 10 - 20 would go below zero

    def test_gift_month_still_lets_the_owner_fund_everyone(self, client):
        # « Mois offert » sends no explicit parts: the owner absorbs the whole
        # price so teachers and the venue still get paid — by design.
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        gift = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={"kind": "percent", "value": 10_000, "category": "gift"},
        )
        assert gift.status_code == 201, gift.text
        paid = client.post("/api/payments", json={"enrollment_id": enrollment})
        assert paid.status_code == 201, paid.text

    def test_legacy_over_cap_share_previews_but_refuses_to_post(self, client):
        # Rows created before the cap existed must still render in the dialog
        # (that is the repair path) yet refuse to move money.
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        legacy = sqlite3.connect(client.app.state.db_path)
        with legacy:
            adjustment_id = legacy.execute(
                "INSERT INTO adjustment (enrollment_id, scope, kind, value,"
                " category) VALUES (?, 'package', 'amount', ?, 'discount')",
                (enrollment, 50 * DH),
            ).lastrowid
            legacy.execute(
                "INSERT INTO adjustment_bearer (adjustment_id, bearer_kind,"
                " bearer_id, share_centimes) VALUES (?, 'owner', 1, ?)",
                (adjustment_id, 50 * DH),
            )
        legacy.close()
        preview = client.get(f"/api/enrollments/{enrollment}/preview")
        assert preview.status_code == 200
        owner = next(
            line for line in preview.json()["lines"] if line["kind"] == "owner"
        )
        assert owner["final_centimes"] == -20 * DH
        paid = client.post("/api/payments", json={"enrollment_id": enrollment})
        assert paid.status_code == 422
        assert "négative" in paid.json()["detail"]


class TestAdjustmentLifecycle:
    def test_reduction_removable_after_a_reversed_payment(self, client):
        # Reverse-then-fix: ledger lines keep referencing the adjustment, so
        # removal must be a soft delete — not the FOREIGN KEY crash it was.
        level, class_id, teacher, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        adjustment = client.post(
            f"/api/enrollments/{enrollment}/adjustments",
            json={
                "kind": "amount",
                "value": 20 * DH,
                "bearers": [
                    {"kind": "teacher", "ref_id": teacher, "share_centimes": 20 * DH}
                ],
            },
        ).json()["id"]
        payment = client.post(
            "/api/payments", json={"enrollment_id": enrollment}
        ).json()["payment_id"]
        reversal = client.post(f"/api/payments/{payment}/reverse", json={})
        assert reversal.status_code == 200, reversal.text
        deleted = client.delete(f"/api/adjustments/{adjustment}")
        assert deleted.status_code == 200, deleted.text
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        assert preview["adjustments"] == []
        assert preview["net_centimes"] == 300 * DH


class TestProration:
    def test_arrival_in_a_later_segment_prices_proportionally(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(
            client, level, package, class_id, arrival_date="2026-09-15"
        )
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        # Default thirds: day 15 of 30 -> 2nd segment -> 67% of 300 = 201 DH.
        assert preview["price_centimes"] == 20100

    def test_first_segment_pays_full_price(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(
            client, level, package, class_id, arrival_date="2026-09-05"
        )
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        assert preview["price_centimes"] == 300 * DH

    def test_proration_segments_are_configurable(self, client):
        (academy,) = client.get("/api/academies").json()
        updated = client.patch(
            f"/api/academies/{academy['id']}",
            json={"proration_bp": [10000, 5000]},  # halves: 100% then 50%
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["proration_bp"] == [10000, 5000]
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(
            client, level, package, class_id, arrival_date="2026-09-20"
        )
        preview = client.get(f"/api/enrollments/{enrollment}/preview").json()
        assert preview["price_centimes"] == 150 * DH


class TestTableAggregates:
    def test_teachers_carry_monthly_earnings_and_subjects(self, client):
        level, class_id, _, package = setup_base(client)
        _, enrollment = enroll(client, level, package, class_id)
        client.post("/api/payments", json={"enrollment_id": enrollment})
        (row,) = client.get("/api/teachers", params={"month": "2026-09"}).json()
        assert row["earned_centimes"] == 180 * DH
        assert row["subjects"] == "Math"

    def test_classes_carry_enrolled_count(self, client):
        level, class_id, _, package = setup_base(client)
        enroll(client, level, package, class_id)
        (row,) = client.get("/api/classes", params={"month": "2026-09"}).json()
        assert row["enrolled_count"] == 1

    def test_subjects_carry_levels_and_class_count(self, client):
        setup_base(client)
        (row,) = client.get("/api/subjects").json()
        assert row["class_count"] == 1
        assert row["levels"] == "Primaire"

    def test_students_carry_unpaid_months_count(self, client, monkeypatch):
        level, class_id, _, package = setup_base(client)
        monkeypatch.setattr(clock, "current_month", lambda: "2026-08")
        student, _ = enroll(client, level, package, class_id, month="2026-08")
        monkeypatch.setattr(clock, "current_month", lambda: "2026-09")
        (row,) = client.get("/api/students", params={"month": "2026-09"}).json()
        assert row["unpaid_months"] == 1
        overview_row = client.get("/api/months/2026-09/overview").json()[0]
        assert overview_row["has_arrears"] is True
        assert overview_row["student_id"] == student
