"""SQLite implementation of the PaymentStore port."""

import sqlite3
from collections.abc import Sequence

from app.domain.adjustments import AdjustmentSpec
from app.domain.money import Centimes
from app.domain.splitting import Beneficiary
from app.ports.payments import (
    AlreadyPaidError,
    AlreadyReversedError,
    ConfiguredAdjustment,
    EnrollmentContext,
    LedgerLine,
    PaymentRecord,
)


class SqlitePaymentStore:
    def __init__(self, connection: sqlite3.Connection):
        self._conn = connection

    def enrollment_context(self, enrollment_id: int) -> EnrollmentContext | None:
        row = self._conn.execute(
            """
            SELECT e.id, e.month, e.price_centimes,
                   s.academy_id, a.venue_bp, a.owner_bp
            FROM enrollment e
            JOIN student s ON s.id = e.student_id
            JOIN academy a ON a.id = s.academy_id
            WHERE e.id = ?
            """,
            (enrollment_id,),
        ).fetchone()
        if row is None:
            return None
        classes = self._enrolled_classes(enrollment_id)
        class_ids = [class_id for class_id, _ in classes]
        return EnrollmentContext(
            enrollment_id=row["id"],
            academy_id=row["academy_id"],
            month=row["month"],
            price=row["price_centimes"],
            venue_id=self._venue_id(row["academy_id"]),
            owner_id=row["academy_id"],
            venue_bp=row["venue_bp"],
            owner_bp=row["owner_bp"],
            subject_teachers=tuple(teacher_id for _, teacher_id in classes),
            adjustments=self._adjustments(enrollment_id, class_ids),
        )

    def record(
        self,
        context: EnrollmentContext,
        net_amount: Centimes,
        lines: Sequence[LedgerLine],
        paid_on: str | None,
    ) -> int:
        try:
            payment_id = self._insert_payment(
                context.enrollment_id, net_amount, paid_on
            )
            self._insert_lines(context.academy_id, context.month, payment_id, lines)
        except sqlite3.IntegrityError as error:
            self._conn.rollback()
            raise AlreadyPaidError(
                f"enrollment {context.enrollment_id} is already paid"
            ) from error
        except Exception:
            self._conn.rollback()
            raise
        self._conn.commit()
        return payment_id

    def payment_record(self, payment_id: int) -> PaymentRecord | None:
        row = self._conn.execute(
            """
            SELECT p.id, p.enrollment_id, p.reversed_at, e.month, s.academy_id
            FROM payment p
            JOIN enrollment e ON e.id = p.enrollment_id
            JOIN student s ON s.id = e.student_id
            WHERE p.id = ?
            """,
            (payment_id,),
        ).fetchone()
        if row is None:
            return None
        return PaymentRecord(
            payment_id=row["id"],
            enrollment_id=row["enrollment_id"],
            academy_id=row["academy_id"],
            month=row["month"],
            reversed=row["reversed_at"] is not None,
            lines=self._payment_lines(payment_id),
        )

    def record_reversal(
        self,
        payment_record: PaymentRecord,
        lines: Sequence[LedgerLine],
        reason: str | None,
    ) -> None:
        try:
            updated = self._conn.execute(
                "UPDATE payment SET reversed_at = datetime('now')"
                " WHERE id = ? AND reversed_at IS NULL",
                (payment_record.payment_id,),
            ).rowcount
            if updated != 1:
                raise AlreadyReversedError(
                    f"payment {payment_record.payment_id} is already reversed"
                )
            self._insert_lines(
                payment_record.academy_id,
                payment_record.month,
                payment_record.payment_id,
                lines,
                note=reason,
            )
        except Exception:
            self._conn.rollback()
            raise
        self._conn.commit()

    def _payment_lines(self, payment_id: int) -> tuple[LedgerLine, ...]:
        rows = self._conn.execute(
            """
            SELECT entry_type, amount_centimes, beneficiary_kind, beneficiary_id,
                   adjustment_id
            FROM ledger_entry
            WHERE payment_id = ? AND entry_type != 'reversal'
            ORDER BY id
            """,
            (payment_id,),
        )
        return tuple(
            LedgerLine(
                entry_type=row["entry_type"],
                amount=row["amount_centimes"],
                beneficiary=(
                    Beneficiary(row["beneficiary_kind"], row["beneficiary_id"])
                    if row["beneficiary_kind"]
                    else None
                ),
                adjustment_id=row["adjustment_id"],
            )
            for row in rows
        )

    def _enrolled_classes(self, enrollment_id: int) -> list[tuple[int, int]]:
        rows = self._conn.execute(
            """
            SELECT ec.class_id, cg.teacher_id
            FROM enrollment_class ec
            JOIN class_group cg ON cg.id = ec.class_id
            WHERE ec.enrollment_id = ?
            ORDER BY ec.class_id
            """,
            (enrollment_id,),
        )
        return [(row["class_id"], row["teacher_id"]) for row in rows]

    def _venue_id(self, academy_id: int) -> int:
        row = self._conn.execute(
            "SELECT id FROM venue WHERE academy_id = ? ORDER BY id LIMIT 1",
            (academy_id,),
        ).fetchone()
        return row["id"]

    def _adjustments(
        self, enrollment_id: int, class_ids: list[int]
    ) -> tuple[ConfiguredAdjustment, ...]:
        rows = self._conn.execute(
            "SELECT id, scope, class_id, kind, value FROM adjustment"
            " WHERE enrollment_id = ?",
            (enrollment_id,),
        ).fetchall()
        return tuple(self._configured(row, class_ids) for row in rows)

    def _configured(
        self, row: sqlite3.Row, class_ids: list[int]
    ) -> ConfiguredAdjustment:
        subject_index = (
            class_ids.index(row["class_id"]) if row["scope"] == "subject" else None
        )
        spec = AdjustmentSpec(
            kind=row["kind"],
            value=row["value"],
            scope=row["scope"],
            subject_index=subject_index,
        )
        bearers, shares_spec = self._bearers(row["id"])
        return ConfiguredAdjustment(
            adjustment_id=row["id"],
            spec=spec,
            bearers=bearers,
            shares_spec=shares_spec,
        )

    def _bearers(
        self, adjustment_id: int
    ) -> tuple[
        tuple[Beneficiary, ...], tuple[tuple[int | None, int | None], ...] | None
    ]:
        rows = self._conn.execute(
            "SELECT bearer_kind, bearer_id, share_centimes, share_bp"
            " FROM adjustment_bearer WHERE adjustment_id = ?",
            (adjustment_id,),
        ).fetchall()
        bearers = tuple(
            Beneficiary(row["bearer_kind"], row["bearer_id"]) for row in rows
        )
        spec = tuple((row["share_centimes"], row["share_bp"]) for row in rows)
        if all(centimes is None and bp is None for centimes, bp in spec):
            return bearers, None
        return bearers, spec

    def _insert_payment(
        self, enrollment_id: int, amount: Centimes, paid_on: str | None
    ) -> int:
        return self._conn.execute(
            "INSERT INTO payment (enrollment_id, amount_centimes, paid_on)"
            " VALUES (?, ?, COALESCE(?, date('now')))",
            (enrollment_id, amount, paid_on),
        ).lastrowid

    def _insert_lines(
        self,
        academy_id: int,
        month: str,
        payment_id: int,
        lines: Sequence[LedgerLine],
        note: str | None = None,
    ) -> None:
        self._conn.executemany(
            "INSERT INTO ledger_entry (academy_id, month, entry_type,"
            " beneficiary_kind, beneficiary_id, amount_centimes, payment_id,"
            " adjustment_id, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    academy_id,
                    month,
                    line.entry_type,
                    line.beneficiary.kind if line.beneficiary else None,
                    line.beneficiary.ref_id if line.beneficiary else None,
                    line.amount,
                    payment_id,
                    line.adjustment_id,
                    note,
                )
                for line in lines
            ],
        )
