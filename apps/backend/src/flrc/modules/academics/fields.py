"""Field values and label fallback shared by grids, archives and reports."""

from flrc.db.models import GradeValue

CellValue = int | str | None
VALUE_FIELD = {"score": "score", "scale3": "scale", "text": "text_value"}


def cell_value(grade: GradeValue | None, value_type: str) -> CellValue:
    return getattr(grade, VALUE_FIELD[value_type]) if grade is not None else None


def pick_label(labels: dict[str, str], locale: str) -> str:
    """Prefer the requested locale, its base language, Turkish, then the first label."""
    return (
        labels.get(locale)
        or labels.get(locale.split("-")[0])
        or labels.get("tr")
        or next(iter(labels.values()), "")
    )
