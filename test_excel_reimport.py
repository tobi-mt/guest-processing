#!/usr/bin/env python3
"""Verify that re-importing an Excel export does not duplicate guests."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from guest_database_manager.database import GuestDatabase


def test_excel_reimport(tmp_path: Path) -> None:
    db = GuestDatabase(tmp_path / "guests.db")
    export = tmp_path / "guests.xlsx"
    pd.DataFrame({
        "Name": ["QA Guest One", "QA Guest Two"],
        "Guest's Email": ["qa-one@example.com", "qa-two@example.com"],
    }).to_excel(export, index=False)

    first = db.import_from_excel(str(export))
    assert (first["imported"], first["updated"], first["errors"]) == (2, 0, 0)
    original_ids = {guest["email"]: guest["id"] for guest in db.get_all_guests()}

    repeated = db.import_from_excel(str(export))
    assert (repeated["imported"], repeated["updated"], repeated["errors"]) == (0, 2, 0)
    guests = db.get_all_guests()
    assert len(guests) == 2
    assert {guest["email"]: guest["id"] for guest in guests} == original_ids


if __name__ == "__main__":
    with TemporaryDirectory() as work:
        test_excel_reimport(Path(work))
