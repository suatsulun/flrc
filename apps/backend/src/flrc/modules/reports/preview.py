"""On-screen report-card previews for teachers (ADR-078).

A teacher checks one student's card before the official set is printed. The
preview is the real card for that student, rendered by the same builder and
templates as the official set, with a diagonal "ÖNİZLEME" mark on every page
so it can never pass for an issued card.

Unlike grade reads (ADR-071), a card is personal data of one student, so a
teacher sees only the cards their own assignments produce in that year:
main/skills give the class's English card, german/french give that karne for
the students who take the language. Administrators may preview any card.
"""

from collections.abc import Iterable
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from flrc.core.rate_limit import report_single_rate_limit
from flrc.db.models import (
    AcademicYear,
    Enrollment,
    SchoolClass,
    Semester,
    Student,
    StudentLanguage,
    TeachingAssignment,
    User,
)
from flrc.db.session import get_session
from flrc.modules.academics.class_names import class_label
from flrc.modules.auth.dependencies import current_user
from flrc.modules.grades.router import grid_semester
from flrc.modules.reports.branding import ReportKind
from flrc.modules.reports.builder import REPORT_SETS, SECOND_LANGUAGES, build_report_entries
from flrc.modules.reports.render import render_report_pdf

router = APIRouter(tags=["report-preview"])

PREVIEW_WATERMARK = "ÖNİZLEME"
ROLE_SUBJECT = {"main": "english", "skills": "english", "german": "german", "french": "french"}
# Report sets in their catalogue order; the scope lists a class's cards in this order.
KIND_ORDER: tuple[ReportKind, ...] = (
    "english_elementary",
    "english_middle",
    "german_karne",
    "french_karne",
)


class PreviewStudentOut(BaseModel):
    student_id: int
    school_number: int | None
    full_name: str


class PreviewClassOut(BaseModel):
    class_id: int
    class_name: str
    grade_level: int
    kind: ReportKind
    # The students this card exists for, in the official set's order.
    students: list[PreviewStudentOut]


class PreviewSemesterOut(BaseModel):
    id: int
    number: int
    status: str


class PreviewScopeOut(BaseModel):
    year_id: int
    year_label: str
    semester_id: int
    semester_number: int
    semesters: list[PreviewSemesterOut]
    classes: list[PreviewClassOut]


def card_kind(role: str, grade_level: int) -> ReportKind | None:
    """The card an assignment role produces for a grade; ``None`` if that grade has none."""
    subject = ROLE_SUBJECT[role]
    for kind in KIND_ORDER:
        spec = REPORT_SETS[kind]
        if spec.subject == subject and spec.first_grade <= grade_level <= spec.last_grade:
            return kind
    return None


async def _roster(
    db: AsyncSession, *, year_id: int, class_ids: Iterable[int]
) -> dict[int, list[tuple[PreviewStudentOut, str | None]]]:
    """Each class's students with their second language, in the report builder's order."""
    rows = (
        await db.execute(
            select(
                Enrollment.class_id,
                Student.id,
                Enrollment.school_number,
                Student.full_name,
                StudentLanguage.language,
            )
            .join(Student, Student.id == Enrollment.student_id)
            .outerjoin(
                StudentLanguage,
                and_(
                    StudentLanguage.student_id == Student.id,
                    StudentLanguage.year_id == year_id,
                ),
            )
            .where(Enrollment.class_id.in_(list(class_ids)))
            .order_by(
                Enrollment.class_id,
                Enrollment.school_number.asc().nulls_last(),
                Student.search_name,
                Student.id,
            )
        )
    ).all()
    roster: dict[int, list[tuple[PreviewStudentOut, str | None]]] = {}
    for class_id, student_id, school_number, full_name, language in rows:
        roster.setdefault(class_id, []).append(
            (
                PreviewStudentOut(
                    student_id=student_id, school_number=school_number, full_name=full_name
                ),
                language,
            )
        )
    return roster


def _card_students(
    roster: list[tuple[PreviewStudentOut, str | None]], kind: ReportKind
) -> list[PreviewStudentOut]:
    """The students a card set includes: everyone, or only those taking the language."""
    subject = REPORT_SETS[kind].subject
    return [
        student
        for student, language in roster
        if subject not in SECOND_LANGUAGES or language == subject
    ]


