"""Backup-on-close logic — written first (TDD)."""

from desktop import backup_database


def make_db(tmp_path, content=b"sqlite-bytes"):
    db = tmp_path / "data.db"
    db.write_bytes(content)
    return db


def test_backup_copies_the_database_with_a_timestamped_name(tmp_path):
    db = make_db(tmp_path)
    target = backup_database(db, stamp="20260729-120000")
    assert target == tmp_path / "backups" / "data-20260729-120000.db"
    assert target.read_bytes() == db.read_bytes()


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
