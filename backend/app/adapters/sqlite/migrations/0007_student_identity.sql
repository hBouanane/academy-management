-- Pré-inscription identity: prénom, année/filière within the niveau, the
-- school attended, tagged phone numbers (étudiant/mère/père/…), and when the
-- record was created. Existing single phones migrate into the tagged table.
BEGIN;

ALTER TABLE student ADD COLUMN first_name TEXT;
ALTER TABLE student ADD COLUMN annee INTEGER CHECK (annee BETWEEN 1 AND 6);
ALTER TABLE student ADD COLUMN filiere TEXT;
ALTER TABLE student ADD COLUMN school_id INTEGER REFERENCES school(id);
ALTER TABLE student ADD COLUMN created_at TEXT;

UPDATE student SET created_at = datetime('now') WHERE created_at IS NULL;

CREATE TABLE IF NOT EXISTS school (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS student_phone (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES student(id),
    tag TEXT NOT NULL,
    number TEXT NOT NULL
);

INSERT INTO student_phone (student_id, tag, number)
SELECT id, 'étudiant', phone FROM student WHERE phone IS NOT NULL;

COMMIT;
PRAGMA user_version = 7;
