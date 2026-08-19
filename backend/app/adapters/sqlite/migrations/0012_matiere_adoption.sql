-- Matières lose the archive half-state: they are now delete-with-guardrails
-- (deletable only with zero classes). Every archived matière is restored,
-- and legacy "Tous niveaux" matières are adopted into the niveau of their
-- classes — copies are created where one name spanned several niveaux —
-- so the "Tous niveaux (anciennes)" section disappears for good.
BEGIN;

UPDATE subject SET is_active = 1 WHERE is_active = 0;

-- Unused legacy matières (no class ever): plain deletion, capabilities too.
DELETE FROM teacher_capability WHERE subject_id IN (
    SELECT id FROM subject s WHERE s.level_id IS NULL
    AND NOT EXISTS (SELECT 1 FROM class_group cg WHERE cg.subject_id = s.id)
);
DELETE FROM subject WHERE level_id IS NULL
    AND NOT EXISTS (
        SELECT 1 FROM class_group cg WHERE cg.subject_id = subject.id
    );

-- Used legacy matières adopt the (lowest) niveau of their classes.
UPDATE subject SET level_id = (
    SELECT MIN(cg.level_id) FROM class_group cg WHERE cg.subject_id = subject.id
) WHERE level_id IS NULL;

-- One name taught in several niveaux: each extra niveau gets its own copy…
INSERT OR IGNORE INTO subject (academy_id, level_id, name, is_active)
SELECT DISTINCT s.academy_id, cg.level_id, s.name, 1
FROM class_group cg JOIN subject s ON s.id = cg.subject_id
WHERE cg.level_id != s.level_id;

INSERT OR IGNORE INTO subject (academy_id, level_id, name, is_active)
SELECT DISTINCT s.academy_id, tc.level_id, s.name, 1
FROM teacher_capability tc JOIN subject s ON s.id = tc.subject_id
WHERE tc.level_id != s.level_id;

-- …and classes / capabilities re-point to the copy of their own niveau.
UPDATE class_group SET subject_id = (
    SELECT s2.id FROM subject s2
    JOIN subject s1 ON s1.id = class_group.subject_id
    WHERE s2.academy_id = s1.academy_id AND s2.name = s1.name
      AND s2.level_id = class_group.level_id
) WHERE EXISTS (
    SELECT 1 FROM subject s1 WHERE s1.id = class_group.subject_id
      AND s1.level_id != class_group.level_id
);

UPDATE teacher_capability SET subject_id = (
    SELECT s2.id FROM subject s2
    JOIN subject s1 ON s1.id = teacher_capability.subject_id
    WHERE s2.academy_id = s1.academy_id AND s2.name = s1.name
      AND s2.level_id = teacher_capability.level_id
) WHERE EXISTS (
    SELECT 1 FROM subject s1 WHERE s1.id = teacher_capability.subject_id
      AND s1.level_id != teacher_capability.level_id
);

COMMIT;
PRAGMA user_version = 12;
