from typing import Any

DANGEROUS_FORMULA_PREFIXES = ("=", "+", "-", "@")


def safe_spreadsheet_cell(value: Any) -> Any:
    """Neutralize formulas when untrusted text is opened by spreadsheet software."""
    if not isinstance(value, str):
        return value
    candidate = value.lstrip(" \t\r\n")
    if candidate.startswith(DANGEROUS_FORMULA_PREFIXES):
        return f"'{value}"
    return value
