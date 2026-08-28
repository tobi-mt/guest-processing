"""Minimal server-side Apollo client for partner decision-maker enrichment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

import requests


class ApolloClientError(RuntimeError):
    """Apollo could not complete a safe enrichment request."""


DEFAULT_TITLES = (
    "Partnerships Director", "Head of Partnerships", "Partnerships Manager",
    "Communications Director", "Head of Communications", "Public Relations Director",
    "Marketing Director", "Founder", "Executive Director",
)


@dataclass
class ApolloClient:
    api_key: str
    base_url: str = "https://api.apollo.io/api/v1"
    timeout_seconds: float = 12.0

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = requests.post(
                f"{self.base_url.rstrip('/')}/{path.lstrip('/')}",
                headers={"X-Api-Key": self.api_key, "Content-Type": "application/json", "Cache-Control": "no-cache"},
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            value = response.json()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            raise ApolloClientError(f"Apollo rejected the enrichment request (HTTP {status}).") from exc
        except requests.RequestException as exc:
            raise ApolloClientError("Apollo could not be reached.") from exc
        except (TypeError, ValueError) as exc:
            raise ApolloClientError("Apollo returned an unreadable response.") from exc
        if not isinstance(value, dict):
            raise ApolloClientError("Apollo returned an unexpected response.")
        return value

    def search_decision_makers(
        self, domain: str, *, titles: Iterable[str] = DEFAULT_TITLES, limit: int = 8
    ) -> List[Dict[str, Any]]:
        """Find likely partnership contacts, then enrich only the bounded shortlist."""
        domain = domain.strip().casefold().removeprefix("www.")
        if not domain or "." not in domain:
            raise ApolloClientError("A valid organisation domain is required for Apollo enrichment.")
        result = self._post("mixed_people/search", {
            "q_organization_domains_list": [domain],
            "person_titles": list(titles),
            "page": 1,
            "per_page": max(1, min(int(limit), 10)),
        })
        people = result.get("people") or result.get("contacts") or []
        normalized = []
        for person in people[:limit]:
            if not isinstance(person, dict):
                continue
            enriched = person
            if not str(person.get("email") or "").strip() and person.get("id"):
                try:
                    match = self._post("people/match", {
                        "id": person["id"], "reveal_personal_emails": False,
                        "reveal_phone_number": False,
                    })
                    enriched = match.get("person") or person
                except ApolloClientError:
                    enriched = person
            first = str(enriched.get("first_name") or "").strip()
            last = str(enriched.get("last_name") or "").strip()
            email = str(enriched.get("email") or "").strip()
            email_status = str(enriched.get("email_status") or "").strip().casefold()
            profile_url = str(enriched.get("linkedin_url") or person.get("linkedin_url") or "").strip()
            normalized.append({
                "provider_record_id": str(enriched.get("id") or person.get("id") or ""),
                "contact_name": " ".join(part for part in (first, last) if part),
                "contact_email": email,
                "role_title": str(enriched.get("title") or person.get("title") or "").strip(),
                "confidence": "high" if email and email_status in {"verified", "valid"} else ("medium" if email else "low"),
                "verification_status": email_status or ("available" if email else "not_returned"),
                "source_url": profile_url,
            })
        return normalized
