"""Class naming rules shared by the API, the importer, reports and the seed.

A class is a grade level plus a section. Grades 1 to 8 carry a letter
section and display as ``5/A`` (ADR-021). The primary school's Hazırlık
(preparatory) year comes before grade 1 and is stored as grade 0; its
classes carry a name such as ``Bulut`` instead of a letter and display as
that name alone (ADR-065).
"""

from flrc.modules.administration.names import turkish_title, turkish_upper

PREP_GRADE = 0
MIN_GRADE = PREP_GRADE
MAX_GRADE = 8
SECTION_MAX_LENGTH = 32


def is_prep(grade_level: int) -> bool:
    return grade_level == PREP_GRADE


def class_label(grade_level: int, section: str) -> str:
    """The class name people use: ``Bulut`` for Hazırlık, ``5/A`` otherwise."""
    return section if is_prep(grade_level) else f"{grade_level}/{section}"


def normalize_section(grade_level: int, section: str) -> str:
    """Canonical section spelling: ``A`` for a letter section, ``Yıldız`` for a name."""
    value = " ".join(section.split())
    return turkish_title(value) if is_prep(grade_level) else turkish_upper(value)
