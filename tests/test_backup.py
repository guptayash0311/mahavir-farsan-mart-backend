from pathlib import Path

from scripts.backup import backup_command, restore_command


def test_backup_and_restore_commands() -> None:
    url = "postgresql+psycopg://mahavir:mahavir@localhost:5432/mahavir"
    backup = backup_command(url, Path("backups/mahavir.dump"))
    restore = restore_command(url, Path("backups/mahavir.dump"))
    assert backup[0] == "pg_dump"
    assert "postgresql://" in backup[-1]
    assert "+psycopg" not in backup[-1]
    assert restore[0] == "pg_restore"
    assert "--clean" in restore
