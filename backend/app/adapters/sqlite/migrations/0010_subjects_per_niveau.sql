-- Matières belong to their niveau: « Mathématique » in Primaire and in
-- Collège are two entries (typing the name again in another niveau IS the
-- copy). Rebuild is needed because the old UNIQUE(academy, name) forbade
-- the same name twice. Legacy rows keep level_id NULL (visible everywhere).
PRAGMA foreign_keys = OFF;
BEGIN;

CREATE TABLE subject_new (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    level_id INTEGER REFERENCES school_level(id),
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    UNIQUE (academy_id, level_id, name)
);

INSERT INTO subject_new (id, academy_id, name, is_active)
SELECT id, academy_id, name, is_active FROM subject;

DROP TABLE subject;
ALTER TABLE subject_new RENAME TO subject;

COMMIT;
PRAGMA foreign_keys = ON;
PRAGMA user_version = 10;
