# SPDX-FileCopyrightText: 2024-present Guest Database Manager <admin@example.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the CLI module."""

from pathlib import Path

import pytest

from guest_database_manager.cli import clean_database, create_parser, import_data
from guest_database_manager.constants import DEFAULT_DB_PATH


def test_create_parser_uses_default_database_path():
    """CLI subcommands should default to the shared database path."""
    parser = create_parser()

    import_args = parser.parse_args(["import", "sample.csv"])
    stats_args = parser.parse_args(["stats"])
    clean_args = parser.parse_args(["clean"])

    expected_path = Path(DEFAULT_DB_PATH)
    assert import_args.db == expected_path
    assert stats_args.db == expected_path
    assert clean_args.db == expected_path


def test_import_data_prints_database_stats(monkeypatch, capsys, tmp_path):
    """Import output should match the GuestDatabase return shape."""

    class StubDatabase:
        def __init__(self, db_path):
            self.db_path = db_path

        def add_guest_from_csv(self, file_path):
            assert file_path.name == "guests.csv"
            return {"imported": 2, "updated": 1, "skipped": 0, "errors": 0}

    csv_path = tmp_path / "guests.csv"
    csv_path.write_text("Name,Email\nJane,jane@example.com\n", encoding="utf-8")

    monkeypatch.setattr("guest_database_manager.cli.GuestDatabase", StubDatabase)

    import_data(csv_path, tmp_path / "guests.db")

    output = capsys.readouterr().out
    assert "Import successful" in output
    assert "New guests: 2" in output
    assert "Updated guests: 1" in output


def test_clean_database_reports_no_changes(monkeypatch, capsys, tmp_path):
    """Cleaning an already clean database should be a non-error path."""

    class StubDatabase:
        def __init__(self, db_path):
            self.db_path = db_path

        def clean_database(self):
            return {"removed": 0, "fixed": 0}

    monkeypatch.setattr("guest_database_manager.cli.GuestDatabase", StubDatabase)

    clean_database(tmp_path / "guests.db")

    output = capsys.readouterr().out
    assert "already clean" in output


def test_import_data_exits_on_import_errors(monkeypatch, tmp_path):
    """Import should exit non-zero when the database reports row-level errors."""

    class StubDatabase:
        def __init__(self, db_path):
            self.db_path = db_path

        def add_guest_from_csv(self, file_path):
            return {"imported": 1, "updated": 0, "skipped": 2, "errors": 1}

    csv_path = tmp_path / "guests.csv"
    csv_path.write_text("Name,Email\nJane,jane@example.com\n", encoding="utf-8")

    monkeypatch.setattr("guest_database_manager.cli.GuestDatabase", StubDatabase)

    with pytest.raises(SystemExit) as exc_info:
        import_data(csv_path, tmp_path / "guests.db")

    assert exc_info.value.code == 1
