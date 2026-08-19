-- Classes gain their real-world coordinates (année, filière, parcours —
-- parcours = programme normal vs râ'ida, distinct from filière). Teachers
-- gain capabilities (what they CAN teach), dated assignment periods (who
-- taught a class WHEN — the money follows these), and a creation date.
-- Formation joins as a fourth niveau.
BEGIN;

ALTER TABLE class_group ADD COLUMN annee INTEGER CHECK (annee BETWEEN 1 AND 6);
ALTER TABLE class_group ADD COLUMN filiere TEXT;
ALTER TABLE class_group ADD COLUMN parcours TEXT;

ALTER TABLE teacher ADD COLUMN created_at TEXT;
UPDATE teacher SET created_at = datetime('now') WHERE created_at IS NULL;

ALTER TABLE student ADD COLUMN parcours TEXT;

CREATE TABLE IF NOT EXISTS teacher_capability (
    id INTEGER PRIMARY KEY,
    teacher_id INTEGER NOT NULL REFERENCES teacher(id),
    level_id INTEGER NOT NULL REFERENCES school_level(id),
    annee INTEGER CHECK (annee BETWEEN 1 AND 6),
    parcours TEXT,
    subject_id INTEGER NOT NULL REFERENCES subject(id)
);

-- Who taught a class during which period. NULL dates mean "open" on that
-- side. Payments resolve each month's teacher share against these rows,
-- so collecting an old month always pays whoever taught it.
CREATE TABLE IF NOT EXISTS class_teacher (
    id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL REFERENCES class_group(id),
    teacher_id INTEGER NOT NULL REFERENCES teacher(id),
    from_date TEXT,
    to_date TEXT
);

INSERT INTO class_teacher (class_id, teacher_id, from_date, to_date)
SELECT id, teacher_id, NULL, NULL FROM class_group;

INSERT INTO school_level (academy_id, name, sort_order)
SELECT id, 'Formation', 4 FROM academy
WHERE NOT EXISTS (
    SELECT 1 FROM school_level sl
    WHERE sl.academy_id = academy.id AND sl.name = 'Formation'
);

COMMIT;
PRAGMA user_version = 8;
