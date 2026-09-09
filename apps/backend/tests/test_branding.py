from pathlib import Path

from flrc.config import settings
from flrc.modules.reports import render


def _overlay(tmp_path: Path) -> Path:
    folder = tmp_path / "branding"
    folder.mkdir()
    (folder / "brand.json").write_text(
        '{"name": "Synthetic Overlay School", "accentColor": "#123456"}', encoding="utf-8"
    )
    (folder / "logo.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    return folder


def test_mounted_overlay_outranks_synced_assets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "school_branding_dir", str(_overlay(tmp_path)))
    monkeypatch.setattr(settings, "school_name", "")
    monkeypatch.setattr(settings, "school_logo_path", "")
    render.school_brand.cache_clear()
    try:
        brand = render.school_brand()
    finally:
        render.school_brand.cache_clear()
    assert brand.name == "Synthetic Overlay School"
    assert brand.accent == "#123456"
    assert brand.logo is not None
    assert brand.logo.startswith("data:image/svg+xml;base64,")


def test_environment_override_outranks_the_overlay(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "school_branding_dir", str(_overlay(tmp_path)))
    monkeypatch.setattr(settings, "school_name", "Synthetic Env School")
    render.school_brand.cache_clear()
    try:
        assert render.school_brand().name == "Synthetic Env School"
    finally:
        render.school_brand.cache_clear()


def test_missing_overlay_falls_back_to_synced_assets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "school_branding_dir", str(tmp_path / "absent"))
    monkeypatch.setattr(settings, "school_name", "")
    render.school_brand.cache_clear()
    try:
        brand = render.school_brand()
    finally:
        render.school_brand.cache_clear()
    assert brand.name == "FL-ReportCard"
