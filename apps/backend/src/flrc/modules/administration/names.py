import unicodedata

_TURKISH_UPPERCASE_I = str.maketrans({"I": "ı", "İ": "i"})


def search_key(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).translate(_TURKISH_UPPERCASE_I)
    return normalized.casefold().strip()


def normalize_email(value: str) -> str:
    return value.strip().casefold()


_TURKISH_LOWERCASE_I = str.maketrans({"i": "İ", "ı": "I"})


def turkish_upper(value: str) -> str:
    """Uppercase with Turkish dotted and dotless i, which str.upper gets wrong."""
    return value.translate(_TURKISH_LOWERCASE_I).upper()


def turkish_lower(value: str) -> str:
    return value.translate(_TURKISH_UPPERCASE_I).lower()


def turkish_title(value: str) -> str:
    """Capitalise every word the Turkish way: ``yıldız`` becomes ``Yıldız``."""
    return " ".join(turkish_upper(word[:1]) + turkish_lower(word[1:]) for word in value.split())
