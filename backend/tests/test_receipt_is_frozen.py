"""Round 33 : a payslip is a RECEIPT, and a receipt never changes.

It was generated from the state of the month, but handed over and signed
at a moment in time, and those two drift apart. Pay Moulay Idris on the
5th, enrol a student on the 12th, and asking for the same receipt again
produced a different paper -- describing money he was never handed.

So the receipt is frozen at the payout: asked for again, the stored file
comes back untouched. What he is owed NOW is a different question, and
the professor page already answers it.

Numbering follows the teacher, not the database. « versement-16 » told
the owner how many payouts the academy had made in total, which is not
a fact about the man holding the paper. His fourth payout reads 04.

Cancelling does not erase. The professor may already hold the signed
sheet, and deleting our copy does not retrieve his: the file is renamed
so the mismatch is visible rather than silent.
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


def with_folder(client, tmp_path):
    client.put("/api/settings/folders/documents", json={"path": str(tmp_path / "aX")})
    return tmp_path / "aX"


def paid_month(client):
    """One teacher, one paying student, so there is something to pay out."""
    level, class_id, teacher, package = setup_base(client)
    _, enrollment = enroll(client, level, package, class_id)
    client.post(
        "/api/payments",
        json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
    )
    return level, class_id, teacher, package


def payout(client, teacher, amount=None):
    """A payout. Without an amount, the whole of what is owed.

    Handing over part of it is the ordinary way a month ends up with two
    receipts: something now, the rest later.
    """
    body = {"kind": "teacher", "ref_id": teacher, "month": "2026-09"}
    if amount is not None:
        body["amount_centimes"] = amount
    made = client.post("/api/payouts", json=body)
    assert made.status_code == 201, made.text
    return made.json()


def file_receipt(client, teacher, payout_id):
    return client.post(
        "/api/documents/file",
        json={
            "kind": "payslip",
            "month": "2026-09",
            "ref_id": teacher,
            "payout_id": payout_id,
        },
    )


def receipts(root):
    place = root / "2026-09 Septembre" / "fiches-de-paie"
    return sorted(item.name for item in place.iterdir()) if place.is_dir() else []


class TestTheReceiptIsFrozen:
    def test_asking_twice_gives_the_same_paper(self, client, tmp_path):
        level, class_id, teacher, package = paid_month(client)
        root = with_folder(client, tmp_path)
        first = payout(client, teacher)
        file_receipt(client, teacher, first["id"])
        filed = receipts(root)
        before = (root / "2026-09 Septembre" / "fiches-de-paie" / filed[0]).read_bytes()

        # The month moves on: another student joins after he was paid.
        enroll(client, level, package, class_id, name="Nouvelle")

        file_receipt(client, teacher, first["id"])
        after = (root / "2026-09 Septembre" / "fiches-de-paie" / filed[0]).read_bytes()

        assert after == before

    def test_a_second_payout_gets_its_own_paper(self, client, tmp_path):
        """Two payouts in one month are two receipts; the second must not
        overwrite the first."""
        _, _, teacher, _ = paid_month(client)
        root = with_folder(client, tmp_path)
        first = payout(client, teacher, 50 * DH)
        file_receipt(client, teacher, first["id"])
        second = payout(client, teacher)
        file_receipt(client, teacher, second["id"])

        assert len(receipts(root)) == 2


class TestNumberingFollowsTheTeacher:
    def test_his_first_payout_reads_01(self, client, tmp_path):
        _, _, teacher, _ = paid_month(client)
        root = with_folder(client, tmp_path)
        made = payout(client, teacher)
        file_receipt(client, teacher, made["id"])

        assert any(name.endswith("-versement-01.docx") for name in receipts(root))

    def test_his_second_payout_reads_02(self, client, tmp_path):
        _, _, teacher, _ = paid_month(client)
        root = with_folder(client, tmp_path)
        file_receipt(client, teacher, payout(client, teacher, 50 * DH)["id"])
        file_receipt(client, teacher, payout(client, teacher)["id"])

        assert any(name.endswith("-versement-02.docx") for name in receipts(root))

    def test_another_teacher_starts_at_01_again(self, client, tmp_path):
        """The number counts HIS payouts. « versement-16 » described the
        academy's bookkeeping, not the man holding the paper."""
        level, _class_id, teacher, package = paid_month(client)
        root = with_folder(client, tmp_path)
        file_receipt(client, teacher, payout(client, teacher)["id"])

        # He has to teach a paid student before anything is owed to him.
        other = client.post(
            "/api/teachers", json={"name": "Sara", "phone": None}
        ).json()["id"]
        subject = client.post(
            "/api/subjects", json={"name": "Physique", "level_id": level}
        ).json()["id"]
        their_class = client.post(
            "/api/classes",
            json={"level_id": level, "subject_id": subject, "teacher_id": other},
        ).json()["id"]
        _, enrollment = enroll(client, level, package, their_class, name="Autre eleve")
        client.post(
            "/api/payments",
            json={"enrollment_id": enrollment, "paid_on": "2026-09-04"},
        )

        made = payout(client, other)
        file_receipt(client, other, made["id"])

        # His first, though it is the second payout the academy has made.
        assert "paie-Sara-versement-01.docx" in receipts(root)


class TestCancellingLeavesATrace:
    def test_the_file_is_renamed_not_deleted(self, client, tmp_path):
        """He may already hold the signed sheet: deleting our copy does not
        retrieve his."""
        _, _, teacher, _ = paid_month(client)
        root = with_folder(client, tmp_path)
        made = payout(client, teacher)
        file_receipt(client, teacher, made["id"])

        client.delete(f"/api/payouts/{made['id']}")

        listed = receipts(root)
        assert len(listed) == 1
        assert "annule" in listed[0].lower()

    def test_cancelling_without_a_folder_still_works(self, client):
        """No folder configured means no file to rename -- the cancellation
        must not fail because of our filing."""
        _, _, teacher, _ = paid_month(client)
        made = payout(client, teacher)
        assert client.delete(f"/api/payouts/{made['id']}").status_code == 200


class TestTheCounterRestartsEachMonth:
    """« versement-04 » should mean his fourth receipt THIS month.

    Counting his payouts since the beginning made the number climb
    forever: by March a teacher paid twice a month is on his fourteenth,
    and the figure says nothing he can check against the month in his
    hand.
    """

    def test_the_first_of_a_new_month_reads_01_again(self, client, tmp_path):
        level, class_id, teacher, package = paid_month(client)
        root = with_folder(client, tmp_path)
        file_receipt(client, teacher, payout(client, teacher)["id"])

        # He has to be owed something in October before he can be paid.
        _, october = enroll(
            client, level, package, class_id, name="Octobre", month="2026-10"
        )
        client.post(
            "/api/payments",
            json={"enrollment_id": october, "paid_on": "2026-10-02"},
        )

        # October: he is paid again, and it is his FIRST of that month.
        made = client.post(
            "/api/payouts",
            json={
                "kind": "teacher",
                "ref_id": teacher,
                "month": "2026-10",
                "amount_centimes": 20 * DH,
            },
        )
        assert made.status_code == 201, made.text
        client.post(
            "/api/documents/file",
            json={
                "kind": "payslip",
                "month": "2026-10",
                "ref_id": teacher,
                "payout_id": made.json()["id"],
            },
        )

        place = root / "2026-10 Octobre" / "fiches-de-paie"
        listed = sorted(item.name for item in place.iterdir())
        assert any(name.endswith("-versement-01.docx") for name in listed)
