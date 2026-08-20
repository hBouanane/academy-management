"""L'année scolaire : une saison bornée, et rien d'autre.

Ici on ne sait ni lire ni écrire : on compte des mois. Savoir quels mois
compose une saison, et à quelle saison appartient un mois, n'a besoin
d'aucune base de données -- et se vérifie donc sans en monter une.
"""

Month = str  # 'YYYY-MM'


def _ordinal(month: Month) -> int:
    """Un mois devient un nombre : décembre et janvier se suivent alors
    d'eux-mêmes, sans qu'on ait à y penser."""
    return int(month[:4]) * 12 + int(month[5:7]) - 1


def _month(ordinal: int) -> Month:
    return f"{ordinal // 12:04d}-{ordinal % 12 + 1:02d}"


def months_between(start: Month, end: Month) -> list[Month]:
    """Tous les mois de la saison, du premier au dernier inclus.

    Une fin posée avant le début ne donne aucun mois plutôt qu'une
    boucle sans terme : une saison vide se voit, un blocage non.
    """
    return [_month(o) for o in range(_ordinal(start), _ordinal(end) + 1)]


def year_holding(years: list[dict], month: Month) -> dict | None:
    """La saison qui contient ce mois — ou aucune.

    L'été n'appartient à personne quand la rentrée s'arrête en juin. Lui
    inventer une saison ferait entrer des recettes dans un bilan qui ne
    les attend pas.
    """
    for year in years:
        if year["start_month"] <= month <= year["end_month"]:
            return year
    return None
