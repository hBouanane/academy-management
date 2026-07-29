"""Scenario builder for read-side tests: real schema, real posting service."""

import sqlite3

from app.adapters.sqlite.seed import seed_default_academy

DH = 100


class Scenario:
    """Builds a populated academy in an open connection, step by step."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.academy_id = seed_default_academy(conn)

    def level_id(self, name: str) -> int:
        return self._one("SELECT id FROM school_level WHERE name = ?", (name,))

    def add_class(self, subject: str, teacher: str, level: str) -> int:
        subject_id = self._insert(
            "INSERT INTO subject (academy_id, name) VALUES (?, ?)",
            (self.academy_id, subject),
        )
        teacher_id = self._insert(
            "INSERT INTO teacher (academy_id, name) VALUES (?, ?)",
            (self.academy_id, teacher),
        )
        return self._insert(
            "INSERT INTO class_group (academy_id, level_id, subject_id, teacher_id)"
            " VALUES (?, ?, ?, ?)",
            (self.academy_id, self.level_id(level), subject_id, teacher_id),
        )

    def add_student(self, name: str, level: str) -> int:
        return self._insert(
            "INSERT INTO student (academy_id, level_id, name) VALUES (?, ?, ?)",
            (self.academy_id, self.level_id(level), name),
        )

    def enroll(
        self, student_id: int, month: str, class_ids: list[int], price_dh: int
    ) -> int:
        package_id = self._insert(
            "INSERT INTO package (academy_id, subject_count, monthly_price_centimes)"
            " VALUES (?, ?, ?)",
            (self.academy_id, len(class_ids), price_dh * DH),
        )
        enrollment_id = self._insert(
            "INSERT INTO enrollment (student_id, package_id, month, price_centimes)"
            " VALUES (?, ?, ?, ?)",
            (student_id, package_id, month, price_dh * DH),
        )
        for class_id in class_ids:
            self.conn.execute(
                "INSERT INTO enrollment_class (enrollment_id, class_id) VALUES (?, ?)",
                (enrollment_id, class_id),
            )
        return enrollment_id

    def add_discount(self, enrollment_id: int, amount_dh: int) -> int:
        return self._insert(
            "INSERT INTO adjustment (enrollment_id, scope, kind, value, category)"
            " VALUES (?, 'package', 'amount', ?, 'discount')",
            (enrollment_id, amount_dh * DH),
        )

    def teacher_id(self, name: str) -> int:
        return self._one("SELECT id FROM teacher WHERE name = ?", (name,))

    def _insert(self, sql: str, params: tuple) -> int:
        return self.conn.execute(sql, params).lastrowid

    def _one(self, sql: str, params: tuple) -> int:
        return self.conn.execute(sql, params).fetchone()[0]
