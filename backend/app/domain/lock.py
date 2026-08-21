"""The lock: what keeps the figures safe from a passing hand.

No database and no network here — only the rule. A code is never kept as
it was typed: we keep enough to recognise it, not enough to read it
back. And since the application lives offline, nobody can reset anything
remotely: the recovery phrase is the only way back in, which is why care
was taken to make it writable by hand.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass

# scrypt rather than a plain SHA: a four-digit code is guessed in a
# second when the computation is fast. These parameters cost a fraction
# of a second on opening, and years to anyone trying every combination.
_COST = 2**14
_BLOCK_SIZE = 8
_PARALLELISM = 1
_KEY_LENGTH = 32

# Short words, no accents, no spelling traps: the phrase gets copied
# onto a scrap of paper, then typed back months later. They stay French
# -- the owner is the one writing them down.
_WORDS = (
    "arbre",
    "bateau",
    "bougie",
    "branche",
    "cahier",
    "canard",
    "chaise",
    "chemin",
    "cheval",
    "cle",
    "coquille",
    "couteau",
    "craie",
    "cuivre",
    "ecole",
    "encre",
    "etoile",
    "falaise",
    "fenetre",
    "feuille",
    "figue",
    "fleuve",
    "fourmi",
    "fraise",
    "fusain",
    "gateau",
    "grenier",
    "guitare",
    "hibou",
    "horloge",
    "jardin",
    "lampe",
    "lavande",
    "lezard",
    "lumiere",
    "marbre",
    "miroir",
    "montagne",
    "moulin",
    "navire",
    "nuage",
    "olive",
    "orange",
    "ortie",
    "panier",
    "papier",
    "pierre",
    "pigeon",
    "plume",
    "poivre",
    "pomme",
    "pont",
    "prairie",
    "rivage",
    "roseau",
    "sable",
    "sapin",
    "sentier",
    "soleil",
    "sucre",
    "table",
    "tapis",
    "theiere",
    "tortue",
    "tulipe",
    "vague",
    "velours",
    "verger",
    "violon",
    "voile",
)


@dataclass(frozen=True)
class Secret:
    """What we keep of a code: enough to recognise it, nothing more."""

    salt: str
    digest: str


def seal(code: str) -> Secret:
    """Seal a code -- each sealing draws its own salt, so that two
    academies sharing a code do not look alike."""
    salt = secrets.token_hex(16)
    return Secret(salt=salt, digest=_digest(code, salt))


def matches(code: str, secret: Secret) -> bool:
    """Constant-time comparison: otherwise how long the answer takes
    would betray how many characters are already right."""
    return hmac.compare_digest(_digest(code, secret.salt), secret.digest)


def recovery_phrase(words: int = 4) -> str:
    """The spare wheel, drawn once and never shown again.

    Four words and a number: enough that nobody guesses it, few enough to
    fit on a single handwritten line.
    """
    chosen = [secrets.choice(_WORDS) for _ in range(words)]
    return "-".join([*chosen, str(secrets.randbelow(90) + 10)])


def _digest(code: str, salt: str) -> str:
    return hashlib.scrypt(
        code.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=_COST,
        r=_BLOCK_SIZE,
        p=_PARALLELISM,
        dklen=_KEY_LENGTH,
    ).hex()
