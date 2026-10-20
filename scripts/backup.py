"""Backup and restore helpers for PostgreSQL.

The runbook in docs/RUNBOOK.md is the procedure. This module builds the
commands and can run them when pg_dump and psql are on PATH.
"""

import argparse
import shlex
import subprocess
from pathlib import Path

from app.core.config import get_settings


def backup_command(database_url: str, destination: Path) -> list[str]:
    return ["pg_dump", "--format=custom", "--file", str(destination), database_url.replace("+psycopg", "")]


def restore_command(database_url: str, source: Path) -> list[str]:
    return ["pg_restore", "--clean", "--if-exists", "--dbname", database_url.replace("+psycopg", ""), str(source)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up or restore the Mahavir database")
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("path")
    args = parser.parse_args()
    database_url = get_settings().database_url
    target = Path(args.path)
    if args.action == "backup":
        target.parent.mkdir(parents=True, exist_ok=True)
        command = backup_command(database_url, target)
    else:
        command = restore_command(database_url, target)
    print(" ".join(shlex.quote(part) for part in command))
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
