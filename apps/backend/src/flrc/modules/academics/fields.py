"""Field values and label fallback shared by grids, archives and reports."""

from flrc.db.models import GradeValue

CellValue = int | str | None
VALUE_FIELD = {"score": "score", "scale3": "scale", "text": "text_value"}
# Every field is named in its subject's own language, whatever language the UI uses.
SUBJECT_LOCALE = {"english": "en", "german": "de", "french": "fr"}


def cell_value(grade: GradeValue | None, value_type: str) -> CellValue:
    return getattr(grade, VALUE_FIELD[value_type]) if grade is not None else None


def pick_label(labels: dict[str, str], locale: str) -> str:
    """Prefer the requested locale, its base language, Turkish, then any non-empty label."""
    return (
        labels.get(locale)
        or labels.get(locale.split("-")[0])
        or labels.get("tr")
        or next((label for label in labels.values() if label), "")
    )


def field_name(labels: dict[str, str], subject: str) -> str:
    """The one name a field shows in the apps: its subject's language, else what was entered."""
    return pick_label(labels, SUBJECT_LOCALE[subject])
