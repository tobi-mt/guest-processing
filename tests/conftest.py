# SPDX-FileCopyrightText: 2024-present Guest Database Manager <admin@example.com>
#
# SPDX-License-Identifier: MIT
"""Test configuration for Guest Database Manager."""

import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the parent directory is in sys.path for module resolution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guest_database_manager.database import GuestDatabase


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
        yield GuestDatabase(db_path)
        # Cleanup
        if db_path.exists():
            db_path.unlink()


@pytest.fixture
def sample_csv_file(tmp_path):
    """Create a temporary CSV file for testing."""
    sample_csv_content = """Name,Full name,Email,Website
John Doe,John Doe,john@example.com,https://johndoe.com
Jane Smith,Jane Smith,jane@example.com,
Alice Johnson,,alice@example.com,https://alice.blog
"""
    csv_file = tmp_path / "test_guests.csv"
    csv_file.write_text(sample_csv_content)
    return csv_file
