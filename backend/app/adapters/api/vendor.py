"""La porte de l'éditeur — le dernier recours, et rien de plus.

Le propriétaire peut tout perdre : son code, et la phrase notée sur
papier. Hors ligne, plus personne ne peut rien pour lui — sauf celui
qui a écrit le logiciel. D'où cette porte, qui ne s'ouvre qu'au
téléphone : l'application affiche un défi, l'éditeur calcule la réponse
avec sa clé, et la dicte.

Trois choses la rendent supportable :

  - elle n'existe QUE si une clé a été déposée dans la version livrée ;
    sans clé, ni bouton ni route ;
  - le défi part de l'installation ET du jour : la réponse d'hier ne
    vaut plus rien, et dépanner une académie ne donne pas la clé d'une
    autre ;
  - dépanner ne prive pas le propriétaire de sa propre porte : il
    repart avec une phrase de secours neuve.

Ce qu'il faut savoir et dire : la clé voyage dans l'exécutable livré.
Qui saurait la lire pourrait ouvrir n'importe quelle installation.
C'est le prix d'une réponse de huit caractères, dictable au téléphone ;
une signature serait inviolable mais ferait cent caractères à recopier.
"""

import hashlib
import hmac
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_KEY_FILE = "vendor_key.txt"


def vendor_key() -> str | None:
    """La clé de l'éditeur, si cette version en porte une.

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
    """Le jour, en clair. Il fait tourner le défi : la réponse dictée
    hier ne rouvre rien aujourd'hui."""
    return datetime.now(UTC).strftime("%Y%m%d")


def challenge_for(installation_id: str) -> str:
    """Le défi affiché : court, lisible à voix haute, propre à cette
    installation et à ce jour."""
    material = f"{installation_id}:{today_stamp()}"
    digest = hashlib.sha256(material.encode()).hexdigest().upper()
    return f"{digest[:4]}-{digest[4:8]}-{digest[8:12]}"


def answer_for(key: str, challenge: str) -> str:
    """Ce que l'éditeur calcule de son côté."""
    digest = hmac.new(key.encode(), challenge.encode(), hashlib.sha256).hexdigest()
    return f"{digest[:4].upper()}-{digest[4:8].upper()}"


def answer_matches(key: str, challenge: str, given: str) -> bool:
    """Comparaison à temps constant, et indulgente sur la forme : la
    réponse est dictée au téléphone, elle doit passer telle qu'on
    l'entend."""
    return hmac.compare_digest(_plain(answer_for(key, challenge)), _plain(given))


def _plain(text: str) -> str:
    return "".join(character for character in text if character.isalnum()).upper()
