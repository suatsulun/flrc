import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from typer.testing import CliRunner

from flrc import cli
from flrc.config import settings
from flrc.modules.backup import crypto, dump, run, schedule
from flrc.modules.backup.drive import RemoteFile
from flrc.modules.backup.status import read_status
from tests.conftest import TEST_URL_SYNC

runner = CliRunner()
FOLDER = "folder-backups"


@dataclass
class MemoryStore:
    """A Drive stand-in: folders and files by id, newest first on listing."""

    files: dict[str, tuple[str, str, bytes, str]] = field(
        default_factory=dict
    )  # id -> (folder, name, bytes, created)
    folders: dict[str, tuple[str, str]] = field(default_factory=dict)  # id -> (parent, name)
    clock: int = 0

    def _tick(self) -> str:
        self.clock += 1
        return f"2026-01-01T00:00:{self.clock:02d}Z"

    def upload(
        self, path: Path, folder_id: str, mime: str = "application/octet-stream"
    ) -> RemoteFile:
        file_id = f"file-{len(self.files) + 1}"
        created = self._tick()
        self.files[file_id] = (folder_id, path.name, path.read_bytes(), created)
        return RemoteFile(id=file_id, name=path.name, created=created)

    def seed(self, folder_id: str, name: str, data: bytes = b"x") -> RemoteFile:
        file_id = f"file-{len(self.files) + 1}"
        created = self._tick()
        self.files[file_id] = (folder_id, name, data, created)
        return RemoteFile(id=file_id, name=name, created=created)

    def list_files(self, folder_id: str) -> list[RemoteFile]:
        items = [
            RemoteFile(id=file_id, name=name, created=created)
            for file_id, (folder, name, _, created) in self.files.items()
            if folder == folder_id
        ]
        return sorted(items, key=lambda item: item.created, reverse=True)

    def delete(self, file_id: str) -> None:
        del self.files[file_id]

    def download(self, file_id: str, target: Path) -> None:
        target.write_bytes(self.files[file_id][2])

    def find_folder(self, name: str, parent_id: str) -> str | None:
        for folder_id, (parent, folder_name) in self.folders.items():
            if parent == parent_id and folder_name == name:
                return folder_id
        return None

    def create_folder(self, name: str, parent_id: str) -> str:
        folder_id = f"folder-{len(self.folders) + 1}"
        self.folders[folder_id] = (parent_id, name)
        return folder_id

    def names(self, folder_id: str) -> list[str]:
        return [item.name for item in self.list_files(folder_id)]


@pytest.fixture
def keys() -> tuple[str, str]:
    return crypto.generate_identity()


@pytest.fixture
def backup_settings(tmp_path: Path, monkeypatch, keys) -> Path:
    identity, recipient = keys
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "backups"))
    monkeypatch.setattr(settings, "backup_age_recipient", recipient)
    monkeypatch.setattr(settings, "backup_age_identity", identity)
    monkeypatch.setattr(settings, "gdrive_backup_folder_id", FOLDER)
    monkeypatch.setattr(settings, "backup_retain", 7)
    monkeypatch.setattr(run, "sync_engine", lambda: create_engine(TEST_URL_SYNC))
    return tmp_path / "backups"


@pytest.fixture
def fake_pg_dump(monkeypatch):
    def write_dump(target: str, *, url: str | None = None) -> None:
        Path(target).write_bytes(b"PGDMP synthetic dump " + target.encode())

    monkeypatch.setattr(dump, "pg_dump", write_dump)
    return write_dump


def test_age_roundtrip_and_identity_parsing(tmp_path: Path, keys) -> None:
    identity, recipient = keys
    plain = tmp_path / "plain.bin"
    plain.write_bytes(b"synthetic dump bytes")
    encrypted = tmp_path / "plain.bin.age"
    crypto.encrypt_file(plain, encrypted, recipient)
    assert encrypted.read_bytes() != plain.read_bytes()
    restored = tmp_path / "restored.bin"
    keygen_file = f"# created: today\n# public key: {recipient}\n{identity}\n"
    crypto.decrypt_file(encrypted, restored, keygen_file)
    assert restored.read_bytes() == b"synthetic dump bytes"
    with pytest.raises(ValueError):
        crypto.parse_identity("nothing here")


