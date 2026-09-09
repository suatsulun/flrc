"""The backup status file: machine-readable, human-readable, and outside the database.

``status.json`` lives in the backups folder that the deployment bind-mounts,
so an operator can read it over SSH and the freshness check can fail loudly
when a night was missed. It never contains names, values, or secrets.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

STATUS_FILE = "status.json"


def status_path(directory: Path) -> Path:
    return directory / STATUS_FILE


def read_status(directory: Path) -> dict[str, object]:
    path = status_path(directory)
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def update_status(directory: Path, **fields: object) -> dict[str, object]:
    """Merge fields into the status file atomically."""
    directory.mkdir(parents=True, exist_ok=True)
    current = read_status(directory)
    current.update(fields)
    current["updated_at"] = now_iso()
    path = status_path(directory)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return current


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
