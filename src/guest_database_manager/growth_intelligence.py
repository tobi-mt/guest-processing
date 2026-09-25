"""Source-backed growth intelligence for Mirror Talk."""

from __future__ import annotations

import hashlib
import csv
import json
import math
import re
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Iterable

from guest_database_manager.db_connection import connect_database
from guest_database_manager.episode_planner import EDITORIAL_PILLARS, build_editorial_fit


CANONICAL_METRICS = {
    "organic_reach": "count",
    "paid_reach": "count",
    "consumption_depth_pct": "percent",
    "conversion_rate_pct": "percent",
    "return_rate_pct": "percent",
    "downloads_7d": "count",
    "youtube_ctr_pct": "percent",
    "youtube_retention_30s_pct": "percent",
    "average_view_duration_seconds": "seconds",
    "spotify_home_impressions": "count",
    "spotify_search_impressions": "count",
    "guest_shares": "count",
    "guest_newsletter_inclusions": "count",
    "email_subscribers_gained": "count",
    "site_to_podcast_conversion_pct": "percent",
    "downloads": "count",
    "plays": "count",
    "streams": "count",
    "unique_listeners": "count",
    "listeners": "count",
    "followers": "count",
    "subscribers": "count",
    "watch_time_hours": "count",
    "device_mobile": "count",
    "device_desktop": "count",
    "device_tablet": "count",
    "device_tv": "count",
    "device_smart_speaker": "count",
    "device_other": "count",
}
MFS_COMPONENTS = ("organic_reach", "consumption_depth_pct", "conversion_rate_pct", "return_rate_pct")

CSV_FIELD_ALIASES = {
    "episode_id": ("episode_id", "episode id", "episode database id"),
    "episode_title": ("episode_title", "episode title", "title", "content title"),
    "guest_name": ("guest_name", "guest name", "guest", "speaker"),
    "provider": ("provider", "platform", "source platform", "channel"),
    "metric_name": ("metric_name", "metric name", "metric", "measure"),
    "metric_value": ("metric_value", "metric value", "value", "result"),
    "traffic_scope": ("traffic_scope", "traffic scope", "scope", "traffic type"),
    "period_start": ("period_start", "period start", "start date", "start", "from", "date"),
    "period_end": ("period_end", "period end", "end date", "end", "to", "date"),
    "source_reference": ("source_reference", "source reference", "source file", "reference"),
}

EXPORTED_METRIC_ALIASES = {
    "plays": ("plays", "play starts"),
    "downloads": ("downloads", "downloaded"),
    "streams": ("streams",),
    "unique_listeners": ("audience", "unique audience", "unique listeners"),
    "listeners": ("listeners",),
    "followers": ("followers",),
    "consumption_depth_pct": ("average consumption", "average consumption percentage", "avg consumption"),
}


