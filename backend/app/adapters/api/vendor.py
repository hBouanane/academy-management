"""La porte de l'éditeur — le dernier recours, et rien de plus.

Le propriétaire peut tout perdre : son code, et la phrase notée sur
papier. Hors ligne, plus personne ne peut rien pour lui — sauf celui
qui a écrit le logiciel. D'où cette porte : l'application affiche un
défi, l'éditeur le signe avec sa clé privée, et renvoie la signature.

Ce qui voyage dans la version livrée n'est que la clé PUBLIQUE. Elle
sait vérifier une signature ; elle ne sait pas en produire. L'extraire
de l'exécutable ne donne donc aucun pouvoir — c'est toute la différence
avec un secret partagé, qui ouvrirait toutes les installations dès
qu'on saurait le lire.

Le prix est la longueur : une signature fait quatre-vingt-huit
caractères, à envoyer par message plutôt qu'à dicter au téléphone.

Trois autres choses la rendent supportable :

  - elle n'existe QUE si une clé publique a été déposée dans la version
    livrée ; sans elle, ni bouton ni route ;
  - le défi part de l'installation ET du jour : la signature d'hier ne
    vaut plus rien, et dépanner une académie n'ouvre pas l'autre ;
  - dépanner ne prive pas le propriétaire de sa propre porte : il
    repart avec une phrase de secours neuve.
"""

import base64
import hashlib
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_KEY_FILE = "vendor_key.txt"


def vendor_key() -> str | None:
    """La clé publique de l'éditeur, si cette version en porte une.

    Elle n'est jamais dans le dépôt : elle est déposée au moment de la
    construction, et une version sans clé n'a tout simplement pas de
    porte de dépannage.
    """
    from_env = os.environ.get("ACADEMY_VENDOR_KEY")
    if from_env:
        return from_env.strip()
    for folder in _key_folders():
        candidate = folder / _KEY_FILE
        if candidate.is_file():
            content = candidate.read_text(encoding="utf-8").strip()
            if content:
                return content
    return None


def _key_folders() -> list[Path]:
    """Où chercher la clé : à côté du programme livré d'abord, puis dans
    packaging/ pour le développement — là où l'éditeur la garde."""
    here = Path(__file__).resolve()
    folders = [here.parents[3], here.parents[4] / "packaging"]
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        folders.insert(0, Path(bundled))
    return folders


def today_stamp() -> str:
    """Le jour, en clair. Il fait tourner le défi : la signature envoyée
    hier ne rouvre rien aujourd'hui."""
    return datetime.now(UTC).strftime("%Y%m%d")


def challenge_for(installation_id: str) -> str:
    """Le défi affiché : court, recopiable, propre à cette installation
    et à ce jour."""
    material = f"{installation_id}:{today_stamp()}"
    digest = hashlib.sha256(material.encode()).hexdigest().upper()
    return f"{digest[:4]}-{digest[4:8]}-{digest[8:12]}"


def answer_matches(public_key_pem: str, challenge: str, given: str) -> bool:
    """La signature répond-elle bien à CE défi ?

    Indulgente sur la forme : la réponse voyage par message et arrive
    souvent avec un retour à la ligne ou une espace collée.
    """
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode())
        if not isinstance(key, Ed25519PublicKey):
            return False
        signature = base64.b64decode(_plain(given), validate=True)
        key.verify(signature, challenge.encode())
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def public_key_text(public_key: Ed25519PublicKey) -> str:
    """La clé publique telle qu'elle est déposée dans la version livrée."""
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def _plain(text: str) -> str:
    return "".join(text.split())
