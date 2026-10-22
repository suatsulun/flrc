"""School programme rules shared by roster editing and synthetic data."""

from typing import Literal

from flrc.modules.academics.class_names import MAX_GRADE, PREP_GRADE

L2_START_GRADE = 4
MIDDLE_START_GRADE = 5

# Primary school is Hazırlık through grade 4; middle school is grades 5-8.
# School numbers are unique per (year, stage); the database derives the
# enrollment stage with the same boundary (migration 9b3e5d7f1c20).
Stage = Literal["primary", "middle"]


def stage_for_grade(grade_level: int) -> Stage:
    return "primary" if grade_level < MIDDLE_START_GRADE else "middle"


# Leaving these grades means entering a new school stage. The school places
# those pupils into sections itself, and new pupils join them, so the rollover
# leaves them for the roster import to place by name (ADR-066).
PLACEMENT_GRADES = frozenset({PREP_GRADE, MIDDLE_START_GRADE - 1})


def carries_over(grade_level: int) -> bool:
    """Whether a pupil keeps their section into next year's class at rollover."""
    return grade_level not in PLACEMENT_GRADES and grade_level < MAX_GRADE


def has_teacher_comments(grade_level: int, subject: str) -> bool:
    return subject != "english" or grade_level < 5


def prints_turkish(grade_level: int, subject: str, value_type: str) -> bool:
    """Whether a field's printed card shows Turkish wording beside the subject's language.

    The primary English card prints every field bilingually. The karne prints its
    rating rows and teacher comments bilingually; its scores only feed the average.
    The middle-school English card prints the subject's language alone.
    """
    if subject == "english":
        return grade_level < MIDDLE_START_GRADE
    return value_type != "score"


def uses_scale_only(grade_level: int, subject: str) -> bool:
    return grade_level == 4 and subject in ("german", "french")


def allows_column_type(grade_level: int, subject: str, value_type: str) -> bool:
    if value_type == "text" and not has_teacher_comments(grade_level, subject):
        return False
    # The rating rule excludes numeric scores, not written teacher comments.
    return not uses_scale_only(grade_level, subject) or value_type in ("scale3", "text")
