-- Qui touche quoi sur une classe, un mois donné.
--
-- Par défaut l'app calcule au prorata des JOURS enseignés de part et d'autre
-- de la reprise — c'est juste, et ça marche tout seul. Mais le propriétaire
-- doit pouvoir trancher autrement : un professeur parti en cours de mois a
-- pu préparer tout le trimestre, un remplaçant a pu assurer double dose.
-- Cette table stocke SA décision, en pourcentages (jamais en montants : un
-- élève qui s'inscrit en cours de mois ou une réduction rendrait un montant
-- figé faux, alors qu'un pourcentage reste juste).
--
-- Absente = répartition automatique. Présente = elle fait foi.
BEGIN;

CREATE TABLE class_month_share (
    id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL REFERENCES class_group(id),
    month TEXT NOT NULL,
    teacher_id INTEGER NOT NULL REFERENCES teacher(id),
    share_bp INTEGER NOT NULL CHECK (share_bp BETWEEN 0 AND 10000),
    UNIQUE (class_id, month, teacher_id)
);

CREATE INDEX IF NOT EXISTS idx_class_month_share
    ON class_month_share (class_id, month);

COMMIT;
PRAGMA user_version = 18;
