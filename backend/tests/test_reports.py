"""Read-side tests: monthly money report and arrears — written first (TDD)."""

import pytest

from app.adapters.sqlite.db import connect, init_db
from app.adapters.sqlite.payment_store import SqlitePaymentStore
from app.adapters.sqlite.reports import arrears, monthly_report
from app.services.payments import post_payment
from tests.support import DH, Scenario


@pytest.fixture
def scenario():
    conn = connect(":memory:")
    init_db(conn)
    yield Scenario(conn)
    conn.close()


def pay(scenario, enrollment_id):
    post_payment(SqlitePaymentStore(scenario.conn), enrollment_id)


def totals_by_name(report):
    return {t.name: t.total for t in report.totals}


class TestMonthlyReport:
    def test_totals_aggregate_across_students(self, scenario):
        math = scenario.add_class("Math", "Ahmed", "Primaire")
        physics = scenario.add_class("Physique", "Sara", "Primaire")
        sami = scenario.add_student("Sami", "Primaire")
        lina = scenario.add_student("Lina", "Primaire")
        pay(scenario, scenario.enroll(sami, "2026-09", [math, physics], 300))
        pay(scenario, scenario.enroll(lina, "2026-09", [math], 150))

        report = monthly_report(scenario.conn, scenario.academy_id, "2026-09")

        # Sami 300: venue 90 / owner 30 / Ahmed 90 / Sara 90.
        # Lina 150: venue 45 / owner 15 / Ahmed 90.
        assert report.cash_in == 450 * DH
        assert totals_by_name(report) == {
            "Salle principale": 135 * DH,
            "Mon académie": 45 * DH,
            "Ahmed": 180 * DH,
            "Sara": 90 * DH,
        }

    def test_cash_in_equals_sum_of_beneficiary_nets(self, scenario):
        math = scenario.add_class("Math", "Ahmed", "Primaire")
        sami = scenario.add_student("Sami", "Primaire")
        enrollment = scenario.enroll(sami, "2026-09", [math], 300)
        scenario.add_discount(enrollment, 50)
        pay(scenario, enrollment)

        report = monthly_report(scenario.conn, scenario.academy_id, "2026-09")

        assert report.cash_in == 250 * DH
        assert sum(t.total for t in report.totals) == report.cash_in

    def test_adjustment_lowers_the_bearer_total(self, scenario):
        math = scenario.add_class("Math", "Ahmed", "Primaire")
        sami = scenario.add_student("Sami", "Primaire")
        enrollment = scenario.enroll(sami, "2026-09", [math], 300)
        scenario.add_discount(enrollment, 50)  # bearerless -> owner absorbs
        pay(scenario, enrollment)

        report = monthly_report(scenario.conn, scenario.academy_id, "2026-09")

        assert totals_by_name(report)["Mon académie"] == (30 - 50) * DH

    def test_levels_are_separated(self, scenario):
        math_p = scenario.add_class("Math", "Ahmed", "Primaire")
        math_c = scenario.add_class("Math C", "Sara", "Collège")
        sami = scenario.add_student("Sami", "Primaire")
        omar = scenario.add_student("Omar", "Collège")
        pay(scenario, scenario.enroll(sami, "2026-09", [math_p], 300))
        pay(scenario, scenario.enroll(omar, "2026-09", [math_c], 200))

        report = monthly_report(scenario.conn, scenario.academy_id, "2026-09")

        by_level = {level.level_name: level for level in report.by_level}
        assert set(by_level) == {"Primaire", "Collège"}
        primaire = {t.name: t.total for t in by_level["Primaire"].totals}
        assert primaire["Ahmed"] == 180 * DH
        assert "Sara" not in primaire

    def test_reversed_payment_zeroes_the_monthly_report(self, scenario):
        from app.services.payments import reverse_payment

        math = scenario.add_class("Math", "Ahmed", "Primaire")
        sami = scenario.add_student("Sami", "Primaire")
        enrollment = scenario.enroll(sami, "2026-09", [math], 300)
        store = SqlitePaymentStore(scenario.conn)
        payment_id = post_payment(store, enrollment).payment_id
        reverse_payment(store, payment_id, reason="bounced")

        report = monthly_report(scenario.conn, scenario.academy_id, "2026-09")

        assert report.cash_in == 0
        assert sum(t.total for t in report.totals) == report.cash_in

    def test_empty_month_reports_zero(self, scenario):
        report = monthly_report(scenario.conn, scenario.academy_id, "2026-01")
        assert report.cash_in == 0
        assert report.totals == ()
        assert report.by_level == ()


class TestArrears:
    def test_unpaid_months_are_listed_net_of_adjustments(self, scenario):
        math = scenario.add_class("Math", "Ahmed", "Primaire")
        sami = scenario.add_student("Sami", "Primaire")
        august = scenario.enroll(sami, "2026-08", [math], 300)
        scenario.add_discount(august, 50)
        pay(scenario, scenario.enroll(sami, "2026-09", [math], 300))  # September paid

        owing = arrears(scenario.conn, scenario.academy_id, "2026-09")

        assert len(owing) == 1
        (entry,) = owing
        assert entry.student_name == "Sami"
        assert [(item.month, item.owed) for item in entry.items] == [
            ("2026-08", 250 * DH)
        ]
        assert entry.total_owed == 250 * DH

    def test_future_months_are_not_arrears(self, scenario):
        math = scenario.add_class("Math", "Ahmed", "Primaire")
        sami = scenario.add_student("Sami", "Primaire")
        scenario.enroll(sami, "2026-10", [math], 300)

        assert arrears(scenario.conn, scenario.academy_id, "2026-09") == ()

    def test_students_are_grouped_and_sorted(self, scenario):
        math = scenario.add_class("Math", "Ahmed", "Primaire")
        zoe = scenario.add_student("Zoe", "Primaire")
        adam = scenario.add_student("Adam", "Primaire")
        scenario.enroll(zoe, "2026-08", [math], 300)
        scenario.enroll(adam, "2026-08", [math], 150)
        scenario.enroll(adam, "2026-09", [math], 150)

        owing = arrears(scenario.conn, scenario.academy_id, "2026-09")

        assert [entry.student_name for entry in owing] == ["Adam", "Zoe"]
        adam_entry = owing[0]
        assert [item.month for item in adam_entry.items] == ["2026-08", "2026-09"]
        assert adam_entry.total_owed == 300 * DH

    def test_reversed_payment_counts_as_unpaid(self, scenario):
        from app.services.payments import reverse_payment

        math = scenario.add_class("Math", "Ahmed", "Primaire")
        sami = scenario.add_student("Sami", "Primaire")
        enrollment = scenario.enroll(sami, "2026-08", [math], 300)
        store = SqlitePaymentStore(scenario.conn)
        payment_id = post_payment(store, enrollment).payment_id
        assert arrears(scenario.conn, scenario.academy_id, "2026-09") == ()

        reverse_payment(store, payment_id, reason="bounced")

        owing = arrears(scenario.conn, scenario.academy_id, "2026-09")
        assert [(e.student_name, e.total_owed) for e in owing] == [("Sami", 300 * DH)]

    def test_gifted_month_owes_nothing(self, scenario):
        math = scenario.add_class("Math", "Ahmed", "Primaire")
        sami = scenario.add_student("Sami", "Primaire")
        enrollment = scenario.enroll(sami, "2026-08", [math], 300)
        scenario.add_discount(enrollment, 300)  # full gift

        owing = arrears(scenario.conn, scenario.academy_id, "2026-09")

        (entry,) = owing
        assert entry.total_owed == 0
