-- The month has a rhythm: students pay at the START, professors are paid at
-- the END. Two consequences the app must model honestly.
--
-- 1. « Garantie professeur » (guarantee): an unpaid student does NOT cost the
--    professor anything — he is paid for the days he taught, guaranteed by
--    the académie. The salle takes the hit WITH the académie: when nothing
--    was collected, la salle receives nothing. Cash stays at zero: only the
--    ledger's who-earned-what moves. When the student finally pays, the
--    guarantee is recovered from the payment (never clawed back from the
--    professor), and everything lands where a normal payment would.
--
-- 2. « Versements » (teacher_payout): what the owner ACTUALLY handed each
--    professor, month by month. Deliberately NOT in the ledger — the ledger
--    says who EARNED what; paying it out is a separate cash event, so
--    « Gagné » never shrinks because a payout was recorded.
PRAGMA foreign_keys = OFF;
BEGIN;

CREATE TABLE ledger_entry_new (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    month TEXT NOT NULL,
    entry_type TEXT NOT NULL CHECK (
        entry_type IN ('payment_in', 'allocation', 'adjustment', 'reversal',
                       'refund', 'avance', 'guarantee')
    ),
    beneficiary_kind TEXT CHECK (beneficiary_kind IN ('venue', 'owner', 'teacher')),
    beneficiary_id INTEGER,
    amount_centimes INTEGER NOT NULL,
    payment_id INTEGER REFERENCES payment(id),
    -- Guarantee lines exist before any payment: they hang off the enrollment.
    enrollment_id INTEGER REFERENCES enrollment(id),
    adjustment_id INTEGER REFERENCES adjustment(id),
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO ledger_entry_new (id, academy_id, month, entry_type,
    beneficiary_kind, beneficiary_id, amount_centimes, payment_id,
    adjustment_id, note, created_at)
SELECT id, academy_id, month, entry_type, beneficiary_kind, beneficiary_id,
    amount_centimes, payment_id, adjustment_id, note, created_at
FROM ledger_entry;

DROP TABLE ledger_entry;
ALTER TABLE ledger_entry_new RENAME TO ledger_entry;

CREATE INDEX IF NOT EXISTS idx_ledger_month ON ledger_entry (academy_id, month);
CREATE INDEX IF NOT EXISTS idx_ledger_beneficiary
    ON ledger_entry (beneficiary_kind, beneficiary_id, month);
CREATE INDEX IF NOT EXISTS idx_ledger_enrollment ON ledger_entry (enrollment_id);

-- One guarantee per enrollment: until when the student actually attended.
-- present_until NULL = the whole month.
CREATE TABLE guarantee (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    enrollment_id INTEGER NOT NULL UNIQUE REFERENCES enrollment(id),
    month TEXT NOT NULL,
    present_until TEXT,
    amount_centimes INTEGER NOT NULL CHECK (amount_centimes >= 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- « Il a arrêté » : the student is not carried into the next month.
ALTER TABLE enrollment ADD COLUMN stopped INTEGER NOT NULL DEFAULT 0
    CHECK (stopped IN (0, 1));

-- What each professor was actually handed, month by month (installments
-- allowed — the owner pays in several times just like students do).
CREATE TABLE teacher_payout (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    teacher_id INTEGER NOT NULL REFERENCES teacher(id),
    month TEXT NOT NULL,
    amount_centimes INTEGER NOT NULL CHECK (amount_centimes > 0),
    paid_on TEXT NOT NULL DEFAULT (date('now')),
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_payout_month
    ON teacher_payout (academy_id, month, teacher_id);

COMMIT;
PRAGMA foreign_keys = ON;
PRAGMA user_version = 16;
