"""Fabrique l'icone du bureau — sans dependance, et reproductible.

Pillow n'est pas installe, et l'ajouter pour dessiner un carre serait
cher paye. Un PNG, c'est de l'entete plus des pixels compresses par
zlib ; un .ico, c'est un catalogue de PNG. La bibliotheque standard
suffit.

Le dessin : une toque de diplome claire sur un fond profond. Elle se
lit encore a 16 pixels, la ou un monogramme devient une tache.

    python packaging\\make_icon.py
"""

import struct
import zlib
from pathlib import Path

TAILLES = (256, 128, 64, 48, 32, 16)
SUPER = 4  # on dessine en grand, on reduit : les bords cessent d'etre en escalier

FOND = (28, 42, 38)  # vert profond, calme sur une barre des taches sombre
TOQUE = (167, 229, 211)  # --orb-mint : la meme couleur que dans l'application
OMBRE = (108, 168, 150)


def _polygone(largeur, hauteur, sommets):
    """Les pixels a l'interieur d'un polygone (balayage par lignes)."""
    dedans = set()
    for y in range(hauteur):
        centre = y + 0.5
        bornes = []
        for index in range(len(sommets)):
            x1, y1 = sommets[index]
            x2, y2 = sommets[(index + 1) % len(sommets)]
            if (y1 <= centre < y2) or (y2 <= centre < y1):
                bornes.append(x1 + (centre - y1) * (x2 - x1) / (y2 - y1))
        bornes.sort()
        for paire in range(0, len(bornes) - 1, 2):
            for x in range(int(bornes[paire]), int(bornes[paire + 1]) + 1):
                if 0 <= x < largeur:
                    dedans.add((x, y))
    return dedans


def _dessine(cote):
    """La toque, en grand, sur son fond arrondi."""
    grand = cote * SUPER
    toile = [[(0, 0, 0, 0)] * grand for _ in range(grand)]

    # Fond : carre aux coins arrondis.
    rayon = grand * 0.22
    for y in range(grand):
        for x in range(grand):
            dx = min(x, grand - 1 - x)
            dy = min(y, grand - 1 - y)
            if dx < rayon and dy < rayon:
                loin = ((rayon - dx) ** 2 + (rayon - dy) ** 2) ** 0.5
                if loin > rayon:
                    continue
            toile[y][x] = (*FOND, 255)

    u = grand / 100.0  # une unite = 1 % du cote

    # La planche : un losange vu de face.
    planche = [
        (50 * u, 24 * u),
        (86 * u, 42 * u),
        (50 * u, 60 * u),
        (14 * u, 42 * u),
    ]
    for x, y in _polygone(grand, grand, planche):
        toile[y][x] = (*TOQUE, 255)

    # La calotte, sous la planche.
    calotte = [
        (28 * u, 49 * u),
        (72 * u, 49 * u),
        (72 * u, 64 * u),
        (50 * u, 74 * u),
        (28 * u, 64 * u),
    ]
    for x, y in _polygone(grand, grand, calotte):
        toile[y][x] = (*OMBRE, 255)

    # Le gland : un fil qui tombe a droite.
    fil = [
        (84 * u, 43 * u),
        (87 * u, 43 * u),
        (87 * u, 70 * u),
        (84 * u, 70 * u),
    ]
    for x, y in _polygone(grand, grand, fil):
        toile[y][x] = (*TOQUE, 255)
    pompon = [
        (81 * u, 70 * u),
        (90 * u, 70 * u),
        (90 * u, 80 * u),
        (81 * u, 80 * u),
    ]
    for x, y in _polygone(grand, grand, pompon):
        toile[y][x] = (*TOQUE, 255)

    return _reduis(toile, grand, cote)


def _reduis(toile, grand, cote):
    """Moyenne chaque bloc : c'est la que naissent les bords lisses."""
    petit = [[(0, 0, 0, 0)] * cote for _ in range(cote)]
    for y in range(cote):
        for x in range(cote):
            r = v = b = a = 0
            for dy in range(SUPER):
                for dx in range(SUPER):
                    pr, pv, pb, pa = toile[y * SUPER + dy][x * SUPER + dx]
                    r += pr * pa
                    v += pv * pa
                    b += pb * pa
                    a += pa
            if a == 0:
                petit[y][x] = (0, 0, 0, 0)
            else:
                petit[y][x] = (r // a, v // a, b // a, a // (SUPER * SUPER))
    return petit


def _png(pixels, cote):
    def morceau(nom, contenu):
        corps = nom + contenu
        return (
            struct.pack(">I", len(contenu)) + corps + struct.pack(">I", zlib.crc32(corps))
        )

    brut = b""
    for ligne in pixels:
        brut += b"\x00" + bytes(
            valeur for pixel in ligne for valeur in pixel
        )
    return (
        b"\x89PNG\r\n\x1a\n"
        + morceau(b"IHDR", struct.pack(">IIBBBBB", cote, cote, 8, 6, 0, 0, 0))
        + morceau(b"IDAT", zlib.compress(brut, 9))
        + morceau(b"IEND", b"")
    )


def ecris_ico(destination: Path) -> None:
    """Un .ico : un catalogue, puis les PNG les uns apres les autres."""
    images = [(cote, _png(_dessine(cote), cote)) for cote in TAILLES]
    entete = struct.pack("<HHH", 0, 1, len(images))
    decalage = len(entete) + 16 * len(images)
    catalogue = b""
    for cote, donnees in images:
        catalogue += struct.pack(
            "<BBBBHHII",
            0 if cote >= 256 else cote,
            0 if cote >= 256 else cote,
            0,
            0,
            1,
            32,
            len(donnees),
            decalage,
        )
        decalage += len(donnees)
    destination.write_bytes(
        entete + catalogue + b"".join(donnees for _, donnees in images)
    )


if __name__ == "__main__":
    cible = Path(__file__).parent / "academy.ico"
    ecris_ico(cible)
    print(f"icone ecrite : {cible} ({cible.stat().st_size} octets)")
