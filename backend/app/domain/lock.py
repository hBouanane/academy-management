"""Le verrou : ce qui protège les chiffres d'une main de passage.

Ici, aucune base et aucun réseau — seulement la règle. Un code n'est
jamais gardé tel qu'il a été tapé : on garde de quoi le reconnaître, pas
de quoi le relire. Et comme l'application vit hors ligne, personne ne
peut réinitialiser quoi que ce soit à distance : la phrase de secours
est la seule porte de sortie, d'où le soin mis à la rendre notable à la
main.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass

# scrypt plutôt qu'un simple SHA : un code à quatre chiffres se devine en
# une seconde si le calcul est rapide. Ces paramètres coûtent une
# fraction de seconde à l'ouverture, et des années à qui essaierait tout.
_COST = 2**14
_BLOCK_SIZE = 8
_PARALLELISM = 1
_KEY_LENGTH = 32

# Des mots courts, sans accent ni piège d'orthographe : la phrase se
# recopie sur un bout de papier, puis se retape des mois plus tard.
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
    """Ce qu'on garde d'un code : de quoi le reconnaître, rien de plus."""

    salt: str
    digest: str


def seal(code: str) -> Secret:
    """Sceller un code — chaque scellement tire son propre sel, pour que
    deux académies au même code ne se ressemblent pas."""
    salt = secrets.token_hex(16)
    return Secret(salt=salt, digest=_digest(code, salt))


def matches(code: str, secret: Secret) -> bool:
    """Comparaison à temps constant : sinon la durée de la réponse
    trahirait combien de caractères sont déjà justes."""
    return hmac.compare_digest(_digest(code, secret.salt), secret.digest)


def recovery_phrase(words: int = 4) -> str:
    """La roue de secours, tirée une seule fois et jamais réaffichée.

    Quatre mots et un nombre : assez pour que personne ne la devine,
    assez peu pour tenir sur une ligne écrite à la main.
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
