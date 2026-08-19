-- Money grows two honest concepts:
--   refund  — cash returned to a student after his class was archived; the
--             promise is a `refund` row (À rembourser), the ledger moves only
--             when the cash actually leaves (Marqué remboursé).
--   avance  — a partial payment: the académie fronts every beneficiary his
--             FULL share; the shortfall sits on the owner line until the
--             student completes.
-- Both need new ledger entry types, hence the CHECK rebuild.
PRAGMA foreign_keys = OFF;
BEGIN;

CREATE TABLE ledger_entry_new (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    month TEXT NOT NULL,
    entry_type TEXT NOT NULL CHECK (
        entry_type IN ('payment_in', 'allocation', 'adjustment', 'reversal',
                       'refund', 'avance')
    ),
    beneficiary_kind TEXT CHECK (beneficiary_kind IN ('venue', 'owner', 'teacher')),
    beneficiary_id INTEGER,
    amount_centimes INTEGER NOT NULL,
    payment_id INTEGER REFERENCES payment(id),
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

-- What the enrollment owed at posting time; cash received so far is the sum
-- of the payment's payment_in lines. NULL = legacy row, fully paid.
ALTER TABLE payment ADD COLUMN due_centimes INTEGER;

-- The « place » where refunds live: promised at class-archive time, settled
-- when the owner hands the cash back.
CREATE TABLE refund (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    enrollment_id INTEGER NOT NULL REFERENCES enrollment(id),
    class_id INTEGER NOT NULL REFERENCES class_group(id),
    student_id INTEGER NOT NULL REFERENCES student(id),
    month TEXT NOT NULL,
    percent_bp INTEGER NOT NULL CHECK (percent_bp BETWEEN 0 AND 10000),
    amount_centimes INTEGER NOT NULL CHECK (amount_centimes >= 0),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'settled')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    settled_at TEXT
);

COMMIT;
PRAGMA foreign_keys = ON;
PRAGMA user_version = 14;
