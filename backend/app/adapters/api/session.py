"""Open sessions -- who may touch the figures, right now.

Nothing is written to disk: closing the application closes the lock,
which is exactly what we want. A session does not survive the machine
being switched off, and a token forgotten in a corner will reopen
nothing tomorrow morning.

The failure counter lives here too. A four-digit code is guessed in a
minute if attempts are unlimited; each mistake therefore lengthens the
wait, and a pause of a few seconds is enough to make the game pointless
without ever hindering someone who mistypes once.
"""

import secrets
import time
from dataclasses import dataclass, field

# After so many failures in a row, every attempt waits. The sequence
# climbs fast but plateaus: the point is not to punish an owner in a
# hurry.
_PATIENCE = 3
_DELAYS = (0, 5, 15, 30, 60)


@dataclass
class Sessions:
    """The live tokens, and the memory of recent failures."""

    tokens: set[str] = field(default_factory=set)
    failures: int = 0
    blocked_until: float = 0.0

    def open(self) -> str:
        token = secrets.token_urlsafe(24)
        self.tokens.add(token)
        self.failures = 0
        self.blocked_until = 0.0
        return token

    def holds(self, token: str | None) -> bool:
        return token is not None and token in self.tokens

    def close_all(self) -> None:
        """Verrouiller : tous les jetons meurent, y compris celui de
        l'onglet qui vient de le demander."""
        self.tokens.clear()

    def seconds_to_wait(self) -> int:
        """How long remains before another attempt is allowed."""
        return max(0, round(self.blocked_until - time.monotonic()))

    def note_failure(self) -> None:
        self.failures += 1
        if self.failures < _PATIENCE:
            return
        step = min(self.failures - _PATIENCE + 1, len(_DELAYS) - 1)
        self.blocked_until = time.monotonic() + _DELAYS[step]
