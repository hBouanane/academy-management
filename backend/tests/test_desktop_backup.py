"""Backup-on-close logic — consistency matters more than byte equality.


Ce dossier-là n'est PAS celui des documents. Une fiche de paie se
donne au professeur, s'imprime, se partage ; la base, elle, contient
toute l'académie — chaque élève, chaque paiement. Les mélanger ferait
voyager le tout dès qu'il tend sa clé USB à quelqu'un.
"""

import sqlite3

from desktop import backup_database


def make_db(tmp_path, value="ledger-row"):
    db = tmp_path / "data.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (v TEXT)")
    conn.execute("INSERT INTO t VALUES (?)", (value,))
    conn.commit()
    conn.close()
    return db


def read_value(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT v FROM t").fetchone()[0]
    finally:
        conn.close()


def test_backup_produces_a_consistent_timestamped_copy(tmp_path):
    db = make_db(tmp_path)
    target = backup_database(db, stamp="20260729-120000")
    assert target == tmp_path / "backups" / "data-20260729-120000.db"
    assert read_value(target) == "ledger-row"


def test_backup_is_consistent_while_a_writer_holds_a_connection(tmp_path):
    # The online backup API must produce a valid snapshot even with another
    # connection open on the database (the uvicorn thread scenario).
    db = make_db(tmp_path)
    writer = sqlite3.connect(db)
    writer.execute("INSERT INTO t VALUES ('second')")
    writer.commit()
    try:
        target = backup_database(db, stamp="20260729-130000")
        rows = sqlite3.connect(target).execute("SELECT COUNT(*) FROM t").fetchone()
        assert rows[0] == 2
    finally:
        writer.close()


def test_missing_database_backs_up_nothing(tmp_path):
    assert backup_database(tmp_path / "data.db") is None
    assert not (tmp_path / "backups").exists()


def test_old_backups_are_pruned_to_the_newest_thirty(tmp_path):
    db = make_db(tmp_path)
    for day in range(1, 35):
        # Une journée de travail entre deux fermetures : sans changement,
        # l'application ne photographie plus rien (et elle a raison).
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO t VALUES (?)", (f"jour {day}",))
        conn.commit()
        conn.close()
        backup_database(db, stamp=f"202607{day:02d}-000000")
    backups = sorted((tmp_path / "backups").glob("data-*.db"))
    assert len(backups) == 30
    assert backups[0].name == "data-20260705-000000.db"  # oldest 4 pruned
    assert backups[-1].name == "data-20260734-000000.db"


def test_without_a_chosen_folder_nothing_changes(tmp_path):
    db = make_db(tmp_path)
    target = backup_database(db, stamp="20260729-120000")
    assert target.exists()
    assert not (tmp_path / "coffre").exists()


def test_an_older_backup_is_brought_forward(tmp_path):
    """Restaurer une sauvegarde ancienne doit marcher : les migrations
    la rattrapent au demarrage."""
    from app.adapters.sqlite.db import connect, init_db
    from app.adapters.sqlite.migrations import latest_version

    old = tmp_path / "ancienne.db"
    conn = sqlite3.connect(old)
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()
    init_db(connect(str(old)))
    assert (
        sqlite3.connect(old).execute("PRAGMA user_version").fetchone()[0]
        == latest_version()
    )


def test_a_backup_from_a_newer_release_is_named_in_the_refusal(tmp_path):
    """L'inverse est dangereux : une base plus recente que l'application
    ne doit surtout pas etre ouverte a l'aveugle. Et le client doit lire
    la vraie raison, pas « le serveur interne n'a pas demarre »."""
    from desktop import database_complaint

    future = tmp_path / "futur.db"
    conn = sqlite3.connect(future)
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()
    complaint = database_complaint(future)
    assert complaint is not None
    assert "plus récente" in complaint


def test_a_healthy_database_raises_no_complaint(tmp_path):
    from desktop import database_complaint

    assert database_complaint(make_db(tmp_path)) is None


def test_a_database_that_does_not_exist_yet_is_fine(tmp_path):
    from desktop import database_complaint

    assert database_complaint(tmp_path / "pas-encore.db") is None
