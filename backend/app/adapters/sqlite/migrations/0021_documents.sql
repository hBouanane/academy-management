-- Les documents sortis, et ce qui les périme.
--
-- Une fiche de paie imprimée le 5 devient fausse si un impayé rentre le
-- 20 : l'argent a bougé, le papier non. Le client veut être prévenu --
-- mais prévenu JUSTE. « Septembre a changé » ferait crier au loup sur
-- toutes les fiches du mois alors qu'une seule est concernée ; au bout
-- de deux semaines plus personne ne lirait l'avertissement.
--
-- D'où la portée : chaque écriture dit QUI elle touche -- ce professeur,
-- cette classe, ou le mois entier -- et seuls les documents de cette
-- portée-là sont signalés.
--
-- On ne déduit pas ces dates des tables existantes : inscriptions et
-- parts manuelles n'ont pas d'horodatage, et en ajouter partout serait
-- fragile. L'écriture le dit elle-même, au moment où elle se produit.
BEGIN;

CREATE TABLE app_setting (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE document_touch (
    month TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('month', 'teacher', 'class')),
    -- 0 pour la portée « mois » : elle n'a personne à désigner.
    ref_id INTEGER NOT NULL DEFAULT 0,
    touched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (month, scope, ref_id)
);

CREATE TABLE exported_document (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('payslip', 'absence', 'excel')),
    month TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('month', 'teacher', 'class')),
    ref_id INTEGER NOT NULL DEFAULT 0,
    path TEXT NOT NULL,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (kind, month, scope, ref_id)
);

COMMIT;
PRAGMA user_version = 21;