def test_libpq_url_translation() -> None:
    assert (
        dump.libpq_url("postgresql+asyncpg://u:p@postgres:5432/flrc?ssl=require")
        == "postgresql://u:p@postgres:5432/flrc?sslmode=require"
    )
    assert dump.url_for_database("postgresql://u:p@h/flrc?x=1", "postgres") == (
        "postgresql://u:p@h/postgres?x=1"
    )


def test_nightly_backup_uploads_encrypted_dump_and_prunes(
    backup_settings, fake_pg_dump, keys
) -> None:
    identity, _ = keys
    store = MemoryStore()
    for day in range(1, 9):  # eight older nights, newest last
        name = f"flrc-2025-12-{day:02d}T02-30-00Z.dump.age"
        store.seed(FOLDER, name)
        store.seed(FOLDER, name + ".sha256")

    result = run.run_backup(store, now=datetime(2026, 1, 9, 2, 30, tzinfo=UTC))

    names = store.names(FOLDER)
    dumps = [name for name in names if name.endswith(".dump.age")]
    assert len(dumps) == 7 and dumps[0] == "flrc-2026-01-09T02-30-00Z.dump.age"
    assert "flrc-2025-12-01T02-30-00Z.dump.age" not in names
    assert "flrc-2025-12-01T02-30-00Z.dump.age.sha256" not in names
    assert "flrc-2025-12-02T02-30-00Z.dump.age" not in names
    assert "flrc-2025-12-03T02-30-00Z.dump.age" in names
    assert result["pruned"] == 2
    uploaded = next(
        data for _, name, data, _ in store.files.values() if name == result["last_file"]
    )
    sidecar = next(
        data for _, name, data, _ in store.files.values() if name == result["last_file"] + ".sha256"
    )
    assert sidecar.decode().split()[0] == result["last_sha256_encrypted"]
    # The remote copy is readable with the school's identity and is the dump.
    encrypted = backup_settings / "check.age"
    encrypted.write_bytes(uploaded)
    plain = backup_settings / "check.dump"
    crypto.decrypt_file(encrypted, plain, identity)
    assert plain.read_bytes().startswith(b"PGDMP synthetic dump")
    status = read_status(backup_settings)
    assert status["last_error"] is None and status["last_file"] == result["last_file"]
    assert not (backup_settings / "work").exists()


def test_failed_dump_records_the_error_and_uploads_nothing(backup_settings, monkeypatch) -> None:
    def broken(target: str, *, url: str | None = None) -> None:
        raise dump.BackupError("pg_dump_exit_1")

    monkeypatch.setattr(dump, "pg_dump", broken)
    store = MemoryStore()
    with pytest.raises(dump.BackupError):
        run.run_backup(store)
    assert store.files == {}
    status = read_status(backup_settings)
    assert status["last_error"] == "pg_dump_exit_1"
    assert "last_failure_at" in status and "last_success_at" not in status


def test_prune_keeps_the_newest_uploads_only(backup_settings) -> None:
    # Retention counts successful uploads by upload time, so a failed night
    # never shrinks the set and file names play no part.
    store = MemoryStore()
    for day in (3, 1, 2):
        store.seed(FOLDER, f"flrc-2026-02-{day:02d}.dump.age")
    store.seed(FOLDER, "unrelated.txt")
    assert run.prune(store, FOLDER, retain=2) == 1
    assert sorted(store.names(FOLDER)) == [
        "flrc-2026-02-01.dump.age",
        "flrc-2026-02-02.dump.age",
        "unrelated.txt",
    ]


