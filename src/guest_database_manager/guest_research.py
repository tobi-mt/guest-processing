"""Public-profile research helpers for guest copilot suggestions."""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from http.client import InvalidURL
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, unquote, urlparse
from urllib.request import Request, urlopen


USER_AGENT = "MirrorTalkGuestCopilot/1.0 (+https://mirrortalkpodcast.com)"
MAX_SOURCES = 3
FETCH_TIMEOUT_SECONDS = 8
GENERIC_INSTAGRAM_RETRY_ATTEMPTS = 2
GOOGLE_SEARCH_URL = "https://www.google.com/search?q={query}&hl=en"
GENERIC_SOURCE_PATTERNS = (
    r"create an account or log in to instagram",
    r"log in to facebook",
    r"sign in to facebook",
    r"join facebook",
    r"login • instagram",
)
GENERIC_SOURCE_LABELS = {"facebook", "instagram"}

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
TIME_SENSITIVE_EVENT_WORDS = re.compile(
    r"\b(launch(?:es|ing)?|release(?:s|d|ing)?|publication|book tour|tour|conference|summit|keynote|appearance|premiere|opening)\b",
    flags=re.IGNORECASE,
)
EVENT_DATE_PATTERNS = (
    (re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b"), "%Y-%m-%d"),
    (
        re.compile(
            r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+20\d{2})\b",
            flags=re.IGNORECASE,
        ),
        "%B %d %Y",
    ),
)

RELEASE_MONTH_THEMES: dict[int, dict[str, Any]] = {
    1: {"label": "fresh starts and intentional growth", "keywords": ("purpose", "goal", "habit", "vision", "mindset", "career")},
    2: {"label": "love, belonging, and relationships", "keywords": ("love", "relationship", "marriage", "friendship", "family", "connection")},
    3: {"label": "courage, identity, and renewal", "keywords": ("women", "identity", "courage", "renewal", "growth", "leadership")},
    4: {"label": "healing, hope, and new life", "keywords": ("healing", "faith", "hope", "stress", "autism", "environment")},
    5: {"label": "mental health, caregiving, and motherhood", "keywords": ("mental", "wellness", "mother", "care", "family", "therapy")},
    6: {"label": "men's health, fatherhood, and community", "keywords": ("men", "father", "health", "wellness", "community", "resilience")},
    7: {"label": "freedom, calling, and leadership", "keywords": ("freedom", "purpose", "calling", "leadership", "service", "career")},
    8: {"label": "learning, preparation, and discipline", "keywords": ("school", "education", "learning", "discipline", "focus", "productivity")},
    9: {"label": "mental wellbeing, resilience, and renewed focus", "keywords": ("mental", "recovery", "resilience", "purpose", "focus", "identity")},
    10: {"label": "healing stories and courageous honesty", "keywords": ("healing", "trauma", "story", "mental", "faith", "transformation")},
    11: {"label": "gratitude, service, and legacy", "keywords": ("gratitude", "service", "community", "legacy", "impact", "family")},
    12: {"label": "hope, faith, rest, and reflection", "keywords": ("hope", "faith", "rest", "reflection", "family", "joy")},
}


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


def _search_query_parts(guest: Dict[str, Any]) -> list[str]:
    parts: list[str] = []
    full_name = _clean_text(guest.get("full_name") or guest.get("name"))
    if full_name:
        parts.append(f'"{full_name}"')

    website_value = _clean_text(guest.get("website"))
    website_bits = _split_url_like_values(website_value)
    if website_bits:
        website_host = re.sub(r"^https?://", "", website_bits[0], flags=re.IGNORECASE)
        website_host = re.sub(r"^www\.", "", website_host, flags=re.IGNORECASE).split("/")[0]
        if website_host:
            parts.append(website_host)
            return parts

    social_text = _clean_text(guest.get("social_media_handles") or guest.get("social_handles"))
    for line in social_text.splitlines():
        entry = line.strip()
        if not entry:
            continue
        labeled_match = re.match(r"^([^:]+):\s*(.+)$", entry)
        value = labeled_match.group(2).strip() if labeled_match else entry
        handle = value.lstrip("@").strip()
        if handle:
            parts.append(f'"{handle}"')
            break

    return parts


def _google_search_url(guest: Dict[str, Any]) -> str:
    parts = _search_query_parts(guest)
    if not parts:
        return ""
    return GOOGLE_SEARCH_URL.format(query=quote_plus(" ".join(parts)))


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