class GrowthIntelligenceError(ValueError):
    """Raised when growth evidence is unsafe or ambiguous."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _iso_date(value: Any, field: str) -> str:
    text = _text(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        for date_format in ("%m/%d/%Y", "%Y/%m/%d", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(text, date_format).date().isoformat()
            except ValueError:
                continue
    raise GrowthIntelligenceError(
        f"{field} must be an ISO date, US date (MM/DD/YYYY), or named-month date."
    )


def _metric_value(metric: str, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise GrowthIntelligenceError("metric_value must be numeric.") from exc
    if not math.isfinite(number) or number < 0:
        raise GrowthIntelligenceError("metric_value must be a finite non-negative number.")
    if CANONICAL_METRICS.get(metric) == "percent" and number > 100:
        raise GrowthIntelligenceError("Percentage metrics cannot exceed 100.")
    return number


class GrowthIntelligence:
    """Persist immutable observations and derive recalculable summaries."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    @staticmethod
    def _header_key(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", " ", _text(value).casefold()).strip()

    @staticmethod
    def _identity_key(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", " ", _text(value).casefold()).strip()

    @classmethod
    def _resolve_csv_mapping(cls, headers: list[str], supplied: Any) -> dict[str, str]:
        normalized_headers = {cls._header_key(header): header for header in headers if _text(header)}
        mapping: dict[str, str] = {}
        if isinstance(supplied, dict):
            for field, header in supplied.items():
                if field in CSV_FIELD_ALIASES and header in headers:
                    mapping[field] = header
        for field, aliases in CSV_FIELD_ALIASES.items():
            if field in mapping:
                continue
            for alias in aliases:
                matched = normalized_headers.get(cls._header_key(alias))
                if matched:
                    mapping[field] = matched
                    break
        return mapping

    @staticmethod
    def _episode_indexes(conn: Any) -> tuple[set[int], dict[tuple[str, str], list[int]], dict[str, list[int]]]:
        conn.row_factory = __import__("sqlite3").Row
        rows = conn.execute(
            "SELECT id, guest_name, episode_title, published_title FROM episodes"
        ).fetchall()
        valid_ids = {int(row["id"]) for row in rows}
        by_title_guest: dict[tuple[str, str], list[int]] = {}
        by_title: dict[str, list[int]] = {}
        for row in rows:
            guest_key = GrowthIntelligence._identity_key(row["guest_name"])
            titles = {
                GrowthIntelligence._identity_key(row["episode_title"]),
                GrowthIntelligence._identity_key(row["published_title"]),
            } - {""}
            for title_key in titles:
                by_title.setdefault(title_key, []).append(int(row["id"]))
                if guest_key:
                    by_title_guest.setdefault((title_key, guest_key), []).append(int(row["id"]))
        return valid_ids, by_title_guest, by_title

    @staticmethod
    def _normalize_observation(
        row: dict[str, Any],
        *,
        valid_episode_ids: set[int],
    ) -> tuple[dict[str, Any], tuple[Any, ...], str]:
        metric = _text(row.get("metric_name"))
        dimensional = bool(re.fullmatch(r"(?:device|country)_[a-z0-9_]{2,64}", metric))
        if metric not in CANONICAL_METRICS and not dimensional:
            raise GrowthIntelligenceError(f"Unsupported metric_name: {metric or 'missing'}.")
        episode_id = row.get("episode_id")
        try:
            episode_id = int(episode_id) if episode_id not in (None, "") else None
        except (TypeError, ValueError) as exc:
            raise GrowthIntelligenceError("episode_id must be a numeric database id.") from exc
        if episode_id is not None and episode_id not in valid_episode_ids:
            raise GrowthIntelligenceError("episode_id does not identify an existing episode.")
        provider = _text(row.get("provider")).lower()
        source_reference = _text(row.get("source_reference"))
        if not provider or not source_reference:
            raise GrowthIntelligenceError("provider and source_reference are required.")
        scope = _text(row.get("traffic_scope") or "all").lower()
        if scope not in {"organic", "paid", "all", "unknown"}:
            raise GrowthIntelligenceError("traffic_scope must be organic, paid, all, or unknown.")
        if metric == "organic_reach" and scope != "organic":
            raise GrowthIntelligenceError("organic_reach must use organic traffic_scope.")
        if metric == "paid_reach" and scope != "paid":
            raise GrowthIntelligenceError("paid_reach must use paid traffic_scope.")
        start = _iso_date(row.get("period_start"), "period_start")
        end = _iso_date(row.get("period_end"), "period_end")
        if end < start:
            raise GrowthIntelligenceError("period_end cannot be before period_start.")
        value = _metric_value(metric, row.get("metric_value"))
        fingerprint = json.dumps([episode_id, provider, metric, scope, start, end], separators=(",", ":"))
        observation_key = hashlib.sha256(fingerprint.encode()).hexdigest()
        key = _text(row.get("idempotency_key")) or observation_key
        source_hash = hashlib.sha256(source_reference.encode()).hexdigest()
        normalized = {
            "episode_id": episode_id,
            "provider": provider,
            "metric_name": metric,
            "metric_value": value,
            "traffic_scope": scope,
            "period_start": start,
            "period_end": end,
            "source_reference": source_reference,
        }
        prepared = (
            episode_id, provider, metric, value, CANONICAL_METRICS.get(metric, "count"), scope, start, end,
            source_reference, source_hash, observation_key, key,
        )
        return normalized, prepared, observation_key

    def preview_csv(
        self,
        csv_text: str,
        *,
        provider: str = "",
        source_reference: str = "",
        mapping: Any = None,
    ) -> dict[str, Any]:
        """Parse and validate an analytics CSV without mutating the database."""
        if not isinstance(csv_text, str) or not csv_text.strip():
            raise GrowthIntelligenceError("Choose a non-empty CSV file to preview.")
        if len(csv_text.encode("utf-8")) > 2_000_000:
            raise GrowthIntelligenceError("Analytics CSV files are limited to 2 MB.")
        try:
            reader = csv.DictReader(StringIO(csv_text.lstrip("\ufeff")))
            headers = [str(item or "").strip() for item in (reader.fieldnames or [])]
            raw_rows = list(reader)
        except csv.Error as exc:
            raise GrowthIntelligenceError("The analytics file is not valid CSV.") from exc
        if not headers:
            raise GrowthIntelligenceError("The analytics CSV needs a header row.")
        if not raw_rows or len(raw_rows) > 500:
            raise GrowthIntelligenceError("Provide between 1 and 500 analytics rows.")
        resolved_mapping = self._resolve_csv_mapping(headers, mapping)
        aliases_by_metric = {
            metric: {self._header_key(metric), self._header_key(metric.replace("_", " "))}
            | {self._header_key(alias) for alias in EXPORTED_METRIC_ALIASES.get(metric, ())}
            for metric in CANONICAL_METRICS
        }
        wide_metric_headers = {
            metric: header
            for metric, aliases in aliases_by_metric.items()
            for header in headers
            if self._header_key(header) in aliases
        }
        long_format = "metric_name" in resolved_mapping and "metric_value" in resolved_mapping
        missing = [field for field in ("period_start", "period_end") if field not in resolved_mapping]
        if not long_format and not wide_metric_headers:
            missing.extend(("metric_name", "metric_value"))
        if missing:
            raise GrowthIntelligenceError(
                "Map the required CSV columns before previewing: " + ", ".join(missing) + "."
            )

        default_provider = _text(provider).lower()
        default_reference = _text(source_reference)
        preview_rows: list[dict[str, Any]] = []
        ready: list[dict[str, Any]] = []
        warnings: list[str] = []
        with connect_database(self.db_path) as conn:
            valid_ids, by_title_guest, by_title = self._episode_indexes(conn)
            existing = {
                str(row[0]) for row in conn.execute("SELECT observation_key FROM growth_metric_observations").fetchall()
            }
            seen: set[str] = set()

            def process_candidate(candidate: dict[str, Any], row_number: int) -> None:
                candidate["provider"] = _text(candidate.get("provider")) or default_provider
                candidate["source_reference"] = _text(candidate.get("source_reference")) or default_reference
                metric = _text(candidate.get("metric_name"))
                if not _text(candidate.get("traffic_scope")):
                    candidate["traffic_scope"] = "organic" if metric == "organic_reach" else "paid" if metric == "paid_reach" else "all"

                row_warnings: list[str] = []
                if candidate.get("episode_id") in (None, ""):
                    title_key = self._identity_key(candidate.get("episode_title"))
                    guest_key = self._identity_key(candidate.get("guest_name"))
                    matches = by_title_guest.get((title_key, guest_key), []) if title_key and guest_key else []
                    if not matches and title_key:
                        matches = by_title.get(title_key, [])
                    unique_matches = sorted(set(matches))
                    if len(unique_matches) == 1:
                        candidate["episode_id"] = unique_matches[0]
                    elif len(unique_matches) > 1:
                        row_warnings.append("Episode title is ambiguous; this metric will remain unlinked.")
                    elif title_key or guest_key:
                        row_warnings.append("No unique episode match; this metric will remain unlinked.")

                try:
                    normalized, _prepared, observation_key = self._normalize_observation(
                        candidate, valid_episode_ids=valid_ids
                    )
                    duplicate = observation_key in existing or observation_key in seen
                    seen.add(observation_key)
                    status = "duplicate" if duplicate else "ready"
                    if duplicate:
                        row_warnings.append("This observation already exists or is repeated in the file.")
                    preview_rows.append({
                        "row": row_number,
                        "status": status,
                        "observation": normalized,
                        "warnings": row_warnings,
                        "errors": [],
                    })
                    if not duplicate:
                        ready.append(normalized)
                    warnings.extend(row_warnings)
                except GrowthIntelligenceError as exc:
                    preview_rows.append({
                        "row": row_number,
                        "status": "invalid",
                        "observation": candidate,
                        "warnings": row_warnings,
                        "errors": [str(exc)],
                    })

            for row_number, raw in enumerate(raw_rows, 2):
                base_candidate = {
                    field: raw.get(header, "")
                    for field, header in resolved_mapping.items()
                    if field not in {"metric_name", "metric_value"}
                }
                if long_format:
                    process_candidate({
                        **base_candidate,
                        "metric_name": raw.get(resolved_mapping["metric_name"], ""),
                        "metric_value": raw.get(resolved_mapping["metric_value"], ""),
                    }, row_number)
                else:
                    for metric, header in wide_metric_headers.items():
                        if _text(raw.get(header)):
                            process_candidate({
                                **base_candidate,
                                "metric_name": metric,
                                "metric_value": raw.get(header, ""),
                            }, row_number)

        if len(preview_rows) > 500:
            raise GrowthIntelligenceError(
                "This CSV expands to more than 500 observations. Split it into smaller files before importing."
            )

        invalid_count = sum(item["status"] == "invalid" for item in preview_rows)
        duplicate_count = sum(item["status"] == "duplicate" for item in preview_rows)
        linked_count = sum(item.get("observation", {}).get("episode_id") is not None for item in preview_rows if item["status"] != "invalid")
        metrics = sorted({item["metric_name"] for item in ready})
        missing_mfs = [metric for metric in MFS_COMPONENTS if metric not in metrics]
        return {
            "headers": headers,
            "mapping": resolved_mapping,
            "format": "long" if long_format else "wide",
            "summary": {
                "submitted": len(preview_rows),
                "ready": len(ready),
                "invalid": invalid_count,
                "duplicates": duplicate_count,
                "linked_to_episode": linked_count,
                "unlinked": max(len(preview_rows) - invalid_count - linked_count, 0),
            },
            "quality": {
                "metrics_present": metrics,
                "missing_mfs_metrics": missing_mfs,
                "providers": sorted({item["provider"] for item in ready}),
                "period_start": min((item["period_start"] for item in ready), default=None),
                "period_end": max((item["period_end"] for item in ready), default=None),
                "warnings": sorted(set(warnings)),
            },
            "rows": preview_rows,
            "observations": ready,
        }

    def record_observations(self, rows: Iterable[dict[str, Any]], *, actor: str, correlation_id: str = "") -> dict[str, Any]:
        rows = list(rows)
        if not rows or len(rows) > 500:
            raise GrowthIntelligenceError("Provide between 1 and 500 observations.")
        prepared = []
        with connect_database(self.db_path) as conn:
            valid_episode_ids = {int(row[0]) for row in conn.execute("SELECT id FROM episodes").fetchall()}
            for row in rows:
                _normalized, values, _observation_key = self._normalize_observation(
                    row, valid_episode_ids=valid_episode_ids
                )
                prepared.append((*values, actor, correlation_id))
            before = conn.total_changes
            conn.executemany(
                """INSERT OR IGNORE INTO growth_metric_observations
                   (episode_id, provider, metric_name, metric_value, unit, traffic_scope,
                    period_start, period_end, source_reference, source_hash, observation_key,
                    idempotency_key, actor, correlation_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                prepared,
            )
            inserted = conn.total_changes - before
            conn.commit()
        return {"submitted": len(rows), "inserted": inserted, "duplicates": len(rows) - inserted}

    @staticmethod
    def _episode_mfs(rows: list[dict[str, Any]]) -> dict[str, Any]:
        latest_period_end = max((row["period_end"] for row in rows), default=None)
        latest_period_start = max(
            (row["period_start"] for row in rows if row["period_end"] == latest_period_end),
            default=None,
        )
        period_rows = [
            row for row in rows
            if row["period_end"] == latest_period_end and row["period_start"] == latest_period_start
        ]
        latest: dict[str, dict[str, Any]] = {}
        for row in period_rows:
            metric = row["metric_name"]
            if metric in MFS_COMPONENTS and metric not in latest:
                latest[metric] = row
        missing = [metric for metric in MFS_COMPONENTS if metric not in latest]
        if missing:
            return {"status": "incomplete", "score": None, "period_start": latest_period_start, "period_end": latest_period_end, "missing_metrics": missing, "components": {key: latest[key]["metric_value"] for key in latest}}
        # Reach is normalized to the current 5k organic-breakout operating target.
        normalized = [min(100.0, latest["organic_reach"]["metric_value"] / 50.0)]
        normalized.extend(float(latest[key]["metric_value"]) for key in MFS_COMPONENTS[1:])
        score = math.prod(max(value, 0.01) for value in normalized) ** (1 / 4)
        return {"status": "ready", "score": round(score, 1), "period_start": latest_period_start, "period_end": latest_period_end, "missing_metrics": [], "components": {key: latest[key]["metric_value"] for key in MFS_COMPONENTS}, "method": "Geometric mean; organic reach normalized to the 5,000-view breakout target."}

    def dashboard(self) -> dict[str, Any]:
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            rows = [dict(row) for row in conn.execute("SELECT * FROM growth_metric_observations ORDER BY period_end DESC, id DESC").fetchall()]
            episodes = [dict(row) for row in conn.execute("SELECT * FROM episodes ORDER BY release_date DESC, id DESC").fetchall()]
            experiments = [dict(row) for row in conn.execute("SELECT * FROM growth_experiments ORDER BY updated_at DESC, id DESC").fetchall()]
            import_history = [dict(row) for row in conn.execute(
                """SELECT COALESCE(NULLIF(correlation_id, ''), source_hash) AS batch_key,
                          MAX(source_reference) AS source_reference, MAX(provider) AS provider,
                          MAX(actor) AS actor, MAX(imported_at) AS imported_at,
                          COUNT(*) AS observation_count,
                          COUNT(DISTINCT episode_id) AS episode_count,
                          MIN(period_start) AS period_start, MAX(period_end) AS period_end
                   FROM growth_metric_observations
                   GROUP BY COALESCE(NULLIF(correlation_id, ''), source_hash)
                   ORDER BY MAX(imported_at) DESC LIMIT 12"""
            ).fetchall()]
        by_episode: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            if row["episode_id"] is not None:
                by_episode.setdefault(int(row["episode_id"]), []).append(row)
        episode_scores = []
        episode_map = {int(item["id"]): item for item in episodes}
        for episode_id, metrics in by_episode.items():
            episode = episode_map.get(episode_id, {})
            episode_scores.append({"episode_id": episode_id, "episode_title": episode.get("published_title") or episode.get("episode_title") or "Untitled episode", "mfs": self._episode_mfs(metrics)})
        released = [episode for episode in episodes if _text(episode.get("release_status")).lower() == "released"][:12]
        pillar_counts = {name: 0 for name in EDITORIAL_PILLARS}
        unclassified = 0
        for episode in released:
            pillar = build_editorial_fit(episode)["pillar"]
            if pillar in pillar_counts:
                pillar_counts[pillar] += 1
            else:
                unclassified += 1
        denominator = len(released) or 1
        guardrails = {
            "Heal": "Heal + Become: 5–7 of 12",
            "Become": "Heal + Become: 5–7 of 12",
            "Love": "Love + Purpose: 3–5 of 12",
            "Purpose": "Love + Purpose: 3–5 of 12",
            "Lead": "1–2 of 12; human story required",
        }
        editorial_mix = [
            {
                "pillar": name,
                "count": pillar_counts[name],
                "actual_share_pct": round(pillar_counts[name] * 100 / denominator, 1),
                "twelve_release_guardrail": guardrails[name],
            }
            for name in EDITORIAL_PILLARS
        ]
        latest_period = max((row["period_end"] for row in rows), default=None)
        current_rows = [row for row in rows if row["period_end"] == latest_period]
        current_total = lambda metric: sum(row["metric_value"] for row in current_rows if row["metric_name"] == metric)
        paid = sum(row["metric_value"] for row in current_rows if row["metric_name"] == "paid_reach")
        organic = sum(row["metric_value"] for row in current_rows if row["metric_name"] == "organic_reach")
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "freshness": "no_data" if not latest_period else "current" if (datetime.now(timezone.utc).date() - datetime.fromisoformat(latest_period).date()).days <= 14 else "stale",
            "latest_period_end": latest_period,
            "quality": {"observation_count": len(rows), "episodes_with_evidence": len(by_episode), "mfs_ready": sum(item["mfs"]["status"] == "ready" for item in episode_scores), "unclassified_released_episodes": unclassified, "editorial_window_count": len(released)},
            "reach": {"organic": organic, "paid": paid, "paid_share_pct": round(paid * 100 / (paid + organic), 1) if paid + organic else None},
            "discovery": {"downloads_7d": current_total("downloads_7d"), "spotify_home_impressions": current_total("spotify_home_impressions"), "spotify_search_impressions": current_total("spotify_search_impressions")},
            "distribution": {"guest_shares": current_total("guest_shares"), "guest_newsletter_inclusions": current_total("guest_newsletter_inclusions")},
            "owned_audience": {"email_subscribers_gained": current_total("email_subscribers_gained"), "site_to_podcast_conversion_pct": max((row["metric_value"] for row in current_rows if row["metric_name"] == "site_to_podcast_conversion_pct"), default=None)},
            "episode_scores": sorted(episode_scores, key=lambda item: (item["mfs"]["score"] is None, -(item["mfs"]["score"] or 0))),
            "editorial_mix": editorial_mix,
            "experiments": experiments,
            "import_history": import_history,
            "metric_definitions": CANONICAL_METRICS,
        }

    def create_experiment(self, payload: dict[str, Any], *, actor: str, correlation_id: str = "") -> dict[str, Any]:
        required = {key: _text(payload.get(key)) for key in ("name", "hypothesis", "primary_metric", "control_label", "treatment_label")}
        if not all(required.values()):
            raise GrowthIntelligenceError("Experiment name, hypothesis, primary metric, control, and treatment are required.")
        if required["primary_metric"] not in CANONICAL_METRICS:
            raise GrowthIntelligenceError("Experiment primary_metric must be canonical.")
        starts_on = _iso_date(payload["starts_on"], "starts_on") if payload.get("starts_on") else None
        ends_on = _iso_date(payload["ends_on"], "ends_on") if payload.get("ends_on") else None
        if starts_on and ends_on and ends_on < starts_on:
            raise GrowthIntelligenceError("Experiment ends_on cannot be before starts_on.")
        with connect_database(self.db_path) as conn:
            cursor = conn.execute("""INSERT INTO growth_experiments
                (name, hypothesis, primary_metric, control_label, treatment_label, status, starts_on, ends_on, actor, correlation_id)
                VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?)""", (*required.values(), starts_on, ends_on, actor, correlation_id))
            experiment_id = int(cursor.lastrowid)
            conn.commit()
        return {"id": experiment_id, "status": "draft", **required, "starts_on": starts_on, "ends_on": ends_on}
