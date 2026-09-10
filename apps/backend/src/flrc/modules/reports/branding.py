"""Optional private report overlay supplied by the school's deployment repo.

No school assets ship in the public application. The overlay is read only;
administrators upload teacher signatures separately into PostgreSQL.
"""

import base64
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from jinja2 import DictLoader, StrictUndefined
from jinja2.sandbox import SandboxedEnvironment
from pydantic import BaseModel, ConfigDict, Field

from flrc.config import settings

ReportKind = Literal["english_elementary", "english_middle", "german_karne", "french_karne"]


class Principal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    titles: dict[str, str] = Field(default_factory=dict)
    signature: str | None = None


class ReportBrandingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    templates: dict[ReportKind, str] = Field(default_factory=dict)
    principals: dict[Literal["primary", "middle"], Principal] = Field(default_factory=dict)
    assets: dict[str, str] = Field(default_factory=dict)
    covers: dict[Literal["german_karne", "french_karne"], str] = Field(default_factory=dict)


def contained_file(root: Path, relative: str) -> Path:
    """Reject traversal, absolute paths and symlinks out of the overlay."""
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError("report_asset_outside_branding")
    if not path.is_file():
        raise ValueError("report_asset_missing")
    return path


def asset_data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0]
    if mime not in {"image/png", "image/jpeg", "image/svg+xml"}:
        raise ValueError("report_asset_invalid_type")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


@dataclass(frozen=True)
class ReportBranding:
    root: Path
    config: ReportBrandingConfig

    def context(self) -> dict[str, object]:
        principals = {
            stage: {
                "name": principal.name,
                "titles": principal.titles,
                "signature": asset_data_uri(contained_file(self.root, principal.signature))
                if principal.signature
                else None,
            }
            for stage, principal in self.config.principals.items()
        }
        assets = {
            name: asset_data_uri(contained_file(self.root, relative))
            for name, relative in self.config.assets.items()
        }
        return {"principals": principals, "assets": assets}

    def environment(self, builtin: Path) -> SandboxedEnvironment:
        # Read only HTML files below the two explicit roots. DTOs and primitive
        # dictionaries are the only objects made available to private templates.
        sources = {path.name: path.read_text("utf-8") for path in builtin.glob("*.html")}
        template_root = self.root / "templates"
        if template_root.is_dir():
            for candidate in template_root.rglob("*.html"):
                relative = candidate.relative_to(template_root).as_posix()
                path = contained_file(self.root, "templates/" + relative)
                sources[relative] = path.read_text("utf-8")
        environment = SandboxedEnvironment(
            loader=DictLoader(sources), autoescape=True, undefined=StrictUndefined
        )
        environment.globals.clear()
        return environment


def report_branding() -> ReportBranding | None:
    if not settings.school_branding_dir:
        return None
    root = Path(settings.school_branding_dir) / "reports"
    config = root / "config.json"
    if not config.is_file():
        return None
    return ReportBranding(
        root=root,
        config=ReportBrandingConfig.model_validate(json.loads(config.read_text("utf-8"))),
    )
