-- L annee scolaire : la saison, et le mois ou elle s arrete.
--
-- Les mois defilaient sans fin. Or une academie ne vit pas en mois,
-- elle vit en rentrees : on ouvre en septembre, on ferme en juin, et
-- l ete on ne compte pas les memes choses. Sans cette borne, aucun
-- bilan de saison n etait possible -- seulement douze bilans separes.
--
-- Le mois de fin se choisit : ici la rentree va de septembre a juin,
-- ailleurs elle court jusqu en juillet. Personne d autre que lui ne
-- sait quand SON annee s arrete.

BEGIN;

CREATE TABLE school_year (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    name TEXT NOT NULL,
    start_month TEXT NOT NULL,
    end_month TEXT NOT NULL,
    -- Tant que c est NULL, l annee court. Une annee close ne se
    -- recalcule plus : c est une saison rangee, pas un brouillon.
    closed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (academy_id, name),
    CHECK (end_month >= start_month)
);

CREATE INDEX idx_school_year_academy ON school_year (academy_id, start_month);

-- Une premiere annee posee sur ce qui existe deja, sinon le proprietaire
-- ouvrirait un rapport de saison vide en se demandant ou sont passees
-- ses recettes. Elle part du plus ancien mois saisi et couvre douze
-- mois ; il en corrigera la fin d un clic.
INSERT INTO school_year (academy_id, name, start_month, end_month)
SELECT
    a.id,
    substr(debut.mois, 1, 4) || '-' ||
        CAST(CAST(substr(debut.mois, 1, 4) AS INTEGER) + 1 AS TEXT),
    debut.mois,
    printf(
        '%04d-%02d',
        CAST(substr(debut.mois, 1, 4) AS INTEGER)
            + (CAST(substr(debut.mois, 6, 2) AS INTEGER) + 10) / 12,
        (CAST(substr(debut.mois, 6, 2) AS INTEGER) + 10) % 12 + 1
    )
FROM academy a
CROSS JOIN (
    SELECT COALESCE(
        (SELECT MIN(month) FROM enrollment),
        strftime('%Y-%m', 'now')
    ) AS mois
) AS debut
WHERE NOT EXISTS (SELECT 1 FROM school_year WHERE academy_id = a.id);

COMMIT;
PRAGMA user_version = 26;
