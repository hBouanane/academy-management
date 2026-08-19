"""Calculer la réponse à un défi de dépannage. À GARDER POUR VOUS.

Votre client a perdu son code ET la phrase notée sur papier. Il vous
appelle. Sur son écran, sous « Code oublié ? », il choisit « Dépannage
par l'éditeur » et vous lit le défi affiché. Vous lancez :

    python backend\\tools\\reponse_editeur.py A1B2-C3D4-E5F6

Vous lui dictez les huit caractères obtenus ; il choisit un nouveau code
et repart avec une phrase de secours neuve.

La clé se lit dans packaging\\vendor_key.txt (jamais dans le dépôt) ou
dans la variable ACADEMY_VENDOR_KEY. Le défi change chaque jour : la
réponse d'hier ne rouvre rien aujourd'hui.

Pour créer la clé une bonne fois :

    python -c "import secrets; print(secrets.token_hex(32))" > packaging\\vendor_key.txt

Ce fichier part dans la version livrée. Gardez-en une copie ailleurs :
sans lui, vous ne pourrez plus dépanner les installations déjà posées.
"""

import hashlib
import hmac
import os
import sys
from pathlib import Path

KEY_FILE = Path(__file__).resolve().parents[2] / "packaging" / "vendor_key.txt"


def key() -> str:
    from_env = os.environ.get("ACADEMY_VENDOR_KEY")
    if from_env:
        return from_env.strip()
    if not KEY_FILE.is_file():
        raise SystemExit(
            f"Aucune clé : ni ACADEMY_VENDOR_KEY, ni {KEY_FILE}.\n"
            "Créez-la avec :\n"
            '  python -c "import secrets; print(secrets.token_hex(32))"'
            f" > {KEY_FILE}"
        )
    return KEY_FILE.read_text(encoding="utf-8").strip()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage : reponse_editeur.py <défi affiché à l'écran>")
    challenge = sys.argv[1].strip()
    digest = hmac.new(key().encode(), challenge.encode(), hashlib.sha256).hexdigest()
    print(f"{digest[:4].upper()}-{digest[4:8].upper()}")


if __name__ == "__main__":
    main()
