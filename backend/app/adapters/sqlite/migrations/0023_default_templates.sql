-- Les trois messages de depart deviennent des modeles comme les autres.
--
-- Ils etaient ecrits en dur : le proprietaire les voyait, ne pouvait pas
-- les toucher, et ecrivait les siens a cote. Or ce sont les memes
-- choses -- il doit pouvoir les reprendre a son gout, les traduire en
-- darija, ou les jeter.
--
-- shown_when : quand le modele a un sens. Proposer « vous n avez pas
-- paye » a une famille qui vient de regler est le meilleur moyen de
-- faire desinstaller l application, alors chaque modele dit quand il
-- sert :
--   always  du moment que l eleve est inscrit ce mois-ci
--   paid    seulement si le mois est regle
--   unpaid  seulement s il reste quelque chose a payer
BEGIN;

ALTER TABLE message_template ADD COLUMN shown_when TEXT NOT NULL
    DEFAULT 'always' CHECK (shown_when IN ('always', 'paid', 'unpaid'));

-- On retient si la liste etait vide AVANT de poser quoi que ce soit :
-- une academie qui a deja ecrit les siens ne doit pas les voir revenir.
CREATE TEMP TABLE liste_vide AS
    SELECT NOT EXISTS (SELECT 1 FROM message_template) AS oui;

INSERT INTO message_template (label, body, shown_when, position)
SELECT * FROM (
    SELECT
        'Confirmation d''inscription' AS label,
        'Bonjour,' || char(10) || char(10) ||
        '{eleve} est bien inscrit(e) pour {mois} en {classes}.' || char(10) ||
        'Montant du mois : {montant}.' || char(10) || char(10) || '{academie}'
            AS body,
        'always' AS shown_when,
        1 AS position
    UNION ALL
    SELECT
        'Reçu de paiement',
        'Bonjour,' || char(10) || char(10) ||
        'Nous avons bien reçu le règlement de {montant} pour {mois} ({eleve}).'
        || char(10) || 'Merci.' || char(10) || char(10) || '{academie}',
        'paid',
        2
    UNION ALL
    SELECT
        'Rappel de paiement',
        'Bonjour,' || char(10) || char(10) ||
        'Le mois de {mois} reste à régler pour {eleve} : {montant}.' || char(10) ||
        'Merci de votre compréhension.' || char(10) || char(10) || '{academie}',
        'unpaid',
        3
)
WHERE (SELECT oui FROM liste_vide);

DROP TABLE liste_vide;

COMMIT;
PRAGMA user_version = 23;
