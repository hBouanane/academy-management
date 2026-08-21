"""Round 21 : un reçu en deux moitiés, et un par versement.

Le professeur signe, prend sa moitié, et l'académie garde l'autre. Une
seule feuille, coupée en deux : c'est ainsi qu'on fait au comptoir, et
ça évite d'imprimer deux fois.

Et chaque versement a son reçu. Payer deux fois dans le mois fait deux
papiers ; le second ne remplace jamais le premier — celui-là est déjà
signé.
"""

import io
import re
import zipfile

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


def printed(content: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    return re.sub(r"<[^>]+>", "", xml)


def paid_teacher(client, amounts):
    """Un professeur, et un versement par montant demandé."""
    level, class_id, teacher, package = setup_base(client)
    _, enrollment = enroll(client, level, package, class_id)
    client.post(
        "/api/payments", json={"enrollment_id": enrollment, "paid_on": "2026-09-03"}
    )
    payouts = []
    for amount in amounts:
        posted = client.post(
            "/api/payouts",
            json={
                "kind": "teacher",
                "ref_id": teacher,
                "month": "2026-09",
                "amount_centimes": amount,
            },
        )
        assert posted.status_code == 201, posted.text
        payouts.append(posted.json()["id"])
    return teacher, payouts


class TestTwoHalvesOnOnePage:
    def test_the_receipt_says_it_twice(self, client):
        teacher, payouts = paid_teacher(client, [120 * DH])
        text = printed(
            client.get(
                f"/api/teachers/{teacher}/invoice.docx"
                f"?month=2026-09&payout={payouts[0]}"
            ).content
        )
        # La ligne qui compte apparaît sur chaque moitié, pas ailleurs.
        assert text.count("Versé ce jour") == 2

    def test_each_half_says_to_whom_it_belongs(self, client):
        teacher, payouts = paid_teacher(client, [120 * DH])
        text = printed(
            client.get(
                f"/api/teachers/{teacher}/invoice.docx"
                f"?month=2026-09&payout={payouts[0]}"
            ).content
        )
        assert "Exemplaire académie" in text
        assert "Exemplaire professeur" in text

    def test_there_is_a_line_to_cut_along(self, client):
        teacher, payouts = paid_teacher(client, [120 * DH])
        text = printed(
            client.get(
                f"/api/teachers/{teacher}/invoice.docx"
                f"?month=2026-09&payout={payouts[0]}"
            ).content
        )
        assert "- - -" in text or "✂" in text

    def test_the_month_sheet_stays_a_single_copy(self, client):
        """Sans versement, ce n'est pas un reçu à signer : rien à couper."""
        teacher, _ = paid_teacher(client, [])
        text = printed(
            client.get(f"/api/teachers/{teacher}/invoice.docx?month=2026-09").content
        )
        assert "Exemplaire académie" not in text


class TestOneReceiptPerPayment:
    def test_two_payments_make_two_files(self, client, tmp_path):
        teacher, payouts = paid_teacher(client, [100 * DH, 50 * DH])
        client.put(
            "/api/settings/folders/documents", json={"path": str(tmp_path / "aX")}
        )
        for payout in payouts:
            filed = client.post(
                "/api/documents/file",
                json={
                    "kind": "payslip",
                    "month": "2026-09",
                    "ref_id": teacher,
                    "payout_id": payout,
                },
            )
            assert filed.status_code == 201, filed.text
        drawer = tmp_path / "aX" / "2026-09 Septembre" / "fiches-de-paie"
        assert len(list(drawer.iterdir())) == 2

    def test_the_second_does_not_erase_the_first(self, client, tmp_path):
        """Le premier est déjà signé : on n'y touche pas."""
        teacher, payouts = paid_teacher(client, [100 * DH, 50 * DH])
        client.put(
            "/api/settings/folders/documents", json={"path": str(tmp_path / "aX")}
        )
        first = client.post(
            "/api/documents/file",
            json={
                "kind": "payslip",
                "month": "2026-09",
                "ref_id": teacher,
                "payout_id": payouts[0],
            },
        ).json()["path"]
        client.post(
            "/api/documents/file",
            json={
                "kind": "payslip",
                "month": "2026-09",
                "ref_id": teacher,
                "payout_id": payouts[1],
            },
        )
        from pathlib import Path

        assert "100,00 DH" in printed(Path(first).read_bytes())


class TestAReceiptNeverGoesStale:
    def test_money_moving_later_does_not_flag_it(self, client, tmp_path):
        """Un reçu constate un fait passé : 100 DH sont sortis ce jour-là.
        Rien de ce qui arrive ensuite ne rend cela faux."""
        teacher, payouts = paid_teacher(client, [100 * DH])
        client.put(
            "/api/settings/folders/documents", json={"path": str(tmp_path / "aX")}
        )
        client.post(
            "/api/documents/file",
            json={
                "kind": "payslip",
                "month": "2026-09",
                "ref_id": teacher,
                "payout_id": payouts[0],
            },
        )
        # On fait bouger l'argent DE CE PROFESSEUR après le reçu : un
        # second élève de sa classe paie enfin.
        classes = client.get("/api/classes?month=2026-09").json()
        his = next(row for row in classes if row["teacher_id"] == teacher)
        student = client.post(
            "/api/students", json={"name": "Autre", "level_id": his["level_id"]}
        ).json()["id"]
        package = client.get("/api/packages").json()[0]["id"]
        other = client.post(
            "/api/enrollments",
            json={
                "student_id": student,
                "month": "2026-09",
                "package_id": package,
                "class_ids": [his["id"]],
            },
        ).json()["id"]
        client.post(
            "/api/payments", json={"enrollment_id": other, "paid_on": "2026-09-20"}
        )
        # Le mois a bien bougé pour lui.
        assert client.get("/api/documents/stale?month=2026-09").json() is not None
        stale = client.get("/api/documents/stale?month=2026-09").json()
        assert [item["kind"] for item in stale if item["kind"] == "payslip"] == []
