-- Un recu par versement, et non un par professeur et par mois.
--
-- La cle etait (kind, month, scope, ref_id) : deux versements au meme
-- professeur dans le meme mois se marchaient dessus, alors que les deux
-- papiers existent bel et bien -- le second ne remplace pas le premier,
-- il s ajoute.
--
-- Sans payout_id, impossible aussi de retrouver LE fichier d un
-- versement donne. Or un recu ne se regenere pas : on doit pouvoir
-- rouvrir celui qui a ete signe, pas en fabriquer un nouveau.
--
-- NULL pour tout ce qui n est pas un versement (export du mois, feuille
-- d absence) : SQLite considere deux NULL comme distincts dans un
-- index UNIQUE, d ou l index partiel plus bas.

BEGIN;

PRAGMA foreign_keys = OFF;

CREATE TABLE exported_document_new (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('payslip', 'absence', 'excel')),
    month TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('month', 'teacher', 'class')),
    ref_id INTEGER NOT NULL DEFAULT 0,
    payout_id INTEGER,
    path TEXT NOT NULL,
    generated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO exported_document_new
    (id, kind, month, scope, ref_id, payout_id, path, generated_at)
SELECT id, kind, month, scope, ref_id, NULL, path, generated_at
FROM exported_document;

DROP TABLE exported_document;
ALTER TABLE exported_document_new RENAME TO exported_document;

-- Ce qui n a pas de versement garde l unicite d avant.
CREATE UNIQUE INDEX idx_exported_document_plain
    ON exported_document (kind, month, scope, ref_id)
    WHERE payout_id IS NULL;

-- Un versement, un recu.
CREATE UNIQUE INDEX idx_exported_document_payout
    ON exported_document (payout_id)
    WHERE payout_id IS NOT NULL;

PRAGMA foreign_keys = ON;

COMMIT;
PRAGMA user_version = 27;
