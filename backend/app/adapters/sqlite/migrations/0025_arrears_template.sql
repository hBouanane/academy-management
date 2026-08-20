-- Un modele pour les familles qui doivent plusieurs mois.
--
-- Le rappel ordinaire parle d un mois. Mais une famille qui traine
-- depuis la rentree en doit trois, et lui ecrire trois fois serait
-- ridicule -- comme lui reclamer 300 DH quand elle en doit 900.
--
-- « arrears » rejoint donc les moments ou un message a un sens. Il ne
-- se propose que s il y a VRAIMENT plusieurs mois en retard : pour un
-- seul, le rappel du mois suffit, et deux messages sur la meme dette
-- se contrediraient.
--
-- SQLite ne sait pas elargir un CHECK : on refait la table.
BEGIN;

PRAGMA foreign_keys = OFF;

CREATE TABLE message_template_new (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    body TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    shown_when TEXT NOT NULL DEFAULT 'always'
        CHECK (shown_when IN ('always', 'paid', 'unpaid', 'arrears'))
);

INSERT INTO message_template_new (id, label, body, position, created_at, shown_when)
SELECT id, label, body, position, created_at, shown_when FROM message_template;

DROP TABLE message_template;
ALTER TABLE message_template_new RENAME TO message_template;

PRAGMA foreign_keys = ON;

-- Un modele tout pret, sinon il faudrait deviner que ce moment existe.
-- Il reste modifiable et supprimable comme les autres.
INSERT INTO message_template (label, body, shown_when, position)
SELECT
    'Rappel de plusieurs mois',
    'Bonjour,' || char(10) || char(10) ||
    'Il reste {impayes} à régler pour {eleve} ({mois_impayes}).' || char(10) ||
    'Merci de passer nous voir.' || char(10) || char(10) || '{academie}',
    'arrears',
    (SELECT COALESCE(MAX(position), 0) + 1 FROM message_template)
WHERE NOT EXISTS (
    SELECT 1 FROM message_template WHERE shown_when = 'arrears'
);

COMMIT;
PRAGMA user_version = 25;
