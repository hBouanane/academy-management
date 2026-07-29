-- Academy Management schema. Money: integer centimes. Percentages: basis points.
-- Nothing is hard-deleted: people carry is_active flags; money lives in an
-- append-only ledger where corrections are new entries, never edits.

CREATE TABLE IF NOT EXISTS academy (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    venue_bp INTEGER NOT NULL DEFAULT 3000 CHECK (venue_bp >= 0),
    owner_bp INTEGER NOT NULL DEFAULT 1000 CHECK (owner_bp >= 0),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    CHECK (venue_bp + owner_bp <= 10000)
);

CREATE TABLE IF NOT EXISTS venue (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS school_level (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    UNIQUE (academy_id, name)
);

CREATE TABLE IF NOT EXISTS subject (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    UNIQUE (academy_id, name)
);

CREATE TABLE IF NOT EXISTS teacher (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    name TEXT NOT NULL,
    phone TEXT,
    is_owner INTEGER NOT NULL DEFAULT 0 CHECK (is_owner IN (0, 1)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- A class: one teacher teaching one subject at one level, optionally scheduled.
-- Default state: a single class per (level, subject). Scaling up = more rows.
CREATE TABLE IF NOT EXISTS class_group (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    level_id INTEGER NOT NULL REFERENCES school_level(id),
    subject_id INTEGER NOT NULL REFERENCES subject(id),
    teacher_id INTEGER NOT NULL REFERENCES teacher(id),
    name TEXT NOT NULL DEFAULT 'A',
    day_of_week INTEGER CHECK (day_of_week BETWEEN 0 AND 6),
    start_time TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    UNIQUE (academy_id, level_id, subject_id, teacher_id, name)
);

CREATE TABLE IF NOT EXISTS student (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    level_id INTEGER NOT NULL REFERENCES school_level(id),
    name TEXT NOT NULL,
    phone TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS package (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    subject_count INTEGER NOT NULL CHECK (subject_count > 0),
    monthly_price_centimes INTEGER NOT NULL CHECK (monthly_price_centimes >= 0),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- One row per student per month; the package can change from month to month.
-- price_centimes snapshots the package price at enrollment time.
CREATE TABLE IF NOT EXISTS enrollment (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES student(id),
    package_id INTEGER NOT NULL REFERENCES package(id),
    month TEXT NOT NULL CHECK (
        month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'
        AND substr(month, 6, 2) BETWEEN '01' AND '12'
    ),
    price_centimes INTEGER NOT NULL CHECK (price_centimes >= 0),
    UNIQUE (student_id, month)
);

CREATE TABLE IF NOT EXISTS enrollment_class (
    enrollment_id INTEGER NOT NULL REFERENCES enrollment(id),
    class_id INTEGER NOT NULL REFERENCES class_group(id),
    PRIMARY KEY (enrollment_id, class_id)
);

-- Discounts, coupons and gifts are one mechanism. Bearers listed separately;
-- default upstream policy is a single 'owner' bearer.
CREATE TABLE IF NOT EXISTS adjustment (
    id INTEGER PRIMARY KEY,
    enrollment_id INTEGER NOT NULL REFERENCES enrollment(id),
    scope TEXT NOT NULL CHECK (scope IN ('package', 'subject')),
    class_id INTEGER REFERENCES class_group(id),
    kind TEXT NOT NULL CHECK (kind IN ('percent', 'amount')),
    value INTEGER NOT NULL CHECK (value >= 0),
    category TEXT NOT NULL CHECK (category IN ('discount', 'coupon', 'gift')),
    reason TEXT,
    CHECK (scope != 'subject' OR class_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS adjustment_bearer (
    adjustment_id INTEGER NOT NULL REFERENCES adjustment(id),
    bearer_kind TEXT NOT NULL CHECK (bearer_kind IN ('venue', 'owner', 'teacher')),
    bearer_id INTEGER NOT NULL,
    PRIMARY KEY (adjustment_id, bearer_kind, bearer_id)
);

CREATE TABLE IF NOT EXISTS payment (
    id INTEGER PRIMARY KEY,
    enrollment_id INTEGER NOT NULL UNIQUE REFERENCES enrollment(id),
    amount_centimes INTEGER NOT NULL CHECK (amount_centimes >= 0),
    paid_on TEXT NOT NULL DEFAULT (date('now'))
);

-- Append-only. Totals anywhere in the app are SUM() over these rows.
CREATE TABLE IF NOT EXISTS ledger_entry (
    id INTEGER PRIMARY KEY,
    academy_id INTEGER NOT NULL REFERENCES academy(id),
    month TEXT NOT NULL,
    entry_type TEXT NOT NULL CHECK (
        entry_type IN ('payment_in', 'allocation', 'adjustment', 'reversal')
    ),
    beneficiary_kind TEXT CHECK (beneficiary_kind IN ('venue', 'owner', 'teacher')),
    beneficiary_id INTEGER,
    amount_centimes INTEGER NOT NULL,
    payment_id INTEGER REFERENCES payment(id),
    adjustment_id INTEGER REFERENCES adjustment(id),
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ledger_month ON ledger_entry (academy_id, month);
CREATE INDEX IF NOT EXISTS idx_ledger_beneficiary
    ON ledger_entry (beneficiary_kind, beneficiary_id, month);
CREATE INDEX IF NOT EXISTS idx_enrollment_month ON enrollment (month);
CREATE INDEX IF NOT EXISTS idx_student_academy ON student (academy_id, is_active);
