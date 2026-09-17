-- Le journal : ce qui a bouge, et quand.
--
-- Rien de neuf n est calcule ici. Tout ce qu il retient existe deja,
-- disperse entre payment, ledger_entry, payout et guarantee -- mais sous
-- une forme qu on interroge, pas qu on relit. Le jour ou il faut
-- retrouver LE paiement encaisse sur le mauvais mois, cette dispersion
-- est exactement le probleme.
--
-- subject_label fige le nom au moment de l ecriture. Un eleve renomme
-- plus tard ne doit pas reecrire ce qui etait affiche ce jour-la : un
-- journal qui se corrige tout seul n en est plus un.
--
-- Pas de colonne « qui » : l application est mono-poste et le
-- proprietaire est seul devant. Inventer un auteur donnerait a la ligne
-- une precision qu elle n a pas.

BEGIN;

CREATE TABLE IF NOT EXISTS journal_entry (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    -- Au milliseme : deux actions dans la meme seconde se compareraient
    -- egales, et l ordre de lecture deviendrait arbitraire.
    happened_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
    action TEXT NOT NULL,
    month TEXT,
    subject_kind TEXT,
    subject_id INTEGER,
    subject_label TEXT,
    amount_centimes INTEGER,
    detail TEXT
);

-- La lecture par defaut : le plus recent en premier.
CREATE INDEX IF NOT EXISTS idx_journal_recent
    ON journal_entry (academy_id, id DESC);

-- Les deux facons de retrouver une ligne : par mois, ou par qui.
CREATE INDEX IF NOT EXISTS idx_journal_month
    ON journal_entry (academy_id, month);
CREATE INDEX IF NOT EXISTS idx_journal_subject
    ON journal_entry (academy_id, subject_kind, subject_id);

COMMIT;
PRAGMA user_version = 28;
