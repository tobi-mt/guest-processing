"""Client for reusing Ask Mirror Talk episode and transcript data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import requests
from requests.auth import HTTPBasicAuth


class AskMirrorTalkClientError(Exception):
    """Raised when Ask Mirror Talk cannot be queried safely."""


@dataclass
class AskMirrorTalkClient:
    """Small read-only client for Ask Mirror Talk admin export endpoints."""

    base_url: str
    username: str
    password: str
    timeout: int = 30

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")

    def export_episodes(
        self,
        *,
        limit: int = 1000,
        search: str = "",
        include_transcript: bool = True,
    ) -> List[Dict[str, Any]]:
        """Fetch episode metadata and latest transcript text from Ask Mirror Talk."""
        try:
            response = requests.get(
                f"{self.base_url}/api/admin/episodes/export",
                params={
                    "limit": max(1, min(int(limit or 1000), 2000)),
                    "search": search or "",
                    "include_transcript": "true" if include_transcript else "false",
                },
                auth=HTTPBasicAuth(self.username, self.password),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise AskMirrorTalkClientError("Could not reach Ask Mirror Talk.") from exc

        if response.status_code in {401, 403}:
            raise AskMirrorTalkClientError("Ask Mirror Talk credentials were rejected.")
        if not response.ok:
            raise AskMirrorTalkClientError("Ask Mirror Talk transcript export failed.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise AskMirrorTalkClientError("Ask Mirror Talk returned invalid JSON.") from exc

        episodes = payload.get("episodes", [])
        if not isinstance(episodes, list):
            raise AskMirrorTalkClientError("Ask Mirror Talk returned an invalid episode payload.")
        return episodes