async def _default_semester(db: AsyncSession) -> Semester:
    """The class catalog's default term: the active (else latest) year's open or last one."""
    year_id = (
        await db.execute(
            select(AcademicYear.id)
            .order_by((AcademicYear.status == "active").desc(), AcademicYear.label.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if year_id is None:
        raise HTTPException(409, {"code": "semester_missing"})
    return await grid_semester(db, year_id, None)


@router.get("/reports/preview/scope")
async def get_preview_scope(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int | None = None,
) -> PreviewScopeOut:
    """The cards the signed-in user's own assignments produce in a semester's year.

    Without ``semester_id`` the current term is used. Lists only classes where the
    user holds a teaching assignment, administrators included.
    """
    if semester_id is None:
        semester = await _default_semester(db)
    else:
        found = await db.get(Semester, semester_id)
        if found is None:
            raise HTTPException(404, {"code": "unknown_semester"})
        semester = found
    year = await db.get(AcademicYear, semester.year_id)
    if year is None:
        raise HTTPException(404, {"code": "unknown_year"})
    semesters = list(
        await db.scalars(
            select(Semester).where(Semester.year_id == year.id).order_by(Semester.number)
        )
    )

    assignments = (
        await db.execute(
            select(SchoolClass, TeachingAssignment.role)
            .join(TeachingAssignment, TeachingAssignment.class_id == SchoolClass.id)
            .where(SchoolClass.year_id == year.id, TeachingAssignment.user_id == user.id)
        )
    ).all()
    kinds_by_class: dict[int, set[ReportKind]] = {}
    classes: dict[int, SchoolClass] = {}
    for school_class, role in assignments:
        kind = card_kind(role, school_class.grade_level)
        if kind is not None:
            classes[school_class.id] = school_class
            kinds_by_class.setdefault(school_class.id, set()).add(kind)

    roster = await _roster(db, year_id=year.id, class_ids=classes) if classes else {}
    entries = [
        PreviewClassOut(
            class_id=school_class.id,
            class_name=class_label(school_class.grade_level, school_class.section),
            grade_level=school_class.grade_level,
            kind=kind,
            students=_card_students(roster.get(school_class.id, []), kind),
        )
        for school_class in sorted(
            classes.values(), key=lambda item: (item.grade_level, item.section, item.id)
        )
        for kind in KIND_ORDER
        if kind in kinds_by_class[school_class.id]
    ]
    return PreviewScopeOut(
        year_id=year.id,
        year_label=year.label,
        semester_id=semester.id,
        semester_number=semester.number,
        semesters=[
            PreviewSemesterOut(id=item.id, number=item.number, status=item.status)
            for item in semesters
        ],
        classes=entries,
    )


def _top_card_only(pdf: bytes) -> bytes:
    """Crop two-up middle-school sheets to their top card, the only one a preview fills."""
    writer = PdfWriter(clone_from=PdfReader(BytesIO(pdf)))
    for page in writer.pages:
        box = page.mediabox
        top = RectangleObject((box.left, box.bottom + box.height / 2, box.right, box.top))
        page.mediabox = top
        page.cropbox = top
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


@router.get(
    "/reports/preview",
    dependencies=[Depends(report_single_rate_limit)],
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Watermarked card"}},
)
async def get_report_preview(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
    semester_id: int,
    student_id: int,
    kind: ReportKind,
) -> Response:
    """One student's card as an inline PDF marked "ÖNİZLEME" on every page.

    Teachers may preview only the card their own assignment in the student's
    class produces; administrators may preview any card. Everyone else gets 403.
    """
    semester = await db.get(Semester, semester_id)
    if semester is None:
        raise HTTPException(404, {"code": "unknown_semester"})
    placement = (
        await db.execute(
            select(SchoolClass)
            .join(Enrollment, Enrollment.class_id == SchoolClass.id)
            .where(Enrollment.student_id == student_id, Enrollment.year_id == semester.year_id)
        )
    ).scalar_one_or_none()
    if placement is None:
        if not user.is_admin:
            raise HTTPException(403, {"code": "forbidden"})
        raise HTTPException(404, {"code": "unknown_student"})
    if not user.is_admin:
        roles = await db.scalars(
            select(TeachingAssignment.role).where(
                TeachingAssignment.class_id == placement.id,
                TeachingAssignment.user_id == user.id,
            )
        )
        if kind not in {card_kind(role, placement.grade_level) for role in roles}:
            raise HTTPException(403, {"code": "forbidden"})

    roster = await _roster(db, year_id=semester.year_id, class_ids=[placement.id])
    eligible = any(
        student.student_id == student_id
        for student in _card_students(roster.get(placement.id, []), kind)
    )
    spec = REPORT_SETS[kind]
    if not eligible or not spec.first_grade <= placement.grade_level <= spec.last_grade:
        # A teacher's own card kind always fits the grade, so only the language can miss.
        if not user.is_admin:
            raise HTTPException(403, {"code": "forbidden"})
        raise HTTPException(409, {"code": "report_preview_not_eligible"})

    entries = await db.run_sync(
        lambda session: build_report_entries(
            session,
            semester_id=semester.id,
            kind=kind,
            locale="tr",
            class_ids=[placement.id],
            student_ids=[student_id],
        )
    )
    # The card is chosen by the requested id, never by name or roster position. It can
    # only be missing if the pupil moved or changed language since the checks above.
    card = next(
        (
            entry.card
            for entry in entries
            if entry.student_id == student_id and entry.class_id == placement.id
        ),
        None,
    )
    if card is None:
        raise HTTPException(409, {"code": "report_preview_roster_changed"})

    pdf = await run_in_threadpool(render_report_pdf, [card], watermark=PREVIEW_WATERMARK)
    if kind == "english_middle":
        pdf = await run_in_threadpool(_top_card_only, pdf)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        },
    )
