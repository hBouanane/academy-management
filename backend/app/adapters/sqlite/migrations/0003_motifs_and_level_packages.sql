-- Motifs become reusable data; packages belong to a school level.
-- One transaction: a crash mid-migration must leave the database at v2.

BEGIN;

CREATE TABLE motif (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    label TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    UNIQUE (academy_id, label)
);

-- NULL level_id = legacy "all levels" packages keep working.
ALTER TABLE package ADD COLUMN level_id INTEGER REFERENCES school_level(id);

COMMIT;
PRAGMA user_version = 3;
