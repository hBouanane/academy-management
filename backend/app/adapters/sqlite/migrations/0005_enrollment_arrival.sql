-- Persist the arrival date: a prorated first month is a one-off concession,
-- and the agenda extension must re-price from the package, not carry it.

BEGIN;

ALTER TABLE enrollment ADD COLUMN arrival_date TEXT;

COMMIT;
PRAGMA user_version = 5;
