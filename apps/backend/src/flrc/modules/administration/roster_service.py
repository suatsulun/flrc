import structlog
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import AcademicYear, Enrollment, SchoolClass, StudentLanguage


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
    changed = 0
    unchanged = 0
    for enrollment in enrollments:
        if enrollment.class_id == target_class.id:
            unchanged += 1
        else:
            enrollment.class_id = target_class.id
            changed += 1
    return changed, unchanged
