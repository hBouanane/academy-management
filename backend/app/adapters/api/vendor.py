"""The vendor's door -- the last resort, and nothing more.

The owner can lose everything: his code, and the phrase written on
paper. Offline, nobody can help him -- except whoever wrote the
software. Hence this door: the application shows a challenge, the vendor
signs it with his private key, and sends the signature back.

What ships inside the delivered build is only the PUBLIC key. It can
verify a signature; it cannot produce one. Extracting it from the
executable therefore grants no power -- which is the whole difference
from a shared secret, which would open every installation the moment
someone could read it.

The price is length: a signature is eighty-eight characters, to be sent
by message rather than dictated over the phone.

Three further things make it bearable:

  - it exists ONLY if a public key was placed in the delivered build;
    without one, there is neither button nor route;
  - the challenge derives from the installation AND the day: yesterday's
    signature is worthless, and rescuing one academy does not open
    another;
  - rescuing does not deprive the owner of his own door: he leaves with
    a fresh recovery phrase.
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
    """The vendor's public key, if this build carries one.

    It is never in the repository: it is placed at build time, and a
    build without a key simply has no rescue door.
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
    """Where to look for the key: next to the delivered program first,
    then in packaging/ for development -- where the vendor keeps it."""
    here = Path(__file__).resolve()
    folders = [here.parents[3], here.parents[4] / "packaging"]
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        folders.insert(0, Path(bundled))
    return folders


def today_stamp() -> str:
    """The day, in plain text. It rotates the challenge: a signature sent
    yesterday reopens nothing today."""
    return datetime.now(UTC).strftime("%Y%m%d")


def challenge_for(installation_id: str) -> str:
    """The challenge shown: short, copyable, specific to this
    installation and this day."""
    material = f"{installation_id}:{today_stamp()}"
    digest = hashlib.sha256(material.encode()).hexdigest().upper()
    return f"{digest[:4]}-{digest[4:8]}-{digest[8:12]}"


def answer_matches(public_key_pem: str, challenge: str, given: str) -> bool:
    """Does this signature actually answer THIS challenge?

    Lenient about shape: the answer travels by message and often arrives
    with a line break or a stray space attached.
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
    """The public key exactly as placed in the delivered build."""
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def _plain(text: str) -> str:
    return "".join(text.split())
