-- Les messages que le proprietaire ecrit lui-meme.
--
-- Nos trois modeles sont en francais poli. Lui parle a ses familles
-- comme il leur parle vraiment -- en darija, en arabe, court et direct :
-- « salam khouya {eleve}, had chhar makhallastich ».
--
-- Il ecrit donc les siens, une fois, et les retrouve d'un clic sur
-- n'importe quel eleve. Les {reperes} sont remplaces au moment d'ouvrir
-- WhatsApp : {eleve}, {mois}, {montant}, {classes}, {academie}.
--
-- position : l'ordre qu'il a choisi. Le plus utilise en premier, c'est
-- lui qui sait lequel.
BEGIN;

CREATE TABLE message_template (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    body TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

COMMIT;
PRAGMA user_version = 22;
