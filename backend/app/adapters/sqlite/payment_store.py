"""SQLite implementation of the PaymentStore port."""

import sqlite3
from collections.abc import Sequence

from app.domain.adjustments import AdjustmentSpec
from app.domain.money import Centimes
from app.domain.splitting import Beneficiary
from app.ports.payments import (
    AlreadyPaidError,
    ConfiguredAdjustment,
    EnrollmentContext,
    LedgerLine,
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
            self._insert_lines(context, payment_id, lines)
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
        return ConfiguredAdjustment(
            adjustment_id=row["id"], spec=spec, bearers=self._bearers(row["id"])
        )

    def _bearers(self, adjustment_id: int) -> tuple[Beneficiary, ...]:
        rows = self._conn.execute(
            "SELECT bearer_kind, bearer_id FROM adjustment_bearer"
            " WHERE adjustment_id = ?",
            (adjustment_id,),
        )
        return tuple(Beneficiary(row["bearer_kind"], row["bearer_id"]) for row in rows)

    def _insert_payment(
        self, enrollment_id: int, amount: Centimes, paid_on: str | None
    ) -> int:
        return self._conn.execute(
            "INSERT INTO payment (enrollment_id, amount_centimes, paid_on)"
            " VALUES (?, ?, COALESCE(?, date('now')))",
            (enrollment_id, amount, paid_on),
        ).lastrowid

    def _insert_lines(
        self, context: EnrollmentContext, payment_id: int, lines: Sequence[LedgerLine]
    ) -> None:
        self._conn.executemany(
            "INSERT INTO ledger_entry (academy_id, month, entry_type,"
            " beneficiary_kind, beneficiary_id, amount_centimes, payment_id,"
            " adjustment_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    context.academy_id,
                    context.month,
                    line.entry_type,
                    line.beneficiary.kind if line.beneficiary else None,
                    line.beneficiary.ref_id if line.beneficiary else None,
                    line.amount,
                    payment_id,
                    line.adjustment_id,
                )
                for line in lines
            ],
        )
