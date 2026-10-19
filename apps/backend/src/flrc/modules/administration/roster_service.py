import structlog
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import (
    SCHOOL_NUMBER_CONSTRAINT,
    AcademicYear,
    Enrollment,
    SchoolClass,
    StudentLanguage,
)
from flrc.modules.academics.programme import stage_for_grade


def is_duplicate_school_number(exc: IntegrityError) -> bool:
    """Whether a failed write reused a school number within its year and stage."""
    return SCHOOL_NUMBER_CONSTRAINT in str(exc.orig)


async def school_number_taken(
    db: AsyncSession,
    *,
    year_id: int,
    stage: str,
    school_number: int,
    except_enrollment_id: int | None = None,
) -> bool:
    """Whether another enrollment already holds this number in the year's stage."""
    statement = select(Enrollment.id).where(
        Enrollment.year_id == year_id,
        Enrollment.stage == stage,
        Enrollment.school_number == school_number,
    )
    if except_enrollment_id is not None:
        statement = statement.where(Enrollment.id != except_enrollment_id)
    return await db.scalar(statement.limit(1)) is not None


async def remove_student(
    db: AsyncSession, *, class_id: int, student_id: int, actor_id: int
) -> None:
    school_class = await db.get(SchoolClass, class_id)
    if school_class is None:
        raise HTTPException(404, {"code": "unknown_class"})
    year = await db.scalar(
        select(AcademicYear).where(AcademicYear.id == school_class.year_id).with_for_update()
    )
    if year is None or year.status == "archived":
        raise HTTPException(409, {"code": "year_not_writable"})
    enrollment = await db.scalar(
        select(Enrollment)
        .where(Enrollment.class_id == class_id, Enrollment.student_id == student_id)
        .with_for_update()
    )
    if enrollment is None:
        raise HTTPException(404, {"code": "unknown_enrollment"})
    await db.execute(
        delete(StudentLanguage).where(
            StudentLanguage.student_id == student_id, StudentLanguage.year_id == year.id
        )
    )
    # Remove this year's roster membership, retaining the person, grades and audit history.
    await db.delete(enrollment)
    await db.commit()
    structlog.get_logger().info(
        "roster_student_removed",
        actor_id=actor_id,
        student_id=student_id,
        class_id=class_id,
        year_id=year.id,
    )


async def move_students(
    db: AsyncSession,
    *,
    student_ids: list[int],
    target_class: SchoolClass,
    allow_grade_change: bool,
) -> tuple[int, int]:
    enrollments = list(
        await db.scalars(
            select(Enrollment).where(
                Enrollment.student_id.in_(student_ids),
                Enrollment.year_id == target_class.year_id,
            )
        )
    )
    if len(enrollments) != len(set(student_ids)):
        raise ValueError("student_not_enrolled_in_year")
    source_ids = {item.class_id for item in enrollments}
    source_classes = {
        item.id: item
        for item in (await db.scalars(select(SchoolClass).where(SchoolClass.id.in_(source_ids))))
    }
    if not allow_grade_change and any(
        source_classes[item.class_id].grade_level != target_class.grade_level
        for item in enrollments
    ):
        raise ValueError("grade_change_requires_confirmation")
    # Numbers are unique per year and stage. A pupil crossing into the target
    # stage keeps their number, so it must not already belong to a pupil there;
    # the move is refused as a whole rather than renumbering anyone.
    target_stage = stage_for_grade(target_class.grade_level)
    if any(item.stage != target_stage for item in enrollments):
        moved_numbers = [
            item.school_number for item in enrollments if item.school_number is not None
        ]
        incoming = [
            item.school_number
            for item in enrollments
            if item.stage != target_stage and item.school_number is not None
        ]
        if len(set(moved_numbers)) != len(moved_numbers) or (
            await db.scalar(
                select(Enrollment.id)
                .where(
                    Enrollment.year_id == target_class.year_id,
                    Enrollment.stage == target_stage,
                    Enrollment.school_number.in_(incoming),
                    Enrollment.id.not_in([item.id for item in enrollments]),
                )
                .limit(1)
            )
            is not None
        ):
            raise ValueError("duplicate_school_number")
    changed = 0
    unchanged = 0
    for enrollment in enrollments:
        if enrollment.class_id == target_class.id:
            unchanged += 1
        else:
            enrollment.class_id = target_class.id
            changed += 1
    return changed, unchanged
