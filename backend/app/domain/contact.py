"""Reaching a family: the rule, without the network.

A number is written the way it is spoken — « 06 61 23 45 67 » — while
WhatsApp only knows the international form, with no spaces and no
national zero. The conversion belongs here: it is a rule, not a
technique.
"""

# The academy is Moroccan; a number written « 06… » is Moroccan. A number
# already in international form keeps its own, whatever it is.
DEFAULT_COUNTRY = "212"


def whatsapp_number(raw: str, country: str = DEFAULT_COUNTRY) -> str | None:
    """The form WhatsApp expects, or nothing if this is not a number.

    Nothing is better than an invented number: a record sometimes reads
    « à demander » or « chez la voisine », and that has to be visible
    rather than turned into a message to a stranger.
    """
    international = raw.strip().startswith("+")
    digits = "".join(character for character in raw if character.isdigit())
    if not digits:
        return None
    if international:
        return digits
    if digits.startswith("0"):
        # National zero: swapped for the country code.
        return country + digits[1:]
    return digits
