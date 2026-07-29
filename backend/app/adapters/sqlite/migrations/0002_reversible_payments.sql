-- Reversals need re-posting: replace payment's hard UNIQUE(enrollment_id)
-- with "one ACTIVE payment per enrollment" (partial unique index), and add
-- reversed_at. SQLite cannot alter constraints, so the table is rebuilt.

-- The rebuild is one explicit transaction: a crash mid-migration must leave
-- the database exactly at version 1, never in a half-rebuilt state.
-- (foreign_keys pragmas must sit outside the transaction to take effect.)
PRAGMA foreign_keys = OFF;
BEGIN;

CREATE TABLE payment_v2 (
    id INTEGER PRIMARY KEY,
    enrollment_id INTEGER NOT NULL REFERENCES enrollment(id),
    amount_centimes INTEGER NOT NULL CHECK (amount_centimes >= 0),
    paid_on TEXT NOT NULL DEFAULT (date('now')),
    reversed_at TEXT
);

INSERT INTO payment_v2 (id, enrollment_id, amount_centimes, paid_on)
SELECT id, enrollment_id, amount_centimes, paid_on FROM payment;

DROP TABLE payment;
ALTER TABLE payment_v2 RENAME TO payment;

CREATE UNIQUE INDEX idx_payment_active_enrollment
    ON payment (enrollment_id) WHERE reversed_at IS NULL;

COMMIT;
PRAGMA user_version = 2;
PRAGMA foreign_keys = ON;
