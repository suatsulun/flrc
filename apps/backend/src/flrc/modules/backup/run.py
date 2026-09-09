"""Backup orchestration (ADR-056).

Nightly: dump, encrypt, upload, keep the last N successful copies, record
status. Monthly: download the newest copy, decrypt, restore into a scratch
database, check it, record status. Whenever a year has been archived and has
no bundle yet: build and upload its archive.
"""

import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from flrc.config import settings
from flrc.db import models as m
from flrc.db.sync import sync_engine
from flrc.modules.backup import archive, crypto, dump, schedule
from flrc.modules.backup.drive import Store, ensure_folder
from flrc.modules.backup.status import now_iso, read_status, update_status

log = structlog.get_logger()

DUMP_SUFFIX = ".dump.age"
SIDECAR_SUFFIX = ".dump.age.sha256"
ARCHIVES_FOLDER = "archives"


def backup_dir() -> Path:
    return Path(settings.backup_dir)


def _work_dir() -> Path:
    work = backup_dir() / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    return work


def _stamp(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")


def run_backup(store: Store, *, now: datetime | None = None) -> dict[str, object]:
    """One nightly backup; raises ``BackupError`` after recording the failure."""
    moment = now or datetime.now(UTC)
    work = _work_dir()
    try:
        plain = work / f"flrc-{_stamp(moment)}.dump"
        dump.pg_dump(str(plain))
        plain_digest = archive.sha256_of(plain)
        encrypted = plain.with_name(plain.name + ".age")
        crypto.encrypt_file(plain, encrypted, settings.backup_age_recipient)
        plain.unlink()
        encrypted_digest = archive.sha256_of(encrypted)
        sidecar = encrypted.with_name(encrypted.name + ".sha256")
        sidecar.write_text(f"{encrypted_digest}  {encrypted.name}\n", encoding="utf-8")

        folder = settings.gdrive_backup_folder_id
        uploaded = store.upload(encrypted, folder)
        store.upload(sidecar, folder, "text/plain")
        pruned = prune(store, folder, settings.backup_retain)
        result = {
            "last_success_at": now_iso(),
            "last_file": encrypted.name,
            "last_file_id": uploaded.id,
            "last_bytes": encrypted.stat().st_size,
            "last_sha256_encrypted": encrypted_digest,
            "last_sha256_plain": plain_digest,
            "last_error": None,
            "pruned": pruned,
        }
        update_status(backup_dir(), **result)
        log.info("backup_finished", bytes=result["last_bytes"], pruned=pruned)
        return result
    except Exception as exc:
        code = str(exc) if isinstance(exc, dump.BackupError) else type(exc).__name__
        update_status(backup_dir(), last_error=code, last_failure_at=now_iso())
        log.error("backup_failed", error=code)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


def prune(store: Store, folder_id: str, retain: int) -> int:
    """Keep the newest ``retain`` dumps; a failed night never shrinks the set."""
    files = store.list_files(folder_id)
    dumps = sorted(
        (item for item in files if item.name.endswith(DUMP_SUFFIX)),
        key=lambda item: item.created,
        reverse=True,
    )
    sidecars = {item.name: item for item in files if item.name.endswith(SIDECAR_SUFFIX)}
    removed = 0
    for old in dumps[retain:]:
        store.delete(old.id)
        removed += 1
        companion = sidecars.get(old.name + ".sha256")
        if companion is not None:
            store.delete(companion.id)
    return removed


def run_restore_test(store: Store) -> dict[str, object]:
    """Prove the newest remote copy restores: download, verify, decrypt, restore, count."""
    work = _work_dir()
    try:
        files = store.list_files(settings.gdrive_backup_folder_id)
        dumps = sorted(
            (item for item in files if item.name.endswith(DUMP_SUFFIX)),
            key=lambda item: item.created,
            reverse=True,
        )
        if not dumps:
            raise dump.BackupError("no_backup_to_test")
        newest = dumps[0]
        encrypted = work / newest.name
        store.download(newest.id, encrypted)
        sidecar = next((item for item in files if item.name == newest.name + ".sha256"), None)
        if sidecar is not None:
            sidecar_path = work / sidecar.name
            store.download(sidecar.id, sidecar_path)
            expected = sidecar_path.read_text(encoding="utf-8").split()[0]
            if expected != archive.sha256_of(encrypted):
                raise dump.BackupError("checksum_mismatch")
        plain = work / newest.name.removesuffix(".age")
        crypto.decrypt_file(encrypted, plain, settings.backup_age_identity)
        with dump.scratch_database() as scratch_url:
            dump.pg_restore(str(plain), url=scratch_url)
            result = inspect_restored(scratch_url)
        outcome = {
            "at": now_iso(),
            "ok": True,
            "file": newest.name,
            **result,
        }
        update_status(backup_dir(), last_restore_test=outcome)
        log.info("restore_test_finished", **result)
        return outcome
    except Exception as exc:
        code = str(exc) if isinstance(exc, dump.BackupError) else type(exc).__name__
        update_status(backup_dir(), last_restore_test={"at": now_iso(), "ok": False, "error": code})
        log.error("restore_test_failed", error=code)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


def inspect_restored(scratch_url: str) -> dict[str, object]:
    """Aggregate facts about a restored database; never row contents."""
    from sqlalchemy import create_engine, func

    engine = create_engine(scratch_url.replace("postgresql://", "postgresql+psycopg://"))
    try:
        with Session(engine) as db:
            revision = archive.schema_revision(db)
            students = int(db.scalar(select(func.count()).select_from(m.Student)) or 0)
            grades = int(db.scalar(select(func.count()).select_from(m.GradeValue)) or 0)
            users = int(db.scalar(select(func.count()).select_from(m.User)) or 0)
    finally:
        engine.dispose()
    with Session(sync_engine()) as live:
        live_revision = archive.schema_revision(live)
    if revision != live_revision:
        raise dump.BackupError("schema_revision_mismatch")
    if students == 0 or users == 0:
        raise dump.BackupError("restored_database_empty")
    return {
        "schema_revision": revision,
        "students": students,
        "grade_values": grades,
        "users": users,
    }


def run_year_archives(store: Store) -> list[str]:
    """Bundle every archived year that has no bundle in Drive yet."""
    with Session(sync_engine()) as db:
        labels = list(
            db.scalars(
                select(m.AcademicYear.label)
                .where(m.AcademicYear.status == "archived")
                .order_by(m.AcademicYear.label)
            )
        )
    archives_id = ensure_folder(store, ARCHIVES_FOLDER, settings.gdrive_backup_folder_id)
    done: list[str] = []
    for label in labels:
        folder_id = store.find_folder(label, archives_id)
        if folder_id is not None and any(
            item.name == archive.MANIFEST for item in store.list_files(folder_id)
        ):
            continue
        archive_year(store, label)
        done.append(label)
    return done


def archive_year(store: Store, label: str) -> dict[str, object]:
    work = _work_dir() / f"archive-{label}"
    try:
        with Session(sync_engine()) as db:
            year = db.scalar(select(m.AcademicYear).where(m.AcademicYear.label == label))
            if year is None:
                raise dump.BackupError("unknown_year")
            files = archive.build_year_documents(db, year, work)
            counts = archive.year_counts(db, year.id)
            revision = archive.schema_revision(db)
        plain = work / f"{label}-database.dump"
        dump.pg_dump(str(plain))
        encrypted = plain.with_name(plain.name + ".age")
        crypto.encrypt_file(plain, encrypted, settings.backup_age_recipient)
        plain.unlink()
        files.append(encrypted)
        manifest = archive.write_manifest(
            work, label=label, files=files, counts=counts, revision=revision
        )
        archives_id = ensure_folder(store, ARCHIVES_FOLDER, settings.gdrive_backup_folder_id)
        folder_id = ensure_folder(store, label, archives_id)
        for path in files:
            store.upload(path, folder_id)
        store.upload(manifest, folder_id, "application/json")
        record = {
            "at": now_iso(),
            "files": len(files) + 1,
            "counts": counts,
            "folder_id": folder_id,
        }
        existing = read_status(backup_dir()).get("archives")
        archives: dict[str, object] = dict(existing) if isinstance(existing, dict) else {}
        archives[label] = record
        update_status(backup_dir(), archives=archives)
        log.info("year_archived_to_drive", label=label, files=record["files"])
        return record
    finally:
        shutil.rmtree(work.parent, ignore_errors=True)


def run_forever(store_factory) -> None:  # pragma: no cover - a loop around the pieces above
    """The sidecar's main loop: sleep until the next run, do the night's work, repeat."""
    while True:
        now = datetime.now(UTC)
        due = schedule.next_run(now, settings.backup_at, settings.backup_timezone)
        log.info("backup_scheduled", at=due.isoformat())
        time.sleep(max(1.0, (due - now).total_seconds()))
        store = store_factory()
        try:
            run_backup(store)
        except Exception:
            continue
        if schedule.is_restore_test_day(
            datetime.now(UTC), settings.backup_restore_test_day, settings.backup_timezone
        ):
            try:
                run_restore_test(store)
            except Exception:
                pass
        try:
            run_year_archives(store)
        except Exception as exc:
            update_status(backup_dir(), last_archive_error=type(exc).__name__)
            log.error("year_archive_failed", error=type(exc).__name__)
