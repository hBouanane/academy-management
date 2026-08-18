-- Un trop-versé a deux issues, et c'est le propriétaire qui choisit :
--   le déduire plus tard — le rappel reste affiché jusqu'à ce qu'il le fasse ;
--   ou le PRENDRE À SA CHARGE — l'académie l'assume, le professeur garde
--   l'argent, et le rappel s'éteint.
--
-- On garde la trace : « offert » n'est pas « oublié ». Chaque prise en
-- charge est une ligne datée, annulable si elle a été saisie par erreur.
BEGIN;

CREATE TABLE overpaid_charge (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    beneficiary_kind TEXT NOT NULL
        CHECK (beneficiary_kind IN ('teacher', 'venue', 'owner')),
    beneficiary_id INTEGER NOT NULL,
    month TEXT NOT NULL,
    amount_centimes INTEGER NOT NULL CHECK (amount_centimes > 0),
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_overpaid_charge
    ON overpaid_charge (academy_id, month, beneficiary_kind, beneficiary_id);

COMMIT;
PRAGMA user_version = 19;
