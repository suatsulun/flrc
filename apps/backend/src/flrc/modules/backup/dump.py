"""PostgreSQL dump and restore through the client tools (ADR-056).

The image carries the PostgreSQL 18 client so ``pg_dump`` matches the server
major. Connection strings never reach logs: failures are reported by code.
"""

import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit

import psycopg

from flrc.config import settings

SCRATCH_DATABASE = "flrc_restore_check"


class BackupError(RuntimeError):
    """A backup step failed; the message is a machine code, never a secret."""


def libpq_url(url: str | None = None) -> str:
    """The SQLAlchemy URL as libpq understands it."""
    value = url or settings.database_url_direct
    value = value.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )
    return value.replace("ssl=require", "sslmode=require")


def url_for_database(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment))


def _run(command: list[str], code: str) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=60 * 60)
    except FileNotFoundError as exc:
        raise BackupError(f"{code}_tool_missing") from exc
    except subprocess.TimeoutExpired as exc:
        raise BackupError(f"{code}_timeout") from exc
    except subprocess.CalledProcessError as exc:
        raise BackupError(f"{code}_exit_{exc.returncode}") from exc


def pg_dump(target: str, *, url: str | None = None) -> None:
    _run(
        [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            f"--file={target}",
            f"--dbname={libpq_url(url)}",
        ],
        "pg_dump",
    )


def pg_restore(source: str, *, url: str) -> None:
    _run(
        [
            "pg_restore",
            "--no-owner",
            "--no-privileges",
            "--exit-on-error",
            f"--dbname={url}",
            source,
        ],
        "pg_restore",
    )


@contextmanager
def scratch_database(url: str | None = None) -> Iterator[str]:
    """A throwaway database on the same server, dropped afterwards."""
    base = libpq_url(url)
    admin = url_for_database(base, "postgres")
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{SCRATCH_DATABASE}" WITH (FORCE)')
        connection.execute(f'CREATE DATABASE "{SCRATCH_DATABASE}"')
    try:
        yield url_for_database(base, SCRATCH_DATABASE)
    finally:
        with psycopg.connect(admin, autocommit=True) as connection:
            connection.execute(f'DROP DATABASE IF EXISTS "{SCRATCH_DATABASE}" WITH (FORCE)')
