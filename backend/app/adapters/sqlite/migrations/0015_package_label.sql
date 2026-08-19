-- Price variants: a forfait can carry an optional label. For bloc niveaux
-- (Primaire, Formation) forfaits are pure price points — « 1ère–4ème année »,
-- « 5ème–6ème année », « Cas particulier » — chosen per student. They are
-- NOT reductions: the reduction/gift mechanism stays a separate concept.
BEGIN;

ALTER TABLE package ADD COLUMN label TEXT;

COMMIT;
PRAGMA user_version = 15;
