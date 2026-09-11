"""School programme rules shared by roster editing and synthetic data."""

L2_START_GRADE = 4


def has_teacher_comments(grade_level: int, subject: str) -> bool:
    return subject != "english" or grade_level < 5


def uses_scale_only(grade_level: int, subject: str) -> bool:
    return grade_level == 4 and subject in ("german", "french")


def allows_column_type(grade_level: int, subject: str, value_type: str) -> bool:
    if value_type == "text" and not has_teacher_comments(grade_level, subject):
        return False
    # The rating rule excludes numeric scores, not written teacher comments.
    return not uses_scale_only(grade_level, subject) or value_type in ("scale3", "text")
