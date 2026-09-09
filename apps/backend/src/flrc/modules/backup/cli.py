"""``flrc backup`` commands (ADR-056)."""

import json

import typer

from flrc.config import settings
from flrc.modules.backup import crypto, run
from flrc.modules.backup.drive import DriveStore, Store
from flrc.modules.backup.status import read_status

app = typer.Typer(help="School backups: encrypted nightly dumps, restore tests, year archives.")


def _store() -> Store:
    missing = [
        name
        for name, value in (
            ("GDRIVE_SERVICE_ACCOUNT_JSON", settings.gdrive_service_account_json),
            ("GDRIVE_BACKUP_FOLDER_ID", settings.gdrive_backup_folder_id),
            ("BACKUP_AGE_RECIPIENT", settings.backup_age_recipient),
        )
        if not value.strip()
    ]
    if missing:
        raise typer.BadParameter("set " + ", ".join(missing), param_hint="environment")
    return DriveStore(settings.gdrive_service_account_json)


@app.command("run")
def run_once() -> None:
    """Dump, encrypt, upload, prune, and record status."""
    result = run.run_backup(_store())
    typer.echo(f"backup uploaded: {result['last_file']} ({result['last_bytes']} bytes)")


@app.command("restore-test")
def restore_test() -> None:
    """Download the newest copy, decrypt, restore into a scratch database, and check it."""
    if not settings.backup_age_identity.strip():
        raise typer.BadParameter("set BACKUP_AGE_IDENTITY", param_hint="environment")
    outcome = run.run_restore_test(_store())
    typer.echo(json.dumps(outcome, sort_keys=True))


@app.command("archives")
def archives() -> None:
    """Bundle every archived academic year that has no bundle in Drive yet."""
    done = run.run_year_archives(_store())
    typer.echo("archived: " + (", ".join(done) if done else "nothing new"))


@app.command("archive-year")
def archive_year(
    label: str = typer.Argument(..., help="Academic year label, e.g. 2026-2027"),
) -> None:
    """Build and upload one year's bundle, even if one exists already."""
    record = run.archive_year(_store(), label)
    typer.echo(f"archived {label}: {record['files']} files")


@app.command("schedule")
def schedule_forever() -> None:
    """Run as the backup sidecar: nightly at BACKUP_AT in BACKUP_TIMEZONE."""
    _store()  # fail fast on missing configuration
    run.run_forever(_store)


@app.command("status")
def status() -> None:
    """Print the status file."""
    typer.echo(json.dumps(read_status(run.backup_dir()), indent=2, sort_keys=True))


@app.command("keygen")
def keygen() -> None:
    """Generate an age key pair. Keep the identity in the school's password manager."""
    identity, recipient = crypto.generate_identity()
    typer.echo(f"BACKUP_AGE_RECIPIENT={recipient}")
    typer.echo(f"BACKUP_AGE_IDENTITY={identity}")
