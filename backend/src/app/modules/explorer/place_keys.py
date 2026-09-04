import unicodedata


def place_name_key(value: str) -> str:
    """Normalize accents, punctuation, casing, and spacing for exact dedupe."""
    decomposed = unicodedata.normalize("NFD", value.casefold()).replace("đ", "d")
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    alphanumeric = "".join(
        character if character.isalnum() else " " for character in without_marks
    )
    return " ".join(alphanumeric.split())
