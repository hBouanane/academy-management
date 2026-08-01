-- Niveaux become user-manageable: the client can add "Soutien", "Langues"…
-- Each niveau declares its TEACHING structure: 0 = one block (Primaire,
-- Formation), N = split into N années (Collège 3, Lycée 3).
BEGIN;

ALTER TABLE school_level ADD COLUMN teaching_annees INTEGER NOT NULL DEFAULT 0
    CHECK (teaching_annees BETWEEN 0 AND 12);

UPDATE school_level SET teaching_annees = 3 WHERE name IN ('Collège', 'Lycée');

COMMIT;
PRAGMA user_version = 9;
