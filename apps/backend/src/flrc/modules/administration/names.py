import unicodedata

_TURKISH_UPPERCASE_I = str.maketrans({"I": "ı", "İ": "i"})


def search_key(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).translate(_TURKISH_UPPERCASE_I)
    return normalized.casefold().strip()


def normalize_email(value: str) -> str:
    return value.strip().casefold()
