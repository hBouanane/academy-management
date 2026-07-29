-- Sponsors: each bearer of a reduction can cover an explicit part (DH or %).
-- Proration: configurable month segments pricing late arrivals.
-- One transaction: a crash mid-migration must leave the database at v3.

BEGIN;

ALTER TABLE adjustment_bearer ADD COLUMN share_centimes INTEGER;
ALTER TABLE adjustment_bearer ADD COLUMN share_bp INTEGER;
ALTER TABLE academy ADD COLUMN proration_json TEXT;

COMMIT;
PRAGMA user_version = 4;
