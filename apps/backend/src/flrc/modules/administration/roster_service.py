from collections.abc import Collection
from typing import TypedDict

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import (
    SCHOOL_NUMBER_CONSTRAINT,
    AcademicYear,
    Enrollment,
    SchoolClass,
    Student,
    StudentLanguage,
)
from flrc.modules.academics.class_names import class_label
from flrc.modules.academics.programme import stage_for_grade

# Who holds a school number: the parameters of a refused change.
NumberHolder = TypedDict("NumberHolder", {"number": int, "student": str, "class": str})


class RemovedEnrollment(TypedDict):
    student_id: int
    class_id: int
    year_id: int
    school_number: int | None
    language: str | None


def is_duplicate_school_number(exc: IntegrityError) -> bool:
    """Whether a failed write reused a school number within its year and stage."""
    return SCHOOL_NUMBER_CONSTRAINT in str(exc.orig)


async def school_number_holder(
    db: AsyncSession,
    *,
    year_id: int,
    stage: str,
    school_number: int,
    except_enrollment_ids: Collection[int] = (),
) -> NumberHolder | None:
    """The pupil already holding this number in the year's stage, if any."""
    statement = (
        select(Student.full_name, SchoolClass.grade_level, SchoolClass.section)
        .select_from(Enrollment)
        .join(Student, Student.id == Enrollment.student_id)
        .join(SchoolClass, SchoolClass.id == Enrollment.class_id)
        .where(
            Enrollment.year_id == year_id,
            Enrollment.stage == stage,
            Enrollment.school_number == school_number,
        )
    )
    if except_enrollment_ids:
        statement = statement.where(Enrollment.id.not_in(list(except_enrollment_ids)))
    row = (await db.execute(statement.limit(1))).first()
    if row is None:
        return None
    return NumberHolder(
        {
            "number": school_number,
            "student": row.full_name,
            "class": class_label(row.grade_level, row.section),
        }
    )


async def school_number_taken(
    db: AsyncSession,
    *,
    year_id: int,
    stage: str,
    school_number: int,
    except_enrollment_id: int | None = None,
) -> bool:
    """Whether another enrollment already holds this number in the year's stage."""
    holder = await school_number_holder(
        db,
        year_id=year_id,
        stage=stage,
        school_number=school_number,
        except_enrollment_ids=() if except_enrollment_id is None else (except_enrollment_id,),
    )
    return holder is not None


async def delete_enrollment(db: AsyncSession, enrollment: Enrollment) -> str | None:
    """Remove one year's roster membership and its second language; return that language.

    The person, their grades and audit history, and other years stay untouched.
    """
    language = await student_language(db, enrollment.student_id, enrollment.year_id)
    await assign_student_language(
        db, student_id=enrollment.student_id, year_id=enrollment.year_id, language=None
    )
    await db.delete(enrollment)
    await db.flush()
    return language


async def lock_enrollments(
    db: AsyncSession, *, year_id: int, student_ids: Collection[int]
) -> list[Enrollment]:
    """Lock pupils' enrollments of one year, in id order, and read them fresh.

    Every write of a pupil's yearly data (number, class, second language) and its undo
    takes this lock first, so a recorded previous state cannot change before the commit.
    """
    return list(
        await db.scalars(
            select(Enrollment)
            .where(Enrollment.year_id == year_id, Enrollment.student_id.in_(list(student_ids)))
            .order_by(Enrollment.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )


async def student_language(db: AsyncSession, student_id: int, year_id: int) -> str | None:
    return await db.scalar(
        select(StudentLanguage.language).where(
            StudentLanguage.student_id == student_id,
            StudentLanguage.year_id == year_id,
        )
    )


async def assign_student_language(
    db: AsyncSession, *, student_id: int, year_id: int, language: str | None
) -> None:
    """Set or clear a pupil's second language for one year.

    Callers hold the pupil's enrollment lock (``lock_enrollments``) or created that
    enrollment in the same transaction.
    """
    if language is None:
        await db.execute(
            delete(StudentLanguage).where(
                StudentLanguage.student_id == student_id,
                StudentLanguage.year_id == year_id,
            )
        )
        return
    await db.execute(
        pg_insert(StudentLanguage)
        .values(student_id=student_id, year_id=year_id, language=language)
        .on_conflict_do_update(
            index_elements=["student_id", "year_id"],
            set_={"language": language},
        )
    )


async def remove_student(db: AsyncSession, *, class_id: int, student_id: int) -> RemovedEnrollment:
    """Remove a pupil from a class roster; the caller records the action and commits."""
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
    school_number = enrollment.school_number
    language = await delete_enrollment(db, enrollment)
    return RemovedEnrollment(
        student_id=student_id,
        class_id=class_id,
        year_id=year.id,
        school_number=school_number,
        language=language,
    )


async def move_students(
    db: AsyncSession,
    *,
    student_ids: list[int],
    target_class: SchoolClass,
    allow_grade_change: bool,
) -> tuple[list[tuple[int, int]], int]:
    """Move pupils within their year; return ``(student_id, from_class_id)`` per move and
    the number already in the target class."""
    enrollments = await lock_enrollments(
        db, year_id=target_class.year_id, student_ids=set(student_ids)
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
    moved: list[tuple[int, int]] = []
    unchanged = 0
    for enrollment in enrollments:
        if enrollment.class_id == target_class.id:
            unchanged += 1
        else:
            moved.append((enrollment.student_id, enrollment.class_id))
            enrollment.class_id = target_class.id
    return moved, unchanged