def _google_result_urls(raw_html: str) -> list[str]:
    candidates = re.findall(r'href="/url\?q=([^"&]+)', raw_html)
    urls: list[str] = []
    seen = set()
    for candidate in candidates:
        decoded = unquote(candidate)
        if not re.match(r"^https?://", decoded, flags=re.IGNORECASE):
            continue
        host = urlparse(decoded).netloc.casefold()
        if host.endswith("google.com") or host.endswith("googleusercontent.com"):
            continue
        if decoded.casefold() in seen:
            continue
        seen.add(decoded.casefold())
        urls.append(decoded)
        if len(urls) >= MAX_SOURCES:
            break
    return urls


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


def _time_sensitive_events(sources: list[dict[str, Any]], *, reference: datetime | None = None) -> list[dict[str, Any]]:
    """Extract dated launch/appearance signals without inventing missing dates."""
    reference = reference or datetime.now(timezone.utc)
    horizon = reference + timedelta(days=550)
    events: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source in sources:
        source_text = " ".join(
            _clean_text(source.get(field)) for field in ("title", "description", "heading", "text")
        )
        if not TIME_SENSITIVE_EVENT_WORDS.search(source_text):
            continue
        for pattern, date_format in EVENT_DATE_PATTERNS:
            for match in pattern.finditer(source_text):
                raw_date = re.sub(r"(\d)(st|nd|rd|th)", r"\1", match.group(1), flags=re.IGNORECASE)
                raw_date = raw_date.replace(",", "")
                try:
                    event_date = datetime.strptime(raw_date, date_format).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                if event_date.date() < reference.date() or event_date > horizon:
                    continue
                context_start = max(0, match.start() - 90)
                context_end = min(len(source_text), match.end() + 90)
                context = re.sub(r"\s+", " ", source_text[context_start:context_end]).strip(" .")
                word_match = TIME_SENSITIVE_EVENT_WORDS.search(context)
                if not word_match:
                    continue
                title = f"Guest {word_match.group(1).lower()}"
                key = (event_date.date().isoformat(), title)
                if key in seen:
                    continue
                seen.add(key)
                events.append(
                    {
                        "title": title,
                        "date": event_date.date().isoformat(),
                        "context": context[:240],
                        "source_url": _clean_text(source.get("url")),
                    }
                )
    events.sort(key=lambda item: item["date"])
    return events[:5]


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


