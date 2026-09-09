"""School programme rules shared by roster editing and synthetic data."""

L2_START_GRADE = 4


def uses_scale_only(grade_level: int, subject: str) -> bool:
    return grade_level == 4 and subject in ("german", "french")


def allows_column_type(grade_level: int, subject: str, value_type: str) -> bool:
    return not uses_scale_only(grade_level, subject) or value_type == "scale3"
