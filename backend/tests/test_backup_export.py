"""Round 17 : emporter ses sauvegardes.

Les copies se font toutes seules à chaque fermeture, sur le disque de
l'ordinateur. Elles sauvent d'une fausse manœuvre — pas d'un portable
volé ou noyé.

Exiger une clé USB branchée en permanence ne marche pas : personne ne
la laisse là, et une copie automatique qui échoue en silence est le
pire des filets — on y croit, et il n'est pas là.

D'où un geste explicite : il branche sa clé quand il y pense, clique
une fois, et tout part. L'application retient où, et le lui rappelle
quand ça fait trop longtemps.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "data.db"))
    with TestClient(app) as test_client:
        yield test_client


def snapshots(tmp_path, how_many=3):
    """Ce que la fermeture aurait laissé sur le disque."""
    folder = tmp_path / "backups"
    folder.mkdir(exist_ok=True)
    for day in range(1, how_many + 1):
        target = folder / f"data-202608{day:02d}-120000-v21.db"
        conn = sqlite3.connect(target)
        conn.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
        conn.commit()
        conn.close()
    return folder


class TestBackupState:
    def test_a_fresh_install_has_nothing_to_report(self, client):
        state = client.get("/api/backups").json()
        assert state["count"] == 0
        assert state["last_copied_at"] is None
        assert state["destination"] is None

    def test_it_counts_what_is_on_the_disk(self, client, tmp_path):
        snapshots(tmp_path, 3)
        state = client.get("/api/backups").json()
        assert state["count"] == 3
        assert state["newest"] == "data-20260803-120000-v21.db"

    def test_never_copied_is_worth_saying(self, client, tmp_path):
        snapshots(tmp_path, 1)
        assert client.get("/api/backups").json()["stale"] is True


class TestCopyingThemOut:
    def test_one_click_takes_them_all(self, client, tmp_path):
        snapshots(tmp_path, 3)
        stick = tmp_path / "cle-usb"
        done = client.post("/api/backups/copy", json={"path": str(stick)})
        assert done.status_code == 200, done.text
        assert done.json()["copied"] == 3
        assert len(list((stick / "AcademyManagement").glob("*.db"))) == 3

    def test_the_destination_is_remembered(self, client, tmp_path):
        snapshots(tmp_path, 1)
        stick = tmp_path / "cle-usb"
        client.post("/api/backups/copy", json={"path": str(stick)})
        state = client.get("/api/backups").json()
        assert state["destination"] == str(stick)
        assert state["last_copied_at"] is not None
        assert state["stale"] is False

    def test_copying_twice_does_not_duplicate(self, client, tmp_path):
        snapshots(tmp_path, 2)
        stick = tmp_path / "cle-usb"
        client.post("/api/backups/copy", json={"path": str(stick)})
        again = client.post("/api/backups/copy", json={"path": str(stick)})
        assert again.json()["copied"] == 0  # elles y sont déjà
        assert len(list((stick / "AcademyManagement").glob("*.db"))) == 2

    def test_a_new_snapshot_joins_the_others_next_time(self, client, tmp_path):
        snapshots(tmp_path, 2)
        stick = tmp_path / "cle-usb"
        client.post("/api/backups/copy", json={"path": str(stick)})
        snapshots(tmp_path, 4)  # deux fermetures de plus
        assert (
            client.post("/api/backups/copy", json={"path": str(stick)}).json()["copied"]
            == 2
        )

    def test_nothing_to_copy_is_not_an_error(self, client, tmp_path):
        done = client.post("/api/backups/copy", json={"path": str(tmp_path / "cle")})
        assert done.status_code == 200
        assert done.json()["copied"] == 0

    def test_an_unreachable_stick_says_so(self, client, tmp_path):
        snapshots(tmp_path, 1)
        intruder = tmp_path / "pas-un-dossier.txt"
        intruder.write_text("x")
        refused = client.post("/api/backups/copy", json={"path": str(intruder)})
        assert refused.status_code == 422
