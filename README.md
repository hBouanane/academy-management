# Academy Management

An offline Windows desktop application for a private tutoring academy: it
enrols students, takes payments, splits each payment between the room, the
academy and the teachers, chases what is still owed, and files the month's
paperwork by itself.

It runs on one laptop, with no server, no internet and no IT support. The
owner is the only user, and the numbers on screen are the ones he pays people
with — so the interesting problem here is not storage, it is **being right**.

```
490 backend tests · 26 schema migrations
8 400 lines of application Python · 7 700 of tests · 14 600 of TypeScript
```

---

## Why this is not a CRUD app

A CRUD application lets you update a row. This one cannot.

Money is written to an **append-only ledger**. A month that has been settled
is never recalculated: if a correction is needed, it arrives as a *new* entry
— a reversal, a refund, an advance and its cancellation — so that the history
of what was actually paid to whom, on what day, survives intact. A payslip
that a teacher signed must never be contradicted by a later regeneration.

That single decision drives most of the design, and most of the hard bugs.
Three real examples from the log:

- An advance paid to a teacher before the family had paid was recorded
  against the *enrolment*, while its cancellation was recorded against the
  *payment*. One view could see it, another could not, and the same teacher's
  earnings differed by 145,16 DH between two lines of the same page.
- "Unpaid month" meant three different things in three screens, so a family
  who had paid 100 of 300 DH appeared simultaneously in debt and in good
  standing.
- A document banner asked the owner to regenerate a file that the automatic
  filing had explicitly decided never to touch — a request that could never
  be satisfied by waiting.

None of these are storage bugs. They are modelling bugs: quantities in this
domain have more than one defensible meaning, and each screen has to commit
to one.

---

## Architecture

### Hexagonal — genuinely, at the core

```
app/
  domain/      pure rules. no I/O, no SQL, no framework      (482 lines)
  ports/       the contract the domain expects of storage
  services/    orchestration: use cases built from domain    (1 054 lines)
  adapters/    sqlite · fastapi · docx · excel               (6 708 lines)
```

`app/domain` imports **nothing but the standard library** — `dataclasses`,
`hashlib`, `hmac`, `secrets` — and its own modules. No `sqlite3`, no FastAPI,
no filesystem. The money engine can be exercised, and is, without a database
existing at all:

```python
allocations = split_payment(300_00, policy, venue_id=1, owner_id=1,
                            subject_teachers=[7, 7, 9])
assert sum(a.amount for a in allocations) == 300_00
```

`app/ports/payments.py` states, as a `Protocol`, what the payment service
needs from whatever stores the data, along with the errors that contract can
raise (`UnknownEnrollmentError`, `AlreadyPaidError`, `AlreadyReversedError`).
`SqlitePaymentStore` implements it.

**Where it bends, honestly.** Only the payment path is formalised behind a
port. The rest of the API layer talks to `adapters/sqlite/crud.py` directly
rather than through an interface, and one service (`school_years`) imports a
read-model from the sqlite adapter instead of receiving it. Those are
pragmatic shortcuts, not a second architecture — but calling the whole
codebase "hexagonal" without qualification would overstate it. The rule that
is actually enforced everywhere is the one that matters: **the domain never
learns where the data lives.**

### DDD — the useful parts, not the ceremony

Present:

- **Value objects and a ubiquitous language.** `Centimes`, `Allocation`,
  `Beneficiary`, `SplitPolicy`, `AdjustmentSpec`. Money is never a float;
  percentages are integer basis points (`10 000 = 100 %`).
- **Invariants living in the domain**, not in validation sprinkled over
  handlers.
- **CQRS-shaped reads.** `adapters/sqlite/reports.py` only ever sums existing
  ledger entries; it never recomputes money. The write side posts entries; the
  read side adds them up.

Absent, deliberately: no aggregate roots, no repository abstraction over every
table, no domain events. For one owner on one laptop, that ceremony would buy
nothing and cost clarity.

---

## The invariants

These are the rules the test suite defends. Each one exists because breaking
it costs the owner money or trust.

