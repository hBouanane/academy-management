-- A reduction or gift can be one-shot (this month only) or recurring: when
-- the agenda extends into a new month, recurring adjustments follow the
-- enrollment automatically (each month gets its own editable copy).
BEGIN;

ALTER TABLE adjustment ADD COLUMN recurring INTEGER NOT NULL DEFAULT 0
    CHECK (recurring IN (0, 1));

COMMIT;
PRAGMA user_version = 11;
