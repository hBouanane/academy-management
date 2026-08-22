"""Round 34 : the receipt is filed when he pays, and printed on demand.

Two complaints, both about the same confusion. Clicking « Imprimer »
downloaded the file -- but it had already been filed the moment the
payout was made, so the owner ended up with a second copy in his
Downloads folder and no printer involved.

So: paying files the receipt, once, in his documents folder. Printing
sends THAT file to the printer. Neither step produces a stray copy.
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
    # Nothing must reach a real printer while the suite runs.
    from app.adapters.api import routes

    sent: list[str] = []
    monkeypatch.setattr(routes, "_print_file", lambda path: sent.append(path))
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        test_client.sent = sent
        yield test_client


def with_folder(client, tmp_path):
    client.put("/api/settings/folders/documents", json={"path": str(tmp_path / "aX")})
    return tmp_path / "aX"


def paid_teacher(client):
    level, class_id, teacher, package = setup_base(client)
    _, enrollment = enroll(client, level, package, class_id)
    client.post(
        "/api/payments",
        json={"enrollment_id": enrollment, "paid_on": "2026-09-03"},
    )
    return teacher


def receipts(root):
    place = root / "2026-09 Septembre" / "fiches-de-paie"
    return sorted(item.name for item in place.iterdir()) if place.is_dir() else []


class TestPayingFilesTheReceipt:
    def test_the_receipt_exists_as_soon_as_he_pays(self, client, tmp_path):
        teacher = paid_teacher(client)
        root = with_folder(client, tmp_path)

        client.post(
            "/api/payouts",
            json={"kind": "teacher", "ref_id": teacher, "month": "2026-09"},
        )

        assert len(receipts(root)) == 1

    def test_paying_without_a_folder_still_works(self, client):
        """No folder means nowhere to file -- the money still moves."""
        teacher = paid_teacher(client)
        made = client.post(
            "/api/payouts",
            json={"kind": "teacher", "ref_id": teacher, "month": "2026-09"},
        )
        assert made.status_code == 201

    def test_the_salle_gets_no_receipt(self, client, tmp_path):
        """Only a teacher signs for what he was handed."""
        paid_teacher(client)
        root = with_folder(client, tmp_path)
        venue = next(
            line
            for line in client.get("/api/caisse?month=2026-09").json()["lines"]
            if line["kind"] == "venue"
        )
        client.post(
            "/api/payouts",
            json={"kind": "venue", "ref_id": venue["ref_id"], "month": "2026-09"},
        )
        assert receipts(root) == []


class TestPrintingSendsTheFiledOne:
    def test_it_prints_the_paper_that_was_filed(self, client, tmp_path):
        teacher = paid_teacher(client)
        root = with_folder(client, tmp_path)
        made = client.post(
            "/api/payouts",
            json={"kind": "teacher", "ref_id": teacher, "month": "2026-09"},
        ).json()

        answer = client.post(f"/api/payouts/{made['id']}/print")

        assert answer.status_code == 200
        assert len(client.sent) == 1
        assert client.sent[0].endswith(receipts(root)[0])

    def test_an_old_payout_gets_its_receipt_made_now(self, client, tmp_path):
        """Payouts made before the receipt was filed automatically -- or
        while no folder was chosen -- had no paper at all, so the button
        answered « not found » and looked broken. A receipt that does not
        exist cannot be frozen: producing it now is strictly better, and
        it is frozen from then on."""
        teacher = paid_teacher(client)
        made = client.post(
            "/api/payouts",
            json={"kind": "teacher", "ref_id": teacher, "month": "2026-09"},
        ).json()
        # The folder arrives only afterwards.
        root = with_folder(client, tmp_path)

        answer = client.post(f"/api/payouts/{made['id']}/print")

        assert answer.status_code == 200
        assert len(receipts(root)) == 1
        assert len(client.sent) == 1

    def test_printing_without_a_folder_says_what_to_do(self, client):
        """Rather than silently doing nothing, which reads as a dead
        button."""
        teacher = paid_teacher(client)
        made = client.post(
            "/api/payouts",
            json={"kind": "teacher", "ref_id": teacher, "month": "2026-09"},
        ).json()

        answer = client.post(f"/api/payouts/{made['id']}/print")

        # It names the thing he has to do, rather than reporting a
        # not-found he can make no sense of.
        assert answer.status_code == 409
        assert "dossier" in answer.json()["detail"].lower()
        assert client.sent == []


class TestItSaysWhereItWent:
    """« Envoyé à l'imprimante » is a claim the owner cannot check.

    On a machine whose default is « Microsoft Print to PDF » the document
    goes to a file and a dialog asks where -- which looks like a fault in
    the application rather than a printer behaving as designed. Naming the
    printer turns a mystery into a fact.
    """

    def test_the_answer_names_the_printer(self, client, tmp_path):
        teacher = paid_teacher(client)
        with_folder(client, tmp_path)
        made = client.post(
            "/api/payouts",
            json={"kind": "teacher", "ref_id": teacher, "month": "2026-09"},
        ).json()

        answer = client.post(f"/api/payouts/{made['id']}/print").json()

        # None on a machine with no printer at all -- said plainly rather
        # than left to be inferred from silence.
        assert "printer" in answer