def test_restore_test_downloads_verifies_decrypts_and_inspects(
    backup_settings, fake_pg_dump, monkeypatch, keys
) -> None:
    store = MemoryStore()
    run.run_backup(store)
    restored: list[str] = []
    monkeypatch.setattr(dump, "pg_restore", lambda source, *, url: restored.append(source))

    class FakeScratch:
        def __enter__(self):
            return "postgresql://scratch/flrc_restore_check"

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(dump, "scratch_database", lambda url=None: FakeScratch())
    monkeypatch.setattr(
        run,
        "inspect_restored",
        lambda url: {"schema_revision": "abc", "students": 5, "grade_values": 9, "users": 2},
    )
    outcome = run.run_restore_test(store)
    assert outcome["ok"] is True and outcome["students"] == 5
    assert restored and restored[0].endswith(".dump")
    assert read_status(backup_settings)["last_restore_test"]["ok"] is True


def test_restore_test_rejects_a_corrupted_remote_copy(backup_settings, fake_pg_dump) -> None:
    store = MemoryStore()
    result = run.run_backup(store)
    file_id = str(result["last_file_id"])
    folder, name, _, created = store.files[file_id]
    store.files[file_id] = (folder, name, b"corrupted bytes", created)
    with pytest.raises(dump.BackupError, match="checksum_mismatch"):
        run.run_restore_test(store)
    assert read_status(backup_settings)["last_restore_test"]["ok"] is False


def test_next_run_is_the_next_local_occurrence() -> None:
    before = datetime(2026, 9, 9, 20, 0, tzinfo=UTC)  # 23:00 Istanbul
    assert schedule.next_run(before, "02:30", "Europe/Istanbul") == datetime(
        2026, 9, 9, 23, 30, tzinfo=UTC
    )
    after = datetime(2026, 9, 9, 23, 45, tzinfo=UTC)  # 02:45 Istanbul, already past
    assert schedule.next_run(after, "02:30", "Europe/Istanbul") == datetime(
        2026, 9, 10, 23, 30, tzinfo=UTC
    )
    assert schedule.is_restore_test_day(
        datetime(2026, 9, 30, 22, 0, tzinfo=UTC), 1, "Europe/Istanbul"
    )


async def test_year_archive_bundles_documents_dump_and_manifest(
    backup_settings, fake_pg_dump, world, keys
) -> None:
    identity, _ = keys
    engine = create_engine(TEST_URL_SYNC)
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE academic_years SET status = 'archived'")
    engine.dispose()
    store = MemoryStore()

    done = run.run_year_archives(store)

    assert done == ["Synthetic year"]
    archives_id = store.find_folder("archives", FOLDER)
    assert archives_id is not None
    year_folder = store.find_folder("Synthetic year", archives_id)
    assert year_folder is not None
    names = sorted(store.names(year_folder))
    assert "manifest.json" in names
    assert "Synthetic year-export.xlsx" in names
    assert "Synthetic year-database.dump.age" in names
    assert any(name.endswith("-english_middle.pdf") for name in names)
    manifest = json.loads(
        next(data for _, name, data, _ in store.files.values() if name == "manifest.json")
    )
    assert manifest["label"] == "Synthetic year"
    assert manifest["counts"]["enrollments"] == 2 and manifest["counts"]["classes"] == 1
    assert {entry["name"] for entry in manifest["files"]} == set(names) - {"manifest.json"}
    assert all(len(entry["sha256"]) == 64 for entry in manifest["files"])
    # Idempotent: a second pass finds the manifest and does nothing.
    assert run.run_year_archives(store) == []
    assert "Synthetic year" in read_status(backup_settings)["archives"]


def test_backup_cli_keygen_and_missing_configuration(monkeypatch) -> None:
    generated = runner.invoke(cli.app, ["backup", "keygen"])
    assert generated.exit_code == 0
    assert "BACKUP_AGE_RECIPIENT=age1" in generated.output
    assert "BACKUP_AGE_IDENTITY=AGE-SECRET-KEY-1" in generated.output
    monkeypatch.setattr(settings, "gdrive_service_account_json", "")
    refused = runner.invoke(cli.app, ["backup", "run"])
    assert refused.exit_code != 0
    assert "GDRIVE_SERVICE_ACCOUNT_JSON" in refused.output
