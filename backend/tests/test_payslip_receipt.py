"""Round 16 : la fiche de paie devient un reçu.

Une fiche sortie n'importe quand ne dit que l'état d'un mois. Celle qui
compte est celle qu'on imprime AU MOMENT DE PAYER : le professeur la
signe, elle atteste de ce qu'il vient de recevoir.

Elle porte donc le versement — sa date et son montant — en plus du
détail du mois. Sans versement désigné, elle reste ce qu'elle était :
l'état du mois.
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


def text_of(content: bytes) -> str:
    """Ce qu'on lirait sur le papier."""
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    import re

    return re.sub(r"<[^>]+>", "", xml)


def paid_teacher(client, amount=None):
    level, class_id, teacher, package = setup_base(client)
    _, enrollment = enroll(client, level, package, class_id)
    client.post(
        "/api/payments", json={"enrollment_id": enrollment, "paid_on": "2026-09-03"}
    )
    body = {"kind": "teacher", "ref_id": teacher, "month": "2026-09"}
    if amount is not None:
        body["amount_centimes"] = amount
    payout = client.post("/api/payouts", json=body)
    assert payout.status_code == 201, payout.text
    return teacher, payout.json()


class TestPayslipAsReceipt:
    def test_without_a_payout_it_is_the_month_as_before(self, client):
        teacher, _ = paid_teacher(client)
        sheet = client.get(f"/api/teachers/{teacher}/invoice.docx?month=2026-09")
        assert sheet.status_code == 200
        assert "Versé ce jour" not in text_of(sheet.content)

    def test_a_payout_puts_the_amount_paid_on_the_paper(self, client):
        teacher, payout = paid_teacher(client, amount=120 * DH)
        sheet = client.get(
            f"/api/teachers/{teacher}/invoice.docx?month=2026-09&payout={payout['id']}"
        )
        assert sheet.status_code == 200
        printed = text_of(sheet.content)
        assert "Versé ce jour" in printed
        assert "120,00 DH" in printed

    def test_the_receipt_carries_the_day_the_money_changed_hands(self, client):
        """Le jour du versement, pas le mois qu'il couvre : on peut payer
        septembre en novembre, et c'est novembre qu'on signe."""
        teacher, payout = paid_teacher(client, amount=50 * DH)
        line = next(
            entry
            for entry in client.get("/api/caisse?month=2026-09").json()["lines"]
            if entry["kind"] == "teacher" and entry["ref_id"] == teacher
        )
        day = line["payouts"][0]["paid_on"]
        printed = text_of(
            client.get(
                f"/api/teachers/{teacher}/invoice.docx"
                f"?month=2026-09&payout={payout['id']}"
            ).content
        )
        assert day in printed

    def test_an_unknown_payout_is_refused(self, client):
        teacher, _ = paid_teacher(client)
        refused = client.get(
            f"/api/teachers/{teacher}/invoice.docx?month=2026-09&payout=9999"
        )
        assert refused.status_code == 404

    def test_someone_elses_payout_is_refused(self, client):
        """Un reçu doit attester d'un versement fait À CE professeur."""
        _, payout = paid_teacher(client)
        other = client.post("/api/teachers", json={"name": "Sara Alami"}).json()["id"]
        refused = client.get(
            f"/api/teachers/{other}/invoice.docx?month=2026-09&payout={payout['id']}"
        )
        assert refused.status_code == 404

    def test_the_filed_copy_can_be_a_receipt_too(self, client, tmp_path):
        teacher, payout = paid_teacher(client, amount=75 * DH)
        client.put(
            "/api/settings/folders/documents", json={"path": str(tmp_path / "aX")}
        )
        filed = client.post(
            "/api/documents/file",
            json={
                "kind": "payslip",
                "month": "2026-09",
                "ref_id": teacher,
                "payout_id": payout["id"],
            },
        )
        assert filed.status_code == 201, filed.text
        from pathlib import Path

        written = Path(filed.json()["path"])
        assert "Versé ce jour" in text_of(written.read_bytes())
