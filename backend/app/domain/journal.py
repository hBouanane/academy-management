"""What the journal is allowed to remember, and what shape it takes.

The journal exists for one moment: six months later, in front of a family
that disputes a figure. « Le paiement de septembre était sur octobre »
has to stay answerable, and a correction that leaves no trace is worse
than the error it corrects.

Which is why the vocabulary is closed. An open log accepts anything, and
what accepts anything eventually contains everything -- at which point
nobody reads it and the disputed line is unfindable. Only what moves
money, or changes what a month asserts about a student, gets in.
"""

from dataclasses import dataclass

# Le code voyage dans la base et ne change jamais ; le libelle est de
# l'affichage et se reformule sans reecrire l'histoire.
ACTIONS = frozenset(
    {
        # L'argent des familles
        "payment_in",
        "payment_completed",
        "payment_reversed",
        "refund_settled",
        # L'argent qui sort
        "payout",
        "payout_cancelled",
        "guarantee",
        "overpaid_charge",
        "overpaid_charge_cancelled",
        # Ce qu'un mois affirme d'un eleve
        "enrollment",
        "enrollment_deleted",
        "adjustment",
        "adjustment_changed",
        "adjustment_deleted",
        "month_prepared",
        "class_archived",
    }
)

# A qui l'action se rapporte -- ce par quoi on la retrouvera.
SUBJECTS = frozenset({"student", "teacher", "venue", "owner", "class", "month"})


@dataclass(frozen=True)
class Entry:
    """Une ligne du journal. Frozen : une ligne ne se modifie pas.

    subject_label is the name AS IT STOOD when the action happened. A
    student renamed afterwards must not rewrite what was on screen that
    day -- a journal that corrects itself is not a journal.
    """

    action: str
    month: str | None = None
    subject_kind: str | None = None
    subject_id: int | None = None
    subject_label: str | None = None
    amount_centimes: int | None = None
    # Une nuance que seule l'action connait : « jamais venu », le motif
    # d'une contre-passation, le mois d'ou vient une extension.
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.action not in ACTIONS:
            raise ValueError(f"unknown journal action: {self.action}")
        if self.subject_kind is not None and self.subject_kind not in SUBJECTS:
            raise ValueError(f"unknown journal subject: {self.subject_kind}")
