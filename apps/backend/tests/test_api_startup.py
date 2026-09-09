import json
import os
import subprocess
from pathlib import Path

import pytest

START_SCRIPT = Path(__file__).parents[1] / "bin" / "start-api.sh"


def run_startup(tmp_path: Path, **environment: str) -> tuple[subprocess.CompletedProcess, list]:
    log = tmp_path / "commands.jsonl"
    for name in ("alembic", "flrc", "uvicorn"):
        executable = tmp_path / name
        executable.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "name = Path(sys.argv[0]).name\n"
            "with open(os.environ['COMMAND_LOG'], 'a') as log:\n"
            "    log.write(json.dumps([name, sys.argv[1:], "
            "os.environ.get('FLRC_MIGRATIONS_URL'), "
            "os.environ.get('DATABASE_URL_DIRECT')]) + '\\n')\n"
            "if name == 'alembic':\n"
            "    sys.exit(int(os.environ.get('MIGRATION_EXIT', '0')))\n"
            "if name == 'flrc':\n"
            "    sys.exit(int(os.environ.get('SEED_EXIT', '0')))\n"
        )
        executable.chmod(0o755)
    env = (
        os.environ
        | {
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "COMMAND_LOG": str(log),
            "DATABASE_URL_DIRECT": "",
            "FLRC_MIGRATIONS_URL": "unrelated-connection",
            "PORT": "8123",
        }
        | environment
    )
    result = subprocess.run(
        ["sh", str(START_SCRIPT)], env=env, capture_output=True, text=True, timeout=10
    )
    commands = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return result, commands


def test_demo_migrates_its_explicit_database_before_starting(tmp_path: Path) -> None:
    result, commands = run_startup(
        tmp_path, ENV="demo", DATABASE_URL_DIRECT="synthetic-demo-connection"
    )
    assert result.returncode == 0
    assert commands[0][:3] == ["alembic", ["upgrade", "head"], "synthetic-demo-connection"]
    assert commands[1][:2] == ["flrc", ["seed", "--demo"]]
    assert commands[2][0] == "uvicorn"
    assert commands[2][1] == [
        "flrc.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8123",
        "--proxy-headers",
        "--forwarded-allow-ips=*",
        "--no-access-log",
    ]


def test_demo_prepares_the_golden_branch_before_its_own(tmp_path: Path) -> None:
    result, commands = run_startup(
        tmp_path,
        ENV="demo",
        DATABASE_URL_DIRECT="synthetic-demo-connection",
        DATABASE_URL_GOLDEN_DIRECT="synthetic-golden-connection",
    )
    assert result.returncode == 0
    assert [command[0] for command in commands] == ["alembic", "flrc", "alembic", "uvicorn"]
    assert commands[0][1:3] == [["upgrade", "head"], "synthetic-golden-connection"]
    assert commands[1][1] == ["seed", "--demo"]
    assert commands[1][3] == "synthetic-golden-connection"
    assert commands[2][1:3] == [["upgrade", "head"], "synthetic-demo-connection"]


def test_failed_migration_prevents_api_startup(tmp_path: Path) -> None:
    result, commands = run_startup(
        tmp_path, ENV="demo", DATABASE_URL_DIRECT="synthetic-demo-connection", MIGRATION_EXIT="7"
    )
    assert result.returncode == 7
    assert [command[0] for command in commands] == ["alembic"]


def test_demo_requires_an_explicit_database(tmp_path: Path) -> None:
    result, commands = run_startup(tmp_path, ENV="demo")
    assert result.returncode != 0
    assert "DATABASE_URL_DIRECT" in result.stderr
    assert commands == []


def test_failed_seed_prevents_api_startup(tmp_path: Path) -> None:
    result, commands = run_startup(
        tmp_path, ENV="demo", DATABASE_URL_DIRECT="synthetic-demo-connection", SEED_EXIT="8"
    )
    assert result.returncode == 8
    assert [command[0] for command in commands] == ["alembic", "flrc"]


@pytest.mark.parametrize("environment", ["school", "dev", "test"])
def test_other_environments_do_not_migrate_at_startup(tmp_path: Path, environment: str) -> None:
    result, commands = run_startup(tmp_path, ENV=environment)
    assert result.returncode == 0
    assert [command[0] for command in commands] == ["uvicorn"]
