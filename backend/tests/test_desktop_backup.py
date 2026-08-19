"""Backup-on-close logic — consistency matters more than byte equality.

Et surtout : la sauvegarde doit atterrir LÀ OÙ LE CLIENT REGARDE. Une
copie parfaite enfouie dans %APPDATA% ne sauve personne le jour où le
portable meurt ; un dossier qu'il a choisi, lui, il l'ouvre.

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
        backup_database(db, stamp=f"202607{day:02d}-000000")
    backups = sorted((tmp_path / "backups").glob("data-*.db"))
    assert len(backups) == 30
    assert backups[0].name == "data-20260705-000000.db"  # oldest 4 pruned
    assert backups[-1].name == "data-20260734-000000.db"


def with_setting(db, key, value):
    """Le reglage tel que la page Academie l'aurait enregistre."""
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS app_setting"
        " (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT OR REPLACE INTO app_setting (key, value) VALUES (?, ?)",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def test_the_backup_lands_in_the_folder_meant_for_it(tmp_path):
    db = make_db(tmp_path)
    safe = tmp_path / "coffre"
    with_setting(db, "db_backup_root", safe)
    backup_database(db, stamp="20260729-120000")
    copy = safe / "academie-20260729-120000.db"
    assert copy.exists()
    assert read_value(copy) == "ledger-row"


def test_the_documents_folder_never_receives_the_database(tmp_path):
    """Le coeur de la separation : une cle USB tendue a un professeur
    ne doit pas emporter toute l'academie."""
    db = make_db(tmp_path)
    with_setting(db, "backup_root", tmp_path / "academX")
    backup_database(db, stamp="20260729-120000")
    assert not (tmp_path / "academX").exists()


def test_without_a_chosen_folder_nothing_changes(tmp_path):
    db = make_db(tmp_path)
    target = backup_database(db, stamp="20260729-120000")
    assert target.exists()
    assert not (tmp_path / "coffre").exists()


def test_a_vanished_folder_does_not_lose_the_backup(tmp_path):
    """La clé USB n'est plus branchée : on garde la copie interne et on
    n'empêche surtout pas la fermeture de l'application."""
    db = make_db(tmp_path)
    with_setting(db, "db_backup_root", tmp_path / "cle-usb" / "coffre")
    (tmp_path / "cle-usb").mkdir()
    (tmp_path / "cle-usb").chmod(0o555)
    try:
        target = backup_database(db, stamp="20260729-120000")
    finally:
        (tmp_path / "cle-usb").chmod(0o755)
    assert target.exists()


def test_the_chosen_folder_keeps_only_the_newest(tmp_path):
    db = make_db(tmp_path)
    safe = tmp_path / "coffre"
    with_setting(db, "db_backup_root", safe)
    for day in range(1, 35):
        backup_database(db, stamp=f"202607{day:02d}-000000")
    copies = sorted(safe.glob("academie-*.db"))
    assert len(copies) == 30
    assert copies[-1].name == "academie-20260734-000000.db"
