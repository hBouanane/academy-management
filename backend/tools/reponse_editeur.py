"""Signer un défi de dépannage. VOTRE CLÉ PRIVÉE NE DOIT JAMAIS SORTIR D'ICI.

Votre client a perdu son code ET la phrase notée sur papier. Il vous
appelle. Sur son écran, sous « Code oublié ? », il choisit « Dépannage
par l'éditeur » et vous envoie le défi affiché. Vous lancez :

    python backend\\tools\\reponse_editeur.py A1B2-C3D4-E5F6

Vous lui envoyez la réponse (elle est longue : par message, pas au
téléphone). Il la colle, choisit un nouveau code, et repart avec une
phrase de secours neuve.

Pour créer la paire, une bonne fois :

    python backend\\tools\\reponse_editeur.py --nouvelle-paire

Deux fichiers apparaissent dans packaging\\ :

  vendor_private.pem  votre clé PRIVÉE. Elle ne quitte jamais ce poste.
                      Sauvegardez-la ailleurs : sans elle, plus aucune
                      installation déjà livrée ne peut être dépannée.
  vendor_key.txt      la clé PUBLIQUE. Elle part dans la version livrée.
                      Elle ne sait que vérifier, jamais signer — la
                      retrouver dans l'exécutable ne donne aucun pouvoir.

Le défi change chaque jour : la signature d'hier ne rouvre rien.
"""

import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PACKAGING = Path(__file__).resolve().parents[2] / "packaging"
PRIVATE_FILE = PACKAGING / "vendor_private.pem"
PUBLIC_FILE = PACKAGING / "vendor_key.txt"


def make_pair() -> None:
    if PRIVATE_FILE.exists():
        raise SystemExit(
            f"{PRIVATE_FILE} existe déjà. La remplacer rendrait impossible le"
            " dépannage de toutes les installations déjà livrées.\n"
            "Supprimez-la vous-même si c'est vraiment ce que vous voulez."
        )
    PACKAGING.mkdir(parents=True, exist_ok=True)
    private = Ed25519PrivateKey.generate()
    PRIVATE_FILE.write_bytes(
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    PUBLIC_FILE.write_bytes(
        private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    print(f"Clé privée : {PRIVATE_FILE}  (à garder, à sauvegarder ailleurs)")
    print(f"Clé publique : {PUBLIC_FILE}  (part dans la version livrée)")


def sign(challenge: str) -> str:
    if not PRIVATE_FILE.is_file():
        raise SystemExit(
            f"Aucune clé privée dans {PRIVATE_FILE}.\n"
            "Créez la paire avec : reponse_editeur.py --nouvelle-paire"
        )
    private = serialization.load_pem_private_key(
        PRIVATE_FILE.read_bytes(), password=None
    )
    return base64.b64encode(private.sign(challenge.encode())).decode()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage :\n"
            "  reponse_editeur.py <défi affiché à l'écran>\n"
            "  reponse_editeur.py --nouvelle-paire"
        )
    argument = sys.argv[1].strip()
    if argument == "--nouvelle-paire":
        make_pair()
        return
    print(sign(argument))


if __name__ == "__main__":
    main()
