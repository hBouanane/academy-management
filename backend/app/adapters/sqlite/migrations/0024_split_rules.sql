-- Les repartitions nommees, et a qui elles s appliquent.
--
-- Jusqu ici l academie avait UNE repartition, la meme partout. Or un
-- professeur chevronne ne se paie pas comme un debutant, et le primaire
-- ne coute pas ce que coute le lycee. Le proprietaire ecrit donc ses
-- regles -- « Prof senior 40/10 », « Primaire 30/20 » -- et dit a qui
-- chacune s applique.
--
-- L ordre de priorite va du plus precis au plus general :
--
--   la classe        cette classe-ci, et elle seule
--   le professeur    toutes ses classes
--   la filiere       Sciences Maths, Ra'ida...
--   le niveau        tout le primaire, tout le college
--   l academie       la repartition de reference, celle des reglages
--
-- La premiere regle trouvee gagne. Une classe sans rien remonte la
-- chaine jusqu a la repartition de l academie.
--
-- Ce qui est DEJA encaisse ne bouge jamais : le partage applique le
-- jour du paiement est ecrit dans le registre, et une regle changee
-- aujourd hui ne vaut que pour ce qui rentrera ensuite.
BEGIN;

CREATE TABLE split_rule (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    name TEXT NOT NULL,
    venue_bp INTEGER NOT NULL CHECK (venue_bp BETWEEN 0 AND 10000),
    owner_bp INTEGER NOT NULL CHECK (owner_bp BETWEEN 0 AND 10000),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (venue_bp + owner_bp <= 10000)
);

CREATE TABLE split_assignment (
    id INTEGER PRIMARY KEY,
    rule_id INTEGER NOT NULL REFERENCES split_rule(id) ON DELETE CASCADE,
    scope TEXT NOT NULL CHECK (scope IN ('class', 'teacher', 'filiere', 'level')),
    -- L identifiant pour class/teacher/level ; pour une filiere, son nom
    -- (elles n ont pas de table a elles).
    ref_id INTEGER,
    ref_text TEXT,
    UNIQUE (scope, ref_id, ref_text)
);

CREATE INDEX IF NOT EXISTS idx_split_assignment ON split_assignment (scope);

COMMIT;
PRAGMA user_version = 24;
