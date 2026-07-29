-- "Deleting" a reduction becomes deactivation: after a reversed payment the
-- ledger still references the adjustment, and history is never destroyed.
BEGIN;
ALTER TABLE adjustment ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;
COMMIT;
PRAGMA user_version = 6;
