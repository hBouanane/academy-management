-- A class may legally have NO teacher (« Sans professeur ») while the owner
-- looks for a replacement: teacher_id becomes nullable. On paid months, the
-- days nobody taught route that class's teacher share to the académie as
-- escrow — never silently to a departed teacher.
PRAGMA foreign_keys = OFF;
BEGIN;

CREATE TABLE class_group_new (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    level_id INTEGER NOT NULL REFERENCES school_level(id),
    subject_id INTEGER NOT NULL REFERENCES subject(id),
    teacher_id INTEGER REFERENCES teacher(id),
    name TEXT NOT NULL DEFAULT 'A',
    day_of_week INTEGER CHECK (day_of_week BETWEEN 0 AND 6),
    start_time TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    annee INTEGER CHECK (annee BETWEEN 1 AND 6),
    filiere TEXT,
    parcours TEXT,
    UNIQUE (academy_id, level_id, subject_id, teacher_id, name)
);

INSERT INTO class_group_new (id, academy_id, level_id, subject_id, teacher_id,
    name, day_of_week, start_time, is_active, annee, filiere, parcours)
SELECT id, academy_id, level_id, subject_id, teacher_id,
    name, day_of_week, start_time, is_active, annee, filiere, parcours
FROM class_group;

DROP TABLE class_group;
ALTER TABLE class_group_new RENAME TO class_group;

COMMIT;
PRAGMA foreign_keys = ON;
PRAGMA user_version = 13;
