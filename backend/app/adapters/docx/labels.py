"""The labels printed on documents handed over in person.

They must say exactly what the screen says: « 1ère année » and not
« 1ème », and at Lycée « Tronc commun / 1ère Bac / 2ème Bac » rather than
a year number nobody uses.
"""

MONTHS_FR = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)

_LYCEE = {1: "Tronc commun", 2: "1ère Bac", 3: "2ème Bac"}


def month_label(month: str) -> str:
    return f"{MONTHS_FR[int(month[5:7]) - 1]} {month[:4]}"


def annee_label(level_name: str, annee: int | None) -> str | None:
    if annee is None:
        return None
    if level_name == "Lycée":
        return _LYCEE.get(annee, f"{annee}ème année")
    return "1ère année" if annee == 1 else f"{annee}ème année"


def segment_label(row) -> str:
    """Level, année, parcours, filière -- in that order, empties dropped."""
    parts = [row["level_name"]]
    annee = annee_label(row["level_name"], row["annee"])
    if annee:
        parts.append(annee)
    if row["parcours"]:
        parts.append(row["parcours"])
    if row["filiere"]:
        parts.append(row["filiere"])
    return " · ".join(parts)
