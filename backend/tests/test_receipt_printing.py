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


def _forget_the_record(tmp_path, payout_id):
    """The file is on disk, the register has lost it -- what a crash
    between the write and the record leaves behind."""
    import sqlite3

    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("DELETE FROM exported_document WHERE payout_id = ?", (payout_id,))
    conn.commit()
    conn.close()


def _lock_docx(monkeypatch):
    """Word, holding the document it is printing."""
    import pathlib

    real = pathlib.Path.write_bytes

    def refuse(self, data):
        if self.suffix == ".docx":
            raise PermissionError(13, "Permission denied", str(self))
        return real(self, data)

    monkeypatch.setattr(pathlib.Path, "write_bytes", refuse)


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


class TestAReceiptOpenInWordIsNotACrash:
    """Word holds a .docx open while it prints it.

    So the everyday sequence -- print a receipt, pay the same teacher
    again -- meets a locked file. That is not an exceptional state to be
    defended against; it is Tuesday. It answered with a stack trace and a
    500, which tells the owner nothing he can act on.
    """

    def test_a_locked_file_names_the_remedy(self, client, tmp_path, monkeypatch):
        teacher = paid_teacher(client)
        with_folder(client, tmp_path)
        made = client.post(
            "/api/payouts",
            json={"kind": "teacher", "ref_id": teacher, "month": "2026-09"},
        ).json()
        # The paper is gone from the register but not from the disk, so
        # printing has to write it again -- onto a file Word is holding.
        _forget_the_record(tmp_path, made["id"])
        _lock_docx(monkeypatch)

        answer = client.post(f"/api/payouts/{made['id']}/print")

        assert answer.status_code == 409
        detail = answer.json()["detail"]
        # It says which file, and what to do about it.
        assert "Word" in detail
        assert ".docx" in detail
        assert client.sent == []

    def test_a_receipt_that_could_not_be_filed_is_announced_at_the_payout(
        self, client, tmp_path, monkeypatch
    ):
        """The money moved -- so this is not a failure -- but silence here
        is how the trouble reappears at the printer, weeks later, with the
        professor standing in front of him."""
        teacher = paid_teacher(client)
        with_folder(client, tmp_path)
        _lock_docx(monkeypatch)

        answer = client.post(
            "/api/payouts",
            json={"kind": "teacher", "ref_id": teacher, "month": "2026-09"},
        )

        assert answer.status_code == 201
        assert "Word" in answer.json()["receipt_error"]
        # The payout itself stands: paperwork comes second.
        caisse = client.get("/api/caisse?month=2026-09").json()
        line = next(
            x
            for x in caisse["lines"]
            if x["kind"] == "teacher" and x["ref_id"] == teacher
        )
        assert line["paid_centimes"] > 0


class TestASignedReceiptIsNeverWrittenOver:
    """A receipt on disk under a live name, belonging to no payout, is the
    paper of a payout that no longer exists. Its figures are somebody
    else's, and the professor may hold it signed.

    Overwriting it destroys the only trace of a sheet still in circulation.
    """

    def test_a_stray_receipt_moves_aside(self, client, tmp_path):
        teacher = paid_teacher(client)
        root = with_folder(client, tmp_path)
        made = client.post(
            "/api/payouts",
            json={"kind": "teacher", "ref_id": teacher, "month": "2026-09"},
        ).json()
        drawer = root / "2026-09 Septembre" / "fiches-de-paie"
        stray = next(drawer.iterdir())
        stray.write_bytes(b"le papier deja signe")
        _forget_the_record(tmp_path, made["id"])

        client.post(f"/api/payouts/{made['id']}/print")

        # The old sheet is still readable, marked; the new one took the name.
        aside = drawer / f"{stray.stem} - annule{stray.suffix}"
        assert aside.read_bytes() == b"le papier deja signe"
        assert stray.exists() and stray.read_bytes() != b"le papier deja signe"

    def test_a_second_stray_does_not_replace_the_first(self, tmp_path):
        """Two cancellations in one month land on the same « annule » name.

        « - annule-2 » is ugly. One file quietly replacing another is
        worse.
        """
        from app.services import documents

        drawer = tmp_path / "drawer"
        drawer.mkdir()
        first = drawer / "paie-X-versement-01.docx"
        first.write_bytes(b"un")
        documents.set_aside(first)
        first.write_bytes(b"deux")

        documents.set_aside(first)

        assert (drawer / "paie-X-versement-01 - annule.docx").read_bytes() == b"un"
        assert (drawer / "paie-X-versement-01 - annule-2.docx").read_bytes() == b"deux"
