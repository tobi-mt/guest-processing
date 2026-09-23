"""Cross-workspace search and personal operating briefings."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from guest_database_manager.db_connection import connect_database


def _text(value: Any) -> str:
    return str(value or "").strip()


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _snippet(value: Any, query: str, *, limit: int = 120) -> str:
    text = " ".join(_text(value).split())
    if not text:
        return ""
    index = text.casefold().find(query.casefold())
    start = max(0, index - 35) if index >= 0 else 0
    result = text[start:start + limit]
    return ("…" if start else "") + result + ("…" if start + limit < len(text) else "")


def search_workspace(
    db_path: str | Path,
    query: str,
    *,
    action_queue: dict[str, Any],
    exceptions: dict[str, Any],
    limit: int = 30,
) -> dict[str, Any]:
    """Search people, interviews, episodes, transcripts, actions, and exceptions."""
    term = _text(query)
    if len(term) < 2:
        return {"query": term, "results": [], "counts": {}, "minimum_query_length": 2}
    pattern = _like(term)
    results: list[dict[str, Any]] = []
    with connect_database(db_path) as conn:
        conn.row_factory = __import__("sqlite3").Row
        for row in conn.execute(
            """SELECT id, COALESCE(NULLIF(full_name, ''), name, 'Unnamed guest') AS title,
                      email, profession, background
               FROM guests
               WHERE full_name LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\'
                  OR email LIKE ? ESCAPE '\\' OR profession LIKE ? ESCAPE '\\'
                  OR background LIKE ? ESCAPE '\\'
               ORDER BY id DESC LIMIT 12""",
            (pattern,) * 5,
        ).fetchall():
            title = _text(row["title"])
            results.append({
                "key": f"guest:{row['id']}", "kind": "guest", "title": title,
                "subtitle": " · ".join(item for item in (_text(row["email"]), _text(row["profession"])) if item),
                "snippet": _snippet(row["background"], term),
                "href": f"/dashboard?{urlencode({'q': title})}", "command": "Open guest",
            })
        for row in conn.execute(
            """SELECT id, guest_name, title, scheduled_for, confirmation_status
               FROM interviews
               WHERE guest_name LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\'
                  OR guest_email LIKE ? ESCAPE '\\' OR notes LIKE ? ESCAPE '\\'
               ORDER BY datetime(scheduled_for) DESC, id DESC LIMIT 12""",
            (pattern,) * 4,
        ).fetchall():
            guest = _text(row["guest_name"]) or "Interview"
            results.append({
                "key": f"interview:{row['id']}", "kind": "interview",
                "title": _text(row["title"]) or guest,
                "subtitle": f"{guest} · {_text(row['scheduled_for']) or 'No date'} · {_text(row['confirmation_status'])}",
                "snippet": "", "href": f"/operations?{urlencode({'q': guest})}", "command": "Open interview",
            })
        for row in conn.execute(
            """SELECT id, guest_name, episode_title, published_title, category, transcript_text,
                      release_status, production_status
               FROM episodes
               WHERE guest_name LIKE ? ESCAPE '\\' OR episode_title LIKE ? ESCAPE '\\'
                  OR published_title LIKE ? ESCAPE '\\' OR category LIKE ? ESCAPE '\\'
                  OR topic LIKE ? ESCAPE '\\' OR transcript_text LIKE ? ESCAPE '\\'
               ORDER BY id DESC LIMIT 16""",
            (pattern,) * 6,
        ).fetchall():
            title = _text(row["published_title"] or row["episode_title"]) or "Untitled episode"
            transcript_match = term.casefold() in _text(row["transcript_text"]).casefold()
            results.append({
                "key": f"episode:{row['id']}", "kind": "episode",
                "title": title,
                "subtitle": f"{_text(row['guest_name']) or 'Guest not set'} · {_text(row['release_status'])} · {_text(row['production_status'])}",
                "snippet": _snippet(row["transcript_text"], term) if transcript_match else _text(row["category"]),
                "match_source": "transcript" if transcript_match else "episode",
                "href": f"/planning?{urlencode({'tab': 'release_planning', 'episode_id': row['id']})}",
                "command": "Open episode",
                "secondary_command": "Schedule" if _text(row["release_status"]).lower() == "unplanned" else "",
                "secondary_href": f"/planning?{urlencode({'tab': 'release_planning', 'episode_id': row['id'], 'action': 'schedule'})}" if _text(row["release_status"]).lower() == "unplanned" else "",
            })

    lowered = term.casefold()
    for item in action_queue.get("items", []):
        haystack = " ".join(_text(item.get(key)) for key in ("title", "next_action", "reason", "owner"))
        if lowered in haystack.casefold():
            results.append({
                "key": f"action:{item.get('key')}", "kind": "action",
                "title": _text(item.get("next_action")) or "Action",
                "subtitle": _text(item.get("title")), "snippet": _text(item.get("reason")),
                "href": _text(item.get("href")) or "/dashboard", "command": _text(item.get("action_label")) or "Review",
            })
    for item in exceptions.get("items", []):
        haystack = " ".join(_text(item.get(key)) for key in ("title", "reason", "category"))
        if lowered in haystack.casefold():
            results.append({
                "key": f"exception:{item.get('key')}", "kind": "exception",
                "title": _text(item.get("title")), "subtitle": _text(item.get("category")).replace("_", " "),
                "snippet": _text(item.get("reason")), "href": _text(item.get("href")) or "/planning",
                "command": _text(item.get("action_label")) or "Review exception",
            })

    kind_order = {"action": 0, "exception": 1, "episode": 2, "interview": 3, "guest": 4}
    results.sort(key=lambda item: (kind_order.get(item["kind"], 9), item["title"].casefold()))
    results = results[:max(1, min(int(limit), 50))]
    counts = {kind: sum(item["kind"] == kind for item in results) for kind in kind_order}
    return {"query": term, "results": results, "counts": counts, "minimum_query_length": 2}


def build_personal_briefing(
    *,
    username: str,
    action_queue: dict[str, Any],
    exceptions: dict[str, Any],
    window: str,
) -> dict[str, Any]:
    """Return a quiet, actionable daily or weekly view for one signed-in teammate."""
    normalized_window = "weekly" if _text(window).lower() == "weekly" else "daily"
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=7 if normalized_window == "weekly" else 1)
    owned = [
        item for item in action_queue.get("items", [])
        if _text(item.get("owner")).casefold() == _text(username).casefold()
    ]

    def parsed(value: Any) -> datetime | None:
        text = _text(value)
        if not text:
            return None
        try:
            result = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    overdue = [item for item in owned if (parsed(item.get("due_at")) or horizon) < now]
    upcoming = [
        item for item in owned
        if parsed(item.get("due_at")) is not None and now <= parsed(item.get("due_at")) <= horizon
    ]
    actionable_exceptions = [
        item for item in exceptions.get("items", []) if item.get("severity") in {"critical", "high"}
    ][:8]
    return {
        "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "username": username,
        "window": normalized_window,
        "counts": {
            "assigned": len(owned), "overdue": len(overdue), "upcoming": len(upcoming),
            "actionable_exceptions": len(actionable_exceptions),
        },
        "assigned": owned[:12],
        "overdue": overdue[:12],
        "upcoming": upcoming[:12],
        "exceptions": actionable_exceptions,
        "notification_policy": "quiet_unless_actionable",
    }
