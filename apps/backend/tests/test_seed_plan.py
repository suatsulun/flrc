from collections import Counter

from flrc.cli import (
    ACADEMIC_YEARS,
    CORE_SECTIONS,
    FRENCH_KEYS,
    G_SECTION_GRADES,
    GERMAN_KEYS,
    PREP_SECTIONS,
    PRIMARY_ENGLISH_KEYS,
    SECONDARY_ENGLISH_KEYS,
    STUDENTS_PER_CLASS,
    seed_class_plans,
)
from flrc.modules.academics.class_names import PREP_GRADE


def test_seed_plan_matches_school_size_and_staff_boundaries() -> None:
    plans = seed_class_plans()

    assert len(ACADEMIC_YEARS) == 4
    assert len(plans) == 55
    assert len(plans) * STUDENTS_PER_CLASS == 1_210
    assert Counter(plan.grade_level for plan in plans) == {
        PREP_GRADE: len(PREP_SECTIONS),
        **{grade: 7 if grade in G_SECTION_GRADES else 6 for grade in range(1, 9)},
    }
    assert {plan.section for plan in plans if plan.grade_level == PREP_GRADE} == set(PREP_SECTIONS)
    assert all(
        {plan.section for plan in plans if plan.grade_level == grade}.issuperset(CORE_SECTIONS)
        for grade in range(1, 9)
    )

    primary = [plan for plan in plans if plan.grade_level <= 4]
    secondary = [plan for plan in plans if plan.grade_level >= 5]
    assert {
        teacher for plan in primary for teacher in (plan.main_teacher, plan.skills_teacher)
    } == set(PRIMARY_ENGLISH_KEYS)
    assert {
        teacher for plan in secondary for teacher in (plan.main_teacher, plan.skills_teacher)
    } == set(SECONDARY_ENGLISH_KEYS)
    assert all(
        plan.grade_level >= 5
        for plan in plans
        if "my-account" in (plan.main_teacher, plan.skills_teacher)
    )

    language_plans = [plan for plan in plans if plan.grade_level >= 4]
    assert Counter(plan.german_teacher for plan in language_plans) == {
        GERMAN_KEYS[0]: 16,
        GERMAN_KEYS[1]: 16,
    }
    assert Counter(plan.french_teacher for plan in language_plans) == {
        FRENCH_KEYS[0]: 16,
        FRENCH_KEYS[1]: 16,
    }
    assert all(
        plan.german_teacher is None and plan.french_teacher is None
        for plan in plans
        if plan.grade_level < 4
    )


def test_a_to_f_cohorts_have_a_complete_three_year_promotion_path() -> None:
    available = {(plan.grade_level, plan.section) for plan in seed_class_plans()}

    for section in CORE_SECTIONS:
        assert all((grade, section) in available for grade in range(5, 9))