| # | Invariant | Why |
|---|---|---|
| 1 | Money is **integer centimes**, never a float | A rounding drift in a currency is a permanent, invisible loss |
| 2 | Allocations of a payment **sum exactly** to the payment | Largest-remainder distribution; the flooring loss is handed to the largest remainders, so no centime ever disappears |
| 3 | The ledger is **append-only**; a settled month is never recomputed | The past is what actually happened; corrections are new entries |
| 4 | A **payslip is a receipt** and is never regenerated | A second sheet would contradict the one the teacher signed |
| 5 | A past month is **still owed while anything remains on it** | A family paying 100 of 300 is not in good standing |
| 6 | The **same rule lives in exactly one place** | Three copies of "is this month owed?" had already drifted into three different answers |
| 7 | **Debt follows the student** across a school year boundary | Money owed does not vanish because the calendar turned |
| 8 | **Archiving is not deleting** | A student who returns finds his whole history |
| 9 | A database is **never opened by an older binary** | It would silently misread columns it does not know |
| 10 | Documents already asked for **stay current**; nothing is created unasked | The owner should not have to remember on the app's behalf |

Invariant 6 is the one that produced the most bugs before it was named. The
canonical formulation of "what is still owed" now exists once, in
`payment_remaining`, with the SQL predicate `_still_owed` documented as its
twin so the two cannot drift apart unnoticed.

---

## The rules the owner controls

**Split precedence.** Every payment is divided between the room, the academy
and the teachers. Several rules could apply at once, so the most specific one
wins, in a fixed and visible order:

```
class → teacher → filière → level → academy default
```

**Proration.** A student arriving mid-month pays a configurable share — the
month is cut into equal slices, and he pays the slice he arrived in.

**School year.** A season runs from a chosen first month to a chosen last
month, because a Moroccan academy ends its year in June or July depending on
the school. Closing one archives the students — nothing presumes they will
return — while their debts follow them into the next.

---

## Money, end to end

```
enrolment  →  price  →  adjustments (discounts, gifts, coupons)
                             ↓
                        net price
                             ↓
        split_payment  →  allocations (room · academy · teachers)
                             ↓
                    ledger entries, append-only
                             ↓
         reports · arrears · payslips · Excel export
```

Every arrow is covered by tests. The step that has caused the most trouble is
the one that looks least interesting: attributing an entry to a class when the
entry has no payment attached to it.

---

## Testing

490 backend tests, written first. They read as specifications rather than
coverage:

```python
def test_a_month_half_paid_owes_the_rest(self, client): ...
def test_what_the_family_owes_survives_the_closing(self, client): ...
def test_a_receipt_is_never_aged_by_anything(self, client): ...
def test_the_refusal_never_tells_him_to_go_back(self, client): ...
```

The last one is worth explaining. A guard refused to open a database written
by a newer version — correct — but advised restoring an older backup. Applied
to a live database that is merely ahead of the app, that advice destroys every
entry made since. The test now forbids the message from ever suggesting it.

---

## Schema migrations

26 numbered SQL migrations, applied in order on startup against SQLite's
`PRAGMA user_version`. There is no operator on the other end, so the app has
to upgrade itself across an arbitrary gap and refuse the one dangerous
direction.

Verified on real databases rather than asserted:

| starting schema | after launch | data |
|---|---|---|
| 10 (sixteen migrations behind) | 26 | intact |
| 23, carrying 2 450,80 DH over 139 ledger entries | 26 | every figure identical |

The reverse — an older binary meeting a newer database — is refused at
startup with an explanation, never with a silent failure.

---

## Stack

- **Frontend:** React 19 · Vite · Tailwind v4 · shadcn/ui
- **Backend:** FastAPI · SQLite (`sqlite3`, no ORM)
- **Documents:** openpyxl (Excel), python-docx (absence sheets, payslips)
- **Desktop shell:** pywebview
- **Packaging:** PyInstaller (`--onedir`) + Inno Setup → a signed-less but
  self-contained Windows installer

In production one Python process runs uvicorn on `127.0.0.1`, serves the API
under `/api` and the built React app as static files, and opens a native
window. No Node, no CORS, no network. In development, Vite proxies `/api` to
FastAPI for hot reload.

---

## Running it

```bash
# backend tests
cd backend && python -m pytest -q

# development (API on :8000, UI on :5173)
python backend/dev.py
npm --prefix frontend run dev

# build the distributable and the installer
powershell -File packaging/build.ps1
powershell -File packaging/installer.ps1
```

The application stores its database in `%APPDATA%\AcademyManagement\`, takes
a snapshot when it closes if anything changed, and keeps roughly a month of
them.

---

## A note on language

The user interface, message templates and generated documents are in
**French**: the client is a Moroccan academy owner and that is the language he
works in. Code comments and commit messages are in English. Older comments
from the middle of the project are still French and are being translated.
