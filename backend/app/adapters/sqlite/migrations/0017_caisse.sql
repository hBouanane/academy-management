-- La caisse : l'argent réel du mois. Un élève qui paie fait ENTRER l'argent
-- dans la caisse — il n'atterrit dans la poche de personne. Payer un
-- professeur le fait SORTIR. La part de la salle et celle du propriétaire
-- sont des sorties comme les autres : il se paie lui-même comme il paie un
-- professeur, donc rien ne lui appartient tant que ça n'a pas quitté la
-- caisse.
--
-- Les versements cessent donc d'être réservés aux professeurs.
PRAGMA foreign_keys = OFF;
BEGIN;

CREATE TABLE payout (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    beneficiary_kind TEXT NOT NULL
        CHECK (beneficiary_kind IN ('teacher', 'venue', 'owner')),
    beneficiary_id INTEGER NOT NULL,
    month TEXT NOT NULL,
    amount_centimes INTEGER NOT NULL CHECK (amount_centimes > 0),
    paid_on TEXT NOT NULL DEFAULT (date('now')),
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO payout (id, academy_id, beneficiary_kind, beneficiary_id, month,
    amount_centimes, paid_on, note, created_at)
SELECT id, academy_id, 'teacher', teacher_id, month, amount_centimes,
    paid_on, note, created_at
FROM teacher_payout;

DROP TABLE teacher_payout;

CREATE INDEX IF NOT EXISTS idx_payout_month
    ON payout (academy_id, month, beneficiary_kind, beneficiary_id);

COMMIT;
PRAGMA foreign_keys = ON;
PRAGMA user_version = 17;
