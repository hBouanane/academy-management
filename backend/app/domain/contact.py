"""Joindre une famille : la règle, sans le réseau.

Un numéro se note comme on le dit — « 06 61 23 45 67 » — et WhatsApp,
lui, ne connaît que la forme internationale, sans espace ni zéro
national. La conversion appartient ici : c'est une règle, pas une
technique.
"""

# L'académie est marocaine ; un numéro noté « 06… » est marocain. Un
# numéro déjà international garde le sien, quel qu'il soit.
DEFAULT_COUNTRY = "212"


def whatsapp_number(raw: str, country: str = DEFAULT_COUNTRY) -> str | None:
    """La forme que WhatsApp attend, ou rien si ce n'en est pas un.

    Rien vaut mieux qu'un numéro inventé : une fiche porte parfois « à
    demander » ou « chez la voisine », et il faut le voir plutôt que
    d'écrire à un inconnu.
    """
    international = raw.strip().startswith("+")
    digits = "".join(character for character in raw if character.isdigit())
    if not digits:
        return None
    if international:
        return digits
    if digits.startswith("0"):
        # Zéro national : on l'échange contre l'indicatif du pays.
        return country + digits[1:]
    return digits
