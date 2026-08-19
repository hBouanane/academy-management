"""Les sessions ouvertes — qui a le droit de toucher aux chiffres, là,
maintenant.

Rien n'est écrit sur le disque : fermer l'application referme le verrou,
ce qui est exactement ce qu'on veut. Une session ne survit pas à
l'extinction du poste, et un jeton oublié dans un coin ne rouvrira rien
demain matin.

Le compteur d'échecs vit ici aussi. Un code à quatre chiffres se devine
en une minute si on peut essayer sans fin ; chaque erreur allonge donc
l'attente, et une pause de quelques secondes suffit à rendre le jeu
sans intérêt sans jamais gêner celui qui se trompe une fois.
"""

import secrets
import time
from dataclasses import dataclass, field

# Après tant d'échecs d'affilée, chaque essai attend. La suite monte vite
# mais plafonne : il ne s'agit pas de punir le propriétaire pressé.
_PATIENCE = 3
_DELAYS = (0, 5, 15, 30, 60)


@dataclass
class Sessions:
    """Les jetons vivants, et le souvenir des échecs récents."""

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
        """Ce qu'il reste à patienter avant d'avoir droit à un essai."""
        return max(0, round(self.blocked_until - time.monotonic()))

    def note_failure(self) -> None:
        self.failures += 1
        if self.failures < _PATIENCE:
            return
        step = min(self.failures - _PATIENCE + 1, len(_DELAYS) - 1)
        self.blocked_until = time.monotonic() + _DELAYS[step]
