"""Validate and normalize Apollo contact exports without importing sensitive extras."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any, Dict, List
from urllib.parse import urlparse


class ApolloImportError(ValueError):
    pass


REQUIRED_COLUMNS = {"First Name", "Last Name", "Title", "Company Name", "Email", "Email Status", "Website", "Person Linkedin Url"}


def parse_apollo_contacts_csv(csv_text: str, *, max_rows: int = 500) -> List[Dict[str, Any]]:
    if len(csv_text.encode("utf-8")) > 2_000_000:
        raise ApolloImportError("Apollo CSV must be smaller than 2 MB.")
    reader = csv.DictReader(StringIO(csv_text.lstrip("\ufeff")))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise ApolloImportError(f"Apollo CSV is missing required columns: {', '.join(sorted(missing))}.")
    contacts = []
    seen_emails = set()
    for index, row in enumerate(reader, start=2):
        if len(contacts) >= max_rows:
            raise ApolloImportError(f"Apollo CSV exceeds the {max_rows}-row import limit.")
        email = str(row.get("Email") or "").strip().casefold()
        website = str(row.get("Website") or "").strip()
        company = str(row.get("Company Name") or "").strip()
        if not company or not email or "@" not in email or email in seen_emails:
            continue
        parsed = urlparse(website)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        seen_emails.add(email)
        status = str(row.get("Email Status") or "").strip().casefold()
        catch_all = str(row.get("Primary Email Catch-all Status") or "").strip().casefold() == "catch-all"
        contacts.append({
            "row_number": index,
            "organisation_name": company,
            "website": website,
            "contact_name": " ".join(part for part in (str(row.get("First Name") or "").strip(), str(row.get("Last Name") or "").strip()) if part),
            "contact_email": email,
            "role_title": str(row.get("Title") or "").strip(),
            "industry": str(row.get("Industry") or "").strip(),
            "country": str(row.get("Country") or "").strip(),
            "confidence": "high" if status == "verified" and not catch_all else "medium",
            "verification_status": "verified_catch_all" if status == "verified" and catch_all else status or "unknown",
            "source_url": str(row.get("Person Linkedin Url") or "").strip() or website,
            "provider_record_id": str(row.get("Apollo Contact Id") or row.get("Apollo Record Id") or "").strip(),
            "last_verified_at": str(row.get("Primary Email Last Verified At") or "").strip(),
        })
    if not contacts:
        raise ApolloImportError("Apollo CSV contains no usable verified business contacts.")
    return contacts
