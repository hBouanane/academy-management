"""Backup-on-close logic — consistency matters more than byte equality."""

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
