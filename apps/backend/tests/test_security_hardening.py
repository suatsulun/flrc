import io
import re
import zipfile
from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from starlette.requests import Request

from flrc.core import rate_limit
from flrc.db import models as m
from flrc.modules.imports.parser import (
    MAX_WORKSHEET_ROWS,
    InvalidWorkbook,
    parse_workbook,
)
from tests.conftest import TestSession, cell


def _workbook_bytes(extra_rows: int = 0) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "5-A"
    sheet.append(["Okul No", "Ad Soyad"])
    sheet.append([51001, "Synthetic Student"])
    for offset in range(extra_rows):
        sheet.append([51002 + offset, f"Synthetic Filler {offset}"])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def _repack(data: bytes, rewrite: Callable[[str], str]) -> bytes:
    """Rebuild a workbook with its first worksheet XML rewritten.

    Hand-editing the sheet XML is the only way to reproduce what a hostile or
    non-openpyxl producer can put on the wire.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                payload = source.read(item.filename)
                if item.filename == "xl/worksheets/sheet1.xml":
                    payload = rewrite(payload.decode()).encode()
                target.writestr(item.filename, payload)
    return buffer.getvalue()


def test_xlsx_external_entity_is_never_resolved() -> None:
    hostile = _repack(
        _workbook_bytes(),
        lambda sheet: (
            '<?xml version="1.0"?>'
            '<!DOCTYPE worksheet [<!ENTITY xxe SYSTEM "file:///etc/hostname">]>'
            + sheet.replace("Synthetic Student", "&xxe;")
        ),
    )

    with pytest.raises(InvalidWorkbook, match="malformed_xlsx"):
        parse_workbook(hostile)


def test_xlsx_row_bound_holds_when_the_declared_dimension_lies() -> None:
    hostile = _repack(
        _workbook_bytes(extra_rows=MAX_WORKSHEET_ROWS),
        lambda sheet: re.sub(r"<dimension[^>]*/>", '<dimension ref="A1:B2"/>', sheet),
    )

    with pytest.raises(InvalidWorkbook, match="xlsx_dimensions_too_large"):
        parse_workbook(hostile)


def test_xlsx_without_a_declared_dimension_still_imports() -> None:
    # Several real exporters omit <dimension>; rejecting those would break the
    # school's only route for loading a roster.
    plan = parse_workbook(
        _repack(_workbook_bytes(), lambda sheet: re.sub(r"<dimension[^>]*/>", "", sheet))
    )

    assert [row.school_number for row in plan.rows] == [51001]


async def test_teacher_cannot_cross_class_or_subject_boundaries(api, world) -> None:
    async with TestSession() as db:
        other_class = m.SchoolClass(year_id=world.year, grade_level=5, section="B")
        db.add(other_class)
        await db.commit()
        other_class_id = other_class.id

    async with api(world.main) as client:
        other_read = await client.get(
            f"/api/classes/{other_class_id}/grid", params={"subject": "english"}
        )
        other_save = await client.post(
            f"/api/classes/{other_class_id}/grid/save",
            json={
                "subject": "english",
                "cells": [cell(world.student_one, world.main_column, 90)],
            },
        )
        other_grant = await client.post(
            f"/api/classes/{other_class_id}/grants", json={"role": "main"}
        )
        foreign_subject = await client.get(
            f"/api/classes/{world.cls}/grid", params={"subject": "german"}
        )

    for response in (other_read, other_save, other_grant, foreign_subject):
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "class_subject_forbidden"


async def test_teacher_cannot_enumerate_unassigned_academic_year(api, world) -> None:
    async with TestSession() as db:
        other_year = m.AcademicYear(label="2040-2041", status="archived")
        db.add(other_year)
        await db.flush()
        db.add(m.Semester(year_id=other_year.id, number=1, status="locked"))
        await db.commit()
        other_year_id = other_year.id

    async with api(world.main) as client:
        years = await client.get("/api/academic-years")
        catalog = await client.get("/api/class-catalog", params={"year_id": other_year_id})

    assert [item["id"] for item in years.json()] == [world.year]
    assert catalog.status_code == 200
    assert catalog.json() == []


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("get", "/api/classes/999999/assignments", {}),
        ("put", "/api/classes/999999/assignments/main", {"json": {"user_id": 999999}}),
        ("patch", "/api/columns/999999", {"json": {"position": 1}}),
        ("delete", "/api/columns/999999", {}),
        ("patch", "/api/admin/users/999999", {"json": {"full_name": "Synthetic Name"}}),
        ("get", "/api/admin/years/999999/classes", {}),
        ("patch", "/api/admin/classes/999999", {"json": {"section": "B"}}),
        ("delete", "/api/admin/classes/999999", {}),
        ("get", "/api/admin/years/999999/assignments", {}),
        ("put", "/api/admin/years/999999/assignments", {"json": {"changes": []}}),
        (
            "patch",
            "/api/admin/students/999999?year_id=999999",
            {"json": {"full_name": "Synthetic Name"}},
        ),
        ("get", "/api/admin/classes/999999/roster", {}),
        (
            "post",
            "/api/admin/classes/999999/roster",
            {"json": {"school_number": 999999, "full_name": "Synthetic Name"}},
        ),
        (
            "patch",
            "/api/admin/classes/999999/roster/999999",
            {"json": {"full_name": "Synthetic Name"}},
        ),
        (
            "put",
            "/api/admin/years/999999/student-language",
            {"json": {"student_ids": [999999], "language": "german"}},
        ),
        ("post", "/api/admin/years/999999/activate", {}),
        ("post", "/api/admin/years/999999/advance-semester", {}),
        ("post", "/api/admin/years/999999/lock-semester-2", {}),
        (
            "post",
            "/api/admin/years/999999/reopen-semester",
            {"json": {"number": 1, "confirm_label": "Synthetic year"}},
        ),
        ("get", "/api/admin/years/999999/audit-export.csv", {}),
        (
            "post",
            "/api/admin/years/999999/close",
            {"json": {"confirm_label": "Synthetic year", "audit_sha256": "0" * 64}},
        ),
        ("get", "/api/archive/years/999999/classes", {}),
        (
            "get",
            "/api/archive/classes/999999/grid?semester=1&subject=english",
            {},
        ),
        ("get", "/api/archive/students/999999/history", {}),
        (
            "get",
            "/api/coordinator/classes/999999/missing?subject=english&semester_id=999999",
            {},
        ),
        ("post", "/api/exports/year/999999", {}),
    ],
)
async def test_teacher_cannot_probe_privileged_object_routes(
    api, world, method: str, path: str, kwargs: dict
) -> None:
    """Every path-id outside the teacher surface must reject before lookup.

    Deliberately nonexistent ids also prove that these endpoints do not become
    existence oracles for authenticated teachers.
    """
    async with api(world.main) as client:
        response = await client.request(method, path, **kwargs)

    assert response.status_code == 403, (method, path, response.text)


async def test_teacher_cannot_read_another_teachers_job(api, world) -> None:
    async with TestSession() as db:
        job = m.JobRun(
            kind="progress_pdf",
            status="queued",
            requested_by=world.skills.id,
            payload={"semester_id": world.semester},
            progress=0,
            total=1,
        )
        db.add(job)
        await db.commit()
        job_id = job.id

    async with api(world.main) as client:
        detail = await client.get(f"/api/jobs/{job_id}")
        download = await client.get(f"/api/jobs/{job_id}/download")

    for response in (detail, download):
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "forbidden"


def test_xlsx_zip_bomb_is_rejected_before_openpyxl_expands_it() -> None:
    source = io.BytesIO(_workbook_bytes())
    with zipfile.ZipFile(source, mode="a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/oversized.bin", b"0" * (51 * 1024 * 1024))

    with pytest.raises(InvalidWorkbook, match="xlsx_archive_too_large"):
        parse_workbook(source.getvalue())


async def test_spreadsheet_formula_text_is_neutralized_in_audit_csv(api, world) -> None:
    formula = '=HYPERLINK("https://attacker.example/", "open")'
    async with TestSession() as db:
        user = await db.get(m.User, world.main.id)
        assert user is not None
        user.full_name = formula
        await db.commit()

    async with api(world.main) as client:
        saved = await client.post(
            f"/api/classes/{world.cls}/grid/save",
            json={
                "subject": "english",
                "cells": [cell(world.student_one, world.main_column, 90)],
            },
        )
    assert saved.status_code == 200

    async with api(world.admin) as client:
        exported = await client.get("/api/audit/export.csv")
    assert exported.status_code == 200
    escaped = formula.replace('"', '""')
    assert f'"\'{escaped}"' in exported.text


async def test_rate_limit_returns_retry_after_without_storing_raw_identity(monkeypatch) -> None:
    evaluate = AsyncMock(side_effect=[(20, 42), (21, 41)])
    monkeypatch.setattr(rate_limit, "client", lambda: SimpleNamespace(eval=evaluate))
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/login",
            "headers": [],
            "client": ("192.0.2.20", 1234),
        }
    )

    await rate_limit.enforce_rate_limit(request, scope="test", limit=20, window_seconds=60)
    with pytest.raises(HTTPException) as caught:
        await rate_limit.enforce_rate_limit(request, scope="test", limit=20, window_seconds=60)

    assert caught.value.status_code == 429
    assert caught.value.headers == {"Retry-After": "41"}
    redis_key = evaluate.await_args_list[0].args[2]
    assert "192.0.2.20" not in redis_key
