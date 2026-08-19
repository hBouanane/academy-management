-- Le verrou de l'application.
--
-- Le danger n'est pas qu'on lise les chiffres, c'est qu'on les CHANGE :
-- un élève qui passe derrière le comptoir et s'offre le mois. D'où un
-- code à l'ouverture, et un reverrouillage automatique -- c'est le
-- portable laissé ouvert pendant le cours qui est le vrai moment de
-- risque, pas le démarrage.
--
-- Une seule ligne, jamais plus : il n'y a qu'un propriétaire. Le code
-- n'est pas gardé tel quel -- seulement de quoi le reconnaître.
--
-- La phrase de secours est la seule porte de sortie : hors ligne,
-- personne ne peut réinitialiser un mot de passe oublié.
BEGIN;

CREATE TABLE app_lock (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    code_salt TEXT NOT NULL,
    code_digest TEXT NOT NULL,
    recovery_salt TEXT NOT NULL,
    recovery_digest TEXT NOT NULL,
    auto_lock_minutes INTEGER NOT NULL DEFAULT 5
        CHECK (auto_lock_minutes BETWEEN 1 AND 240),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

COMMIT;
PRAGMA user_version = 20;
