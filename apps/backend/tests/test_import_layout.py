"""Roster workbooks as schools export them: one sheet per class (ADR-069)."""

import io
from itertools import count

from openpyxl import Workbook

from flrc.modules.academics.class_names import PREP_GRADE
from flrc.modules.imports.parser import parse_workbook

HEADERS = ["SIRA\nNO", "OKUL \nNO", "ADI SOYADI", "CİNSİYET", "AÇIKLAMA"]


def class_sheet(workbook: Workbook, title: str, grade: int, numbers: count) -> None:
    sheet = workbook.create_sheet(title)
    headers = HEADERS[:4] + (["2.Y.D."] if grade >= 4 else []) + HEADERS[4:]
    sheet.append([f"2026-2027 Synthetic School {title} class list"])
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    sheet.append(headers)
    for order, language in enumerate(("ALM.", "FR."), 1):
        row = [order, next(numbers), f"Synthetic Pupil {title} {order}", "E"]
        sheet.append(row + ([language] if grade >= 4 else []))
    # Summary rows put their label in either merged column and a count under the names.
    sheet.append(["KIZ", None, 1])
    sheet.append([None, "ERKEK", 1])
    sheet.append(["TOPLAM", None, 2])


def school_export() -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    numbers = count(101)
    for prep in ("GÜNEŞ", "BULUT"):
        class_sheet(workbook, prep, PREP_GRADE, numbers)
    for grade in range(1, 9):
        for section in "ABCD":
            class_sheet(workbook, f"{grade}-{section}", grade, numbers)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_class_per_sheet_school_export_imports_every_pupil() -> None:
    plan = parse_workbook(school_export())

    assert plan.issues == []
    assert len(plan.rows) == 34 * 2
    classes = {(row.grade_level, row.section) for row in plan.rows}
    assert {(PREP_GRADE, "Güneş"), (PREP_GRADE, "Bulut"), (1, "A"), (8, "D")} <= classes
    assert len(classes) == 34
    languages = {(row.grade_level >= 4, row.language) for row in plan.rows}
    assert languages == {(False, None), (True, "german"), (True, "french")}
    assert all(row.language_present == (row.grade_level >= 4) for row in plan.rows)


def test_bare_title_without_class_sheets_is_not_a_class() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Liste"
    sheet.append(["Okul No", "Ad Soyad"])
    sheet.append([101, "Synthetic Pupil One"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    plan = parse_workbook(buffer.getvalue())

    assert plan.rows == []
    assert [issue.code for issue in plan.issues] == ["bad_class"]