def build_release_timing_recommendation(
    research: Dict[str, Any], *, reference: datetime | None = None
) -> Dict[str, Any]:
    """Build durable, evidence-linked prospective release windows for a guest."""
    reference = reference or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    signal_text = " ".join(
        _clean_text(item)
        for item in [
            *(research.get("likely_topics") or []),
            *(research.get("timely_signals") or []),
            research.get("summary"),
        ]
        if _clean_text(item)
    ).casefold()

    candidates: list[dict[str, Any]] = []
    year, month = reference.year, reference.month
    # Use full future months so a recommendation never points to a nearly
    # completed current-month window.
    for offset in range(1, 13):
        candidate_month = ((month - 1 + offset) % 12) + 1
        candidate_year = year + ((month - 1 + offset) // 12)
        theme = RELEASE_MONTH_THEMES[candidate_month]
        matched = [keyword for keyword in theme["keywords"] if keyword in signal_text]
        if not matched:
            continue
        start = datetime(candidate_year, candidate_month, 1, tzinfo=reference.tzinfo)
        next_month = datetime(candidate_year + (candidate_month == 12), (candidate_month % 12) + 1, 1, tzinfo=reference.tzinfo)
        end = next_month - timedelta(days=1)
        candidates.append(
            {
                "month": candidate_month,
                "year": candidate_year,
                "month_label": start.strftime("%B %Y"),
                "window_start": start.date().isoformat(),
                "window_end": end.date().isoformat(),
                "score": len(set(matched)),
                "matched_signals": list(dict.fromkeys(matched)),
                "rationale": f"Aligns with {theme['label']}.",
            }
        )

    for event in research.get("time_sensitive_events") or []:
        if not isinstance(event, dict):
            continue
        try:
            event_date = datetime.fromisoformat(_clean_text(event.get("date"))).replace(tzinfo=reference.tzinfo)
        except ValueError:
            continue
        if event_date.date() <= reference.date() or event_date > reference + timedelta(days=550):
            continue
        event_title = _clean_text(event.get("title")) or "guest event"
        candidates.append(
            {
                "month": event_date.month,
                "year": event_date.year,
                "month_label": event_date.strftime("%B %Y"),
                "window_start": (event_date - timedelta(days=21)).date().isoformat(),
                "window_end": (event_date + timedelta(days=7)).date().isoformat(),
                "score": 10,
                "matched_signals": [event_title],
                "rationale": f"Creates a timely release runway around {event_title} on {event_date.date().isoformat()}.",
                "event": dict(event),
            }
        )

    candidates.sort(key=lambda item: (-item["score"], item["year"], item["month"]))
    windows = candidates[:3]
    if windows:
        confidence = "high" if windows[0]["score"] >= 3 else "medium" if windows[0]["score"] >= 2 else "low"
        summary = f"Best prospective window: {windows[0]['month_label']} — {windows[0]['rationale']}"
    else:
        confidence = "low"
        summary = "No strong seasonal signal was found; treat this guest as evergreen and use the next editorially balanced opening."

    return {
        "status": "seasonal_match" if windows else "evergreen",
        "summary": summary,
        "confidence": confidence,
        "recommended_windows": windows,
        "basis": "Saved public-profile topics and timely signals; calendar capacity and episode readiness are evaluated later in Planning.",
        "generated_at": reference.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def _is_generic_source(source: dict[str, Any]) -> bool:
    title = _normalize_text(source.get("title", ""))
    description = _normalize_text(source.get("description", ""))
    heading = _normalize_text(source.get("heading", ""))
    combined = _normalize_text(" ".join([title, description, heading]))
    if any(re.search(pattern, combined) for pattern in GENERIC_SOURCE_PATTERNS):
        return True
    low_signal_parts = [part for part in (title, description, heading) if part]
    return bool(low_signal_parts) and all(part in GENERIC_SOURCE_LABELS for part in low_signal_parts)


def _is_instagram_url(url: str) -> bool:
    """Return whether a source is hosted by Instagram, including its www host."""
    host = urlparse(url).netloc.casefold().split(":", 1)[0]
    return host in {"instagram.com", "www.instagram.com"}


def research_guest_from_public_web(guest: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch a few public profile pages and extract grounded copilot notes."""
    urls = _candidate_urls(guest)
    if not urls:
        raise ValueError("Add a website or labeled social profile before running web research.")

    fetched_sources: list[dict[str, Any]] = []
    evidence_texts: list[str] = []
    errors: list[str] = []

    for url in urls:
        attempts = GENERIC_INSTAGRAM_RETRY_ATTEMPTS if _is_instagram_url(url) else 1
        source: dict[str, Any] | None = None
        for attempt in range(attempts):
            try:
                candidate = _fetch_page(url)
            except (HTTPError, URLError, TimeoutError, ValueError, InvalidURL) as exc:
                errors.append(f"{url}: {exc}")
                break
            if _is_generic_source(candidate) and attempt + 1 < attempts:
                continue
            source = candidate
            break

        if source is None:
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
    events = _time_sensitive_events(fetched_sources)
    summary = _summary_from_research(topics, fetched_sources)

    if not topics and not signals and not summary:
        detail = errors[0] if errors else "The available pages did not contain enough meaningful profile information."
        raise ValueError(f"Public web research could not find usable profile information. {detail}")

    return {
        "summary": summary,
        "likely_topics": topics,
        "timely_signals": signals,
        "time_sensitive_events": events,
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
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def research_guest_from_google_search(guest: Dict[str, Any]) -> Dict[str, Any]:
    """Use a Google search results page to find likely profile sources, then extract grounded notes."""
    search_url = _google_search_url(guest)
    if not search_url:
        raise ValueError("Add a guest name plus a website or social profile before retrying with search.")

    search_request = Request(search_url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en"})
    try:
        with urlopen(search_request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            raw_html = response.read(120_000).decode("utf-8", errors="ignore")
    except (HTTPError, URLError, TimeoutError, ValueError, InvalidURL) as exc:
        raise ValueError(f"Google search fallback could not load results. {exc}") from exc

    result_urls = _google_result_urls(raw_html)
    if not result_urls:
        raise ValueError("Google search fallback did not find any readable profile links.")

    rescued_guest = dict(guest)
    rescued_guest["website"] = "\n".join(result_urls[:MAX_SOURCES])
    research = research_guest_from_public_web(rescued_guest)
    research["search_fallback"] = {
        "query_url": search_url,
        "result_urls": result_urls[:MAX_SOURCES],
    }
    return research
