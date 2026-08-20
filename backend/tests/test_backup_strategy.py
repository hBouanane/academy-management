"""Round 23 : sauvegarder quand il y a de quoi, prévenir quand il faut.

Ouvrir l'application pour consulter un chiffre, puis la fermer, ne
mérite pas une copie : trente photographies identiques chassent les
vraies. On ne photographie donc que si la base a bougé.

Et le rappel d'emporter la clé ne doit pas s'afficher tous les jours —
un avertissement permanent finit par faire partie du décor. Il attend
d'avoir trente sauvegardes qui n'ont jamais quitté l'ordinateur : à ce
compte-là, il y a vraiment quelque chose à perdre.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.app import create_app
from desktop import backup_database


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "data.db"))
    with TestClient(app) as test_client:
        yield test_client


def make_db(tmp_path):
    db = tmp_path / "data.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    conn.commit()
    conn.close()
    return db


def kept(tmp_path):
    folder = tmp_path / "backups"
    return (
        sorted(item.name for item in folder.glob("data-*.db"))
        if folder.is_dir()
        else []
    )


def touch_the_data(db, value="quelque chose"):
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO t VALUES (?)", (value,))
    conn.commit()
    conn.close()


class TestOnlyWhenSomethingMoved:
    def test_the_first_close_always_photographs(self, tmp_path):
        db = make_db(tmp_path)
        backup_database(db, stamp="20260801-100000")
        assert kept(tmp_path) == ["data-20260801-100000.db"]

    def test_closing_without_touching_anything_photographs_nothing(self, tmp_path):
        """Il a ouvert pour regarder un chiffre, puis ferme. Rien n'a
        bouge : une copie de plus chasserait une vraie."""
        db = make_db(tmp_path)
        backup_database(db, stamp="20260801-100000")
        backup_database(db, stamp="20260801-110000")
        assert kept(tmp_path) == ["data-20260801-100000.db"]

    def test_a_single_change_is_enough(self, tmp_path):
        db = make_db(tmp_path)
        backup_database(db, stamp="20260801-100000")
        touch_the_data(db)
        backup_database(db, stamp="20260801-110000")
        assert len(kept(tmp_path)) == 2

    def test_it_says_it_did_nothing(self, tmp_path):
        db = make_db(tmp_path)
        backup_database(db, stamp="20260801-100000")
        assert backup_database(db, stamp="20260801-110000") is None


class TestWhenToRemind:
    def test_a_handful_of_backups_says_nothing(self, client, tmp_path):
        _snapshots(tmp_path, 5)
        assert client.get("/api/backups").json()["stale"] is False

    def test_thirty_never_copied_is_worth_saying(self, client, tmp_path):
        _snapshots(tmp_path, 30)
        state = client.get("/api/backups").json()
        assert state["stale"] is True
        assert state["uncopied"] == 30

    def test_copying_settles_it(self, client, tmp_path):
        _snapshots(tmp_path, 30)
        client.post("/api/backups/copy", json={"path": str(tmp_path / "cle")})
        state = client.get("/api/backups").json()
        assert state["stale"] is False
        assert state["uncopied"] == 0

    def test_it_counts_again_from_there(self, client, tmp_path):
        _snapshots(tmp_path, 30)
        client.post("/api/backups/copy", json={"path": str(tmp_path / "cle")})
        _snapshots(tmp_path, 32, start=31)
        assert client.get("/api/backups").json()["uncopied"] == 2


def _snapshots(tmp_path, how_many, start=1):
    """Autant de fermetures qui ont vraiment change quelque chose."""
    db = make_db(tmp_path)
    for index in range(start, how_many + 1):
        touch_the_data(db, f"changement {index}")
        backup_database(db, stamp=f"202608{index:02d}-120000")
