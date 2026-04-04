"""Public-profile research helpers for guest copilot suggestions."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from http.client import InvalidURL
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


USER_AGENT = "MirrorTalkGuestCopilot/1.0 (+https://mirrortalkpodcast.com)"
MAX_SOURCES = 3
FETCH_TIMEOUT_SECONDS = 8
GENERIC_SOURCE_PATTERNS = (
    r"create an account or log in to instagram",
    r"log in to facebook",
    r"sign in to facebook",
    r"join facebook",
    r"login • instagram",
)

STOPWORDS = {
    "about", "after", "also", "been", "being", "because", "between", "build", "coach", "community",
    "episode", "experience", "focus", "from", "guest", "have", "help", "into", "journey", "lead",
    "more", "their", "there", "these", "they", "through", "with", "work", "works", "your",
}

TOPIC_KEYWORDS = {
    "faith": "Faith",
    "spiritual": "Spirituality",
    "healing": "Healing",
    "mental": "Mental Health",
    "wellness": "Wellness",
    "mindset": "Mindset",
    "purpose": "Purpose",
    "leadership": "Leadership",
    "business": "Business",
    "career": "Career",
    "relationship": "Relationships",
    "family": "Family",
    "trauma": "Trauma",
    "grief": "Grief",
    "resilience": "Resilience",
    "identity": "Identity",
    "story": "Storytelling",
    "podcast": "Podcasting",
    "author": "Authorship",
    "book": "Books",
    "speaker": "Speaking",
    "coach": "Coaching",
    "therap": "Therapy",
    "entrepreneur": "Entrepreneurship",
}

TIMELY_SIGNAL_PATTERNS = (
    (r"\bbook\b|\bauthor\b", "public profile highlights books or authorship"),
    (r"\bpodcast\b|\bhost\b", "public profile shows active podcast or media presence"),
    (r"\bfounder\b|\bco-founder\b", "public profile highlights a founder or builder story"),
    (r"\bspeaker\b|\bkeynote\b", "public profile emphasizes speaking experience"),
    (r"\bcoach\b|\bmentor\b", "public profile points to coaching or mentoring work"),
    (r"\btherap", "public profile points to therapeutic or mental health work"),
)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_text(value: Any) -> str:
    return _clean_text(value).casefold()


def _website_with_scheme(value: str) -> str:
    text = _clean_text(value)
    if text and not re.match(r"^[a-z]+://", text, flags=re.IGNORECASE):
        return f"https://{text}"
    return text


def _split_url_like_values(value: Any) -> list[str]:
    """Split multiline or comma-separated profile fields into individual URL-like entries."""
    text = _clean_text(value)
    if not text:
        return []
    extracted_urls = re.findall(r"https?://[^\s\],)]+|www\.[^\s\],)]+", text, flags=re.IGNORECASE)
    if extracted_urls:
        return [item.strip() for item in extracted_urls if item.strip()]
    parts = [
        chunk.strip()
        for chunk in re.split(r"[\r\n,;]+", text)
        if chunk and chunk.strip()
    ]
    return parts


def _candidate_urls(guest: Dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for website_value in _split_url_like_values(guest.get("website")):
        website = _website_with_scheme(website_value)
        if website:
            urls.append(website)

    social_text = _clean_text(guest.get("social_media_handles"))
    for line in social_text.splitlines():
        entry = line.strip()
        if not entry:
            continue
        labeled_match = re.match(r"^([^:]+):\s*(.+)$", entry)
        label = ""
        value = entry
        if labeled_match:
            label = labeled_match.group(1).strip().casefold()
            value = labeled_match.group(2).strip()

        if re.match(r"^https?://", value, flags=re.IGNORECASE):
            urls.append(value)
            continue

        handle = value.lstrip("@")
        if label == "instagram":
            urls.append(f"https://www.instagram.com/{handle}")
        elif label == "youtube":
            urls.append(f"https://www.youtube.com/@{handle}")
        elif label in {"x/twitter", "twitter", "x"}:
            urls.append(f"https://x.com/{handle}")
        elif label == "facebook":
            urls.append(f"https://www.facebook.com/{handle}")
        elif label == "tiktok":
            urls.append(f"https://www.tiktok.com/@{handle}")
        elif label == "linkedin":
            if value.startswith("linkedin.com/"):
                urls.append(f"https://{value}")

    unique: list[str] = []
    seen = set()
    for url in urls:
        key = url.casefold()
        if url and key not in seen:
            seen.add(key)
            unique.append(url)
    return unique[:MAX_SOURCES]


def _strip_tags(raw_html: str) -> str:
    without_scripts = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw_html)
    text = re.sub(r"(?s)<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _extract_meta(raw_html: str, key: str) -> str:
    pattern = rf'(?is)<meta[^>]+(?:name|property)=["\']{re.escape(key)}["\'][^>]+content=["\'](.*?)["\']'
    match = re.search(pattern, raw_html)
    return html.unescape(match.group(1)).strip() if match else ""


def _extract_title(raw_html: str) -> str:
    match = re.search(r"(?is)<title>(.*?)</title>", raw_html)
    return html.unescape(match.group(1)).strip() if match else ""


def _extract_heading(raw_html: str) -> str:
    match = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", raw_html)
    if not match:
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", match.group(1)))).strip()


def _fetch_page(url: str) -> dict[str, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en"})
    with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            return {"url": url, "title": "", "description": "", "heading": "", "text": ""}
        raw_html = response.read(120_000).decode("utf-8", errors="ignore")
    return {
        "url": url,
        "title": _extract_title(raw_html),
        "description": _extract_meta(raw_html, "description") or _extract_meta(raw_html, "og:description"),
        "heading": _extract_heading(raw_html),
        "text": _strip_tags(raw_html)[:4000],
    }


def _topic_matches(text: str) -> list[str]:
    normalized = _normalize_text(text)
    labels: list[str] = []
    for needle, label in TOPIC_KEYWORDS.items():
        if needle in normalized and label not in labels:
            labels.append(label)
    return labels[:5]


def _timely_signals(text: str) -> list[str]:
    normalized = _normalize_text(text)
    signals: list[str] = []
    for pattern, label in TIMELY_SIGNAL_PATTERNS:
        if re.search(pattern, normalized) and label not in signals:
            signals.append(label)
    return signals[:4]


def _evidence_snippets(source: dict[str, str]) -> list[str]:
    snippets = [source.get("description", ""), source.get("heading", ""), source.get("title", "")]
    clean = [snippet for snippet in snippets if snippet]
    return clean[:2]


def _summary_from_research(topics: list[str], sources: list[dict[str, Any]]) -> str:
    if topics:
        lead = ", ".join(topics[:3])
        return f"Public profile research suggests strong conversation angles around {lead.lower()}."
    for source in sources:
        description = _clean_text(source.get("description"))
        if description:
            return description
    return ""


def _is_generic_source(source: dict[str, Any]) -> bool:
    combined = _normalize_text(" ".join([
        source.get("title", ""),
        source.get("description", ""),
        source.get("heading", ""),
    ]))
    return any(re.search(pattern, combined) for pattern in GENERIC_SOURCE_PATTERNS)


def research_guest_from_public_web(guest: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch a few public profile pages and extract grounded copilot notes."""
    urls = _candidate_urls(guest)
    if not urls:
        raise ValueError("Add a website or labeled social profile before running web research.")

    fetched_sources: list[dict[str, Any]] = []
    evidence_texts: list[str] = []
    errors: list[str] = []

    for url in urls:
        try:
            source = _fetch_page(url)
        except (HTTPError, URLError, TimeoutError, ValueError, InvalidURL) as exc:
            errors.append(f"{url}: {exc}")
            continue
        source["host"] = urlparse(url).netloc
        source["evidence"] = _evidence_snippets(source)
        if _is_generic_source(source):
            errors.append(f"{url}: generic social/login page")
            continue
        if source["title"] or source["description"] or source["heading"]:
            fetched_sources.append(source)
            evidence_texts.extend(source["evidence"])

    if not fetched_sources:
        detail = errors[0] if errors else "No readable public profile text was found."
        raise ValueError(f"Public web research could not find usable profile information. {detail}")

    combined_text = "\n".join(
        part
        for source in fetched_sources
        for part in [source.get("title"), source.get("description"), source.get("heading"), source.get("text")]
        if part
    )
    topics = _topic_matches(combined_text)
    signals = _timely_signals(combined_text)
    summary = _summary_from_research(topics, fetched_sources)

    if not topics and not signals and not summary:
        detail = errors[0] if errors else "The available pages did not contain enough meaningful profile information."
        raise ValueError(f"Public web research could not find usable profile information. {detail}")

    return {
        "summary": summary,
        "likely_topics": topics,
        "timely_signals": signals,
        "sources": [
            {
                "url": source["url"],
                "host": source["host"],
                "title": source.get("title", ""),
                "description": source.get("description", ""),
                "evidence": source.get("evidence", []),
            }
            for source in fetched_sources
        ],
        "evidence": evidence_texts[:4],
        "updated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    }
