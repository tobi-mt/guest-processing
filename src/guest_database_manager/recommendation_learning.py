"""Governed learning loop for release recommendations.

The subsystem deliberately separates observation, evaluation, approval, and activation.
No read path writes data and no candidate can change production ranking before promotion.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable
from uuid import uuid4

from guest_database_manager.db_connection import connect_database

FEATURE_SCHEMA_VERSION = "release-features-v2"
FEATURE_NAMES = (
    "bias",
    "base_score",
    "promotion_readiness",
    "has_research",
    "has_website",
    "has_title",
    "watchout_count",
    "production_buffer",
    "audience_fatigue",
    "event_alignment",
    "capacity_delay",
)
OUTCOME_LABELS = {
    "accepted": 0.7,
    "rejected": 0.0,
    "booked": 0.8,
    "released": 1.0,
    "delayed": 0.25,
    "cancelled": 0.0,
    "performance": None,
    "positive": 1.0,
    "neutral": 0.5,
    "negative": 0.0,
}


class LearningError(ValueError):
    """A safe, operator-facing learning workflow error."""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _loads(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(value) if value else fallback
    except (TypeError, json.JSONDecodeError):
        return fallback


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _finite_float(value: Any, *, field: str, default: float | None = None) -> float:
    """Parse a finite numeric value or raise a safe, operator-facing error."""
    if value is None or value == "":
        if default is not None:
            return default
        raise LearningError(f"{field} must be a finite number")
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise LearningError(f"{field} must be a finite number") from exc
    if not math.isfinite(numeric):
        raise LearningError(f"{field} must be a finite number")
    return numeric


def _validated_weights(value: Any) -> dict[str, float] | None:
    """Return a complete finite policy vector, or None for unsafe persisted data."""
    if not isinstance(value, dict):
        return None
    weights: dict[str, float] = {}
    for name, raw in value.items():
        if name not in FEATURE_NAMES:
            continue
        try:
            weights[name] = _finite_float(raw, field=f"Policy weight {name}")
        except LearningError:
            return None
    return weights


def extract_features(recommendation: dict[str, Any]) -> dict[str, float]:
    """Extract a small, explainable, non-sensitive feature vector."""
    readiness = recommendation.get("promotion_readiness") or {}
    watchouts = recommendation.get("watchouts") or []
    research = recommendation.get("guest_research") or {}
    forecast = recommendation.get("production_readiness_forecast") or {}
    fatigue = recommendation.get("audience_fatigue") or {}
    capacity = recommendation.get("calendar_capacity") or {}
    return {
        "bias": 1.0,
        "base_score": max(-1.0, min(1.0, _finite_float(recommendation.get("base_priority_score") or recommendation.get("priority_score"), field="Recommendation score", default=0.0) / 100.0)),
        "promotion_readiness": max(0.0, min(1.0, _finite_float(readiness.get("score"), field="Promotion readiness score", default=0.0) / 100.0)),
        "has_research": 1.0 if research else 0.0,
        "has_website": 1.0 if str(recommendation.get("website") or "").strip() else 0.0,
        "has_title": 1.0 if str(recommendation.get("working_title") or recommendation.get("episode_title") or "").strip() else 0.0,
        "watchout_count": min(1.0, len(watchouts) / 4.0),
        "production_buffer": max(-1.0, min(1.0, _finite_float(forecast.get("buffer_days"), field="Production buffer", default=0.0) / 28.0)),
        "audience_fatigue": max(0.0, min(1.0, _finite_float(fatigue.get("score"), field="Audience fatigue score", default=0.0) / 100.0)),
        "event_alignment": 1.0 if recommendation.get("time_sensitive_event_alignment") else 0.0,
        "capacity_delay": max(0.0, min(1.0, _finite_float(capacity.get("weeks_until_slot"), field="Capacity delay", default=0.0) / 12.0)),
    }


def _probability(features: dict[str, float], weights: dict[str, float]) -> float:
    z = sum(float(features.get(name, 0)) * float(weights.get(name, 0)) for name in FEATURE_NAMES)
    z = max(-20.0, min(20.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def apply_active_policy(db_path: str | Path, recommendations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply the active bounded adjustment in memory; this read never records observations."""
    items = [dict(item) for item in recommendations]
    with connect_database(db_path) as conn:
        conn.row_factory = __import__("sqlite3").Row
        row = conn.execute("SELECT * FROM recommendation_policies WHERE status = 'active'").fetchone()
    if not row:
        return items
    raw_weights = _loads(row["weights_json"], {})
    weights = _validated_weights(raw_weights)
    policy_is_valid = weights is not None
    weights = weights or {}
    for item in items:
        features = extract_features(item)
        adjustment = max(-10.0, min(10.0, (_probability(features, weights) - 0.5) * 20.0)) if weights else 0.0
        base_score = _finite_float(item.get("priority_score"), field="Recommendation score", default=0.0)
        item["priority_score"] = round(base_score + adjustment, 1)
        item["learning"] = {
            "policy_version": row["version"],
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "adjustment": round(adjustment, 1),
            "mode": "adaptive" if weights else "rules_baseline" if policy_is_valid else "invalid_policy_fallback",
        }
    if weights:
        items.sort(key=lambda item: (-float(item.get("priority_score") or 0), str(item.get("guest_name") or "")))
    return items


class RecommendationLearning:
    """Transactional workflow for observations, training, promotion, and monitoring."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    def _audit(self, conn: Any, event_type: str, actor: str, reason: str, after: Any) -> None:
        conn.execute(
            """INSERT INTO audit_events
               (entity_type, entity_id, event_type, actor, source, reason, correlation_id, after_json)
               VALUES ('recommendation_policy', ?, ?, ?, 'recommendation_learning', ?, ?, ?)""",
            (str((after or {}).get("version") or "system"), event_type, actor, reason or None, str(uuid4()), _json(after)),
        )

    def status(self) -> dict[str, Any]:
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            active = conn.execute("SELECT * FROM recommendation_policies WHERE status = 'active'").fetchone()
            settings = conn.execute("SELECT * FROM recommendation_learning_settings WHERE id = 1").fetchone()
            counts = conn.execute(
                """SELECT
                    (SELECT COUNT(*) FROM recommendation_observations),
                    (SELECT COUNT(*) FROM recommendation_outcomes),
                    (SELECT COUNT(*) FROM recommendation_evaluations)"""
            ).fetchone()
            policies = conn.execute(
                "SELECT version, parent_version, status, training_summary_json, created_by, approved_by, created_at, approved_at, row_version FROM recommendation_policies ORDER BY id DESC"
            ).fetchall()
            evaluations = conn.execute("SELECT * FROM recommendation_evaluations ORDER BY id DESC LIMIT 10").fetchall()
            runs = conn.execute("SELECT * FROM recommendation_learning_runs ORDER BY id DESC LIMIT 10").fetchall()
            outcome_breakdown = {
                str(row[0]): int(row[1])
                for row in conn.execute(
                    "SELECT outcome_type, COUNT(*) FROM recommendation_outcomes GROUP BY outcome_type"
                ).fetchall()
            }
            unlinked_outcomes = int(conn.execute(
                "SELECT COUNT(*) FROM recommendation_outcomes WHERE observation_id IS NULL"
            ).fetchone()[0])
            latest_outcome_at = conn.execute(
                "SELECT MAX(occurred_at) FROM recommendation_outcomes"
            ).fetchone()[0]
            outcome_values = [float(row[0]) for row in conn.execute(
                "SELECT value FROM recommendation_outcomes ORDER BY occurred_at DESC, id DESC LIMIT 60"
            ).fetchall()]
            performance_values = [float(row[0]) for row in conn.execute(
                "SELECT value FROM recommendation_outcomes WHERE outcome_type = 'performance'"
            ).fetchall()]
            scored_rows = [
                (_loads(row[0], {}), float(row[1]))
                for row in conn.execute(
                    """SELECT o.features_json, r.value
                       FROM recommendation_outcomes r
                       JOIN recommendation_observations o ON o.id = r.observation_id
                       WHERE o.feature_schema_version = ?""",
                    (FEATURE_SCHEMA_VERSION,),
                ).fetchall()
            ]
            pending_reviews = [dict(row) for row in conn.execute(
                """SELECT e.id AS episode_id,
                          COALESCE(NULLIF(e.published_title, ''), NULLIF(e.episode_title, ''), 'Untitled episode') AS episode_title,
                          e.guest_name, e.release_date, o.id AS observation_id, o.policy_version
                   FROM episodes e
                   JOIN recommendation_observations o ON o.id = (
                       SELECT MAX(latest.id) FROM recommendation_observations latest
                       WHERE latest.episode_id = e.id
                   )
                   LEFT JOIN recommendation_outcomes r ON r.observation_id = o.id
                   WHERE LOWER(TRIM(COALESCE(e.release_status, ''))) = 'released'
                   GROUP BY e.id, o.id
                   HAVING COUNT(r.id) = 0
                   ORDER BY date(e.release_date) DESC, e.id DESC LIMIT 12"""
            ).fetchall()]
        recent = outcome_values[:30]
        previous = outcome_values[30:60]
        recent_mean = sum(recent) / len(recent) if recent else None
        previous_mean = sum(previous) / len(previous) if previous else None
        drift = abs(recent_mean - previous_mean) if recent_mean is not None and previous_mean is not None else None
        active_weights = _validated_weights(_loads(active["weights_json"], {})) if active else None
        log_loss = self._log_loss(scored_rows, active_weights or {}) if scored_rows else None
        decisions = outcome_breakdown.get("accepted", 0) + outcome_breakdown.get("rejected", 0)
        accepted = outcome_breakdown.get("accepted", 0)
        released = outcome_breakdown.get("released", 0)
        latest_run = dict(runs[0]) if runs else None
        latest_run_details = _loads(latest_run.get("details_json"), {}) if latest_run else {}
        return {
            "active_policy": dict(active) if active else None,
            "settings": dict(settings) if settings else {},
            "counts": {"observations": counts[0], "outcomes": counts[1], "evaluations": counts[2]},
            "outcomes": {
                "by_type": outcome_breakdown,
                "linked": int(counts[1]) - unlinked_outcomes,
                "unlinked": unlinked_outcomes,
                "latest_at": latest_outcome_at,
            },
            "pending_outcome_reviews": pending_reviews,
            "policies": [{**dict(row), "training_summary": _loads(row["training_summary_json"], {})} for row in policies],
            "evaluations": [{**dict(row), "guardrails": _loads(row["guardrails_json"], {}), "report": _loads(row["report_json"], {})} for row in evaluations],
            "runs": [{**dict(row), "details": _loads(row["details_json"], {})} for row in runs],
            "evidence_progress": {
                "linked": int(counts[1]) - unlinked_outcomes,
                "minimum": int((dict(settings) if settings else {}).get("min_samples", 30)),
                "credible_target": 100,
            },
            "kpis": {
                "ranking_acceptance_rate": accepted / decisions if decisions else None,
                "release_completion_rate": released / accepted if accepted else None,
                "post_release_performance": sum(performance_values) / len(performance_values) if performance_values else None,
                "log_loss": log_loss,
                "human_override_rate": outcome_breakdown.get("rejected", 0) / decisions if decisions else None,
                "latest_cycle_latency_ms": latest_run.get("latency_ms") if latest_run else None,
                "fallback_rate": latest_run_details.get("fallback_rate"),
            },
            "monitoring": {
                "recent_outcomes": len(recent), "previous_outcomes": len(previous),
                "recent_mean": recent_mean, "previous_mean": previous_mean,
                "outcome_drift": drift, "alert": bool(drift is not None and drift > 0.2),
            },
        }

    def run_shadow_cycle(
        self,
        recommendations: Iterable[dict[str, Any]],
        *,
        actor: str = "shadow-learning-automation",
        cycle_key: str = "",
    ) -> dict[str, Any]:
        """Capture recommendations and link later release outcomes without changing ranking."""
        key = cycle_key.strip() or f"shadow:{datetime.now(timezone.utc).date().isoformat()}"
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            cursor = conn.execute(
                """INSERT OR IGNORE INTO recommendation_learning_runs
                   (cycle_key, status, actor) VALUES (?, 'running', ?)""",
                (key, actor),
            )
            conn.commit()
            existing = conn.execute(
                "SELECT * FROM recommendation_learning_runs WHERE cycle_key = ?", (key,)
            ).fetchone()
        if cursor.rowcount == 0:
            return {**dict(existing), "idempotent_replay": True}

        started = perf_counter()
        try:
            items = list(recommendations)
            observed = self.observe(items, actor=actor, correlation_id=key)
            linked = 0
            with connect_database(self.db_path) as conn:
                conn.row_factory = __import__("sqlite3").Row
                releasable = conn.execute(
                    """SELECT e.id, e.release_date
                       FROM episodes e
                       JOIN recommendation_observations o ON o.id = (
                           SELECT MAX(latest.id) FROM recommendation_observations latest
                           WHERE latest.episode_id = e.id
                       )
                       WHERE LOWER(TRIM(COALESCE(e.release_status, ''))) = 'released'
                         AND NOT EXISTS (
                           SELECT 1 FROM recommendation_outcomes r
                           WHERE r.episode_id = e.id AND r.outcome_type = 'released'
                         )"""
                ).fetchall()
            for row in releasable:
                self.record_outcome(
                    int(row["id"]), outcome_type="released", value=None,
                    metadata={"release_date": row["release_date"]}, actor=actor,
                    source="shadow_learning_automation", occurred_at=str(row["release_date"] or ""),
                    idempotency_key=f"shadow-released:{row['id']}",
                )
                linked += 1

            current = self.status()
            evaluation = None
            if current["outcomes"]["linked"] >= int(current["settings"].get("min_samples", 30)):
                evaluation = self.evaluate(actor=actor)
            run_status = "completed" if evaluation else "insufficient_data"
            details = {
                "policy_version": observed["policy_version"],
                "ranking_changed": False,
                "evaluation_status": evaluation.get("status") if evaluation else None,
                "fallback_rate": (
                    sum((item.get("learning") or {}).get("mode") == "invalid_policy_fallback" for item in items)
                    / len(items)
                    if items else 0.0
                ),
            }
            values = (run_status, observed["recorded"], linked,
                      evaluation.get("id") if evaluation else None, _json(details))
        except Exception as exc:
            run_status = "failed"
            details = {"error_type": type(exc).__name__, "ranking_changed": False}
            values = (run_status, 0, 0, None, _json(details))
            raise
        finally:
            latency_ms = max(0, round((perf_counter() - started) * 1000))
            with connect_database(self.db_path) as conn:
                conn.row_factory = __import__("sqlite3").Row
                conn.execute(
                    """UPDATE recommendation_learning_runs SET status = ?, observations_recorded = ?,
                       outcomes_linked = ?, evaluation_id = ?, details_json = ?, latency_ms = ?
                       WHERE cycle_key = ?""",
                    (*values, latency_ms, key),
                )
                conn.commit()
                run = conn.execute(
                    "SELECT * FROM recommendation_learning_runs WHERE cycle_key = ?", (key,)
                ).fetchone()
        return {**dict(run), "details": details, "idempotent_replay": False}

    def observe(self, recommendations: Iterable[dict[str, Any]], *, actor: str, correlation_id: str = "") -> dict[str, Any]:
        items = list(recommendations)
        request_id = correlation_id.strip() or str(uuid4())
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            policy = conn.execute("SELECT version FROM recommendation_policies WHERE status = 'active'").fetchone()
            if not policy:
                raise LearningError("No active recommendation policy is configured")
            inserted = 0
            for rank, item in enumerate(items, 1):
                episode_id = int(item.get("id") or item.get("episode_id") or 0)
                if not episode_id:
                    continue
                cursor = conn.execute(
                    """INSERT OR IGNORE INTO recommendation_observations
                       (episode_id, policy_version, feature_schema_version, features_json, score, rank,
                        recommendation_snapshot, correlation_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (episode_id, policy["version"], FEATURE_SCHEMA_VERSION, _json(extract_features(item)),
                     float(item.get("priority_score") or 0), rank, _json(item), request_id),
                )
                inserted += max(0, cursor.rowcount)
            self._audit(conn, "recommendations_observed", actor, "Explicit recommendation snapshot", {"version": policy["version"], "count": inserted})
            conn.commit()
        return {"correlation_id": request_id, "recorded": inserted, "policy_version": policy["version"]}

    def record_outcome(self, episode_id: int, *, outcome_type: str, value: float | None, metadata: Any,
                       actor: str, source: str, occurred_at: str, idempotency_key: str) -> dict[str, Any]:
        kind = outcome_type.strip().lower()
        if kind not in OUTCOME_LABELS:
            raise LearningError("Unsupported recommendation outcome")
        numeric = OUTCOME_LABELS[kind] if value is None else _finite_float(value, field="Outcome value")
        if numeric is None or not 0 <= numeric <= 1:
            raise LearningError("Outcome value must be between 0 and 1")
        key = idempotency_key.strip() or str(uuid4())
        when = occurred_at.strip() or _now()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", when):
            when = f"{when}T00:00:00Z"
        try:
            parsed_when = datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError as exc:
            raise LearningError("Outcome timestamp must be a valid ISO 8601 datetime") from exc
        if parsed_when.tzinfo is None or parsed_when.utcoffset() is None:
            raise LearningError("Outcome timestamp must include a timezone")
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            if not conn.execute("SELECT 1 FROM episodes WHERE id = ?", (episode_id,)).fetchone():
                raise LearningError("Episode not found")
            existing = conn.execute("SELECT * FROM recommendation_outcomes WHERE idempotency_key = ?", (key,)).fetchone()
            if existing:
                return dict(existing)
            observation = conn.execute(
                """SELECT id FROM recommendation_observations
                   WHERE episode_id = ? AND datetime(created_at) <= datetime(?)
                   ORDER BY datetime(created_at) DESC, id DESC LIMIT 1""", (episode_id, when)
            ).fetchone()
            cursor = conn.execute(
                """INSERT INTO recommendation_outcomes
                   (episode_id, observation_id, outcome_type, value, metadata_json, actor, source, idempotency_key, occurred_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (episode_id, observation["id"] if observation else None, kind, numeric, _json(metadata or {}), actor, source, key, when),
            )
            saved = dict(conn.execute("SELECT * FROM recommendation_outcomes WHERE id = ?", (cursor.lastrowid,)).fetchone())
            self._audit(conn, "recommendation_outcome_recorded", actor, kind, {"version": "system", **saved})
            conn.commit()
            return saved

    @staticmethod
    def _log_loss(rows: list[tuple[dict[str, float], float]], weights: dict[str, float]) -> float:
        if not rows:
            return 1.0
        total = 0.0
        for features, label in rows:
            probability = max(1e-6, min(1 - 1e-6, _probability(features, weights)))
            total += -(label * math.log(probability) + (1 - label) * math.log(1 - probability))
        return total / len(rows)

    def evaluate(self, *, actor: str) -> dict[str, Any]:
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            conn.execute("BEGIN IMMEDIATE")
            settings = conn.execute("SELECT * FROM recommendation_learning_settings WHERE id = 1").fetchone()
            champion = conn.execute("SELECT * FROM recommendation_policies WHERE status = 'active'").fetchone()
            rows = conn.execute(
                """SELECT o.features_json, r.value, r.episode_id
                   FROM recommendation_outcomes r JOIN recommendation_observations o ON o.id = r.observation_id
                   WHERE o.feature_schema_version = ? ORDER BY r.occurred_at, r.id""", (FEATURE_SCHEMA_VERSION,)
            ).fetchall()
            sample_rows = []
            for row in rows:
                features = _loads(row["features_json"], {})
                if not isinstance(features, dict):
                    raise LearningError("Stored recommendation features are invalid")
                clean_features = {
                    name: _finite_float(features.get(name), field=f"Stored feature {name}", default=0.0)
                    for name in FEATURE_NAMES
                }
                sample_rows.append((int(row["episode_id"]), clean_features, _finite_float(row["value"], field="Stored outcome value")))
            episode_ids = list(dict.fromkeys(row[0] for row in sample_rows))
            minimum = int(settings["min_samples"])
            if len(episode_ids) < minimum:
                report = {"message": f"Need {minimum} independently linked episodes; found {len(episode_ids)}", "generated_at": _now()}
                cursor = conn.execute(
                    """INSERT INTO recommendation_evaluations
                       (candidate_version, champion_version, sample_count, baseline_metric, candidate_metric, uplift,
                        guardrails_json, report_json, status, created_by) VALUES (?, ?, ?, 0, 0, 0, ?, ?, 'insufficient_data', ?)""",
                    ("none", champion["version"], len(episode_ids), _json({"passed": False}), _json(report), actor),
                )
                conn.commit()
                return dict(conn.execute("SELECT * FROM recommendation_evaluations WHERE id = ?", (cursor.lastrowid,)).fetchone())

            split = max(1, int(len(episode_ids) * 0.8))
            training_ids = set(episode_ids[:split])
            validation_ids = set(episode_ids[split:] or episode_ids[-1:])
            training = [(features, label) for episode_id, features, label in sample_rows if episode_id in training_ids]
            validation = [(features, label) for episode_id, features, label in sample_rows if episode_id in validation_ids]
            current = _validated_weights(_loads(champion["weights_json"], {}))
            if current is None:
                raise LearningError("The active recommendation policy contains invalid weights")
            learned = dict(current)
            for _ in range(400):
                gradients = {name: 0.0 for name in FEATURE_NAMES}
                for features, label in training:
                    error = _probability(features, learned) - label
                    for name in FEATURE_NAMES:
                        gradients[name] += error * features.get(name, 0.0)
                for name in FEATURE_NAMES:
                    gradient = gradients[name] / len(training) + 0.02 * learned.get(name, 0.0)
                    learned[name] = learned.get(name, 0.0) - 0.15 * gradient
            bound = float(settings["max_weight_change"])
            bounded = {name: round(max(current.get(name, 0.0) - bound, min(current.get(name, 0.0) + bound, learned.get(name, 0.0))), 6) for name in FEATURE_NAMES}
            baseline_loss = self._log_loss(validation, current)
            candidate_loss = self._log_loss(validation, bounded)
            uplift = (baseline_loss - candidate_loss) / baseline_loss if baseline_loss else 0.0
            prediction_shift = sum(abs(_probability(features, bounded) - _probability(features, current)) for features, _ in validation) / len(validation)
            guardrails = {
                "non_sensitive_features_only": True,
                "independent_episode_split": not bool(training_ids & validation_ids),
                "label_diversity": len({round(label, 6) for _, _, label in sample_rows}) >= 2,
                "max_weight_change": max(abs(bounded[name] - current.get(name, 0.0)) for name in FEATURE_NAMES) <= bound + 1e-9,
                "mean_prediction_shift": round(prediction_shift, 6),
                "prediction_shift_ok": prediction_shift <= 0.15,
                "validation_samples": len(validation),
            }
            passed = uplift >= float(settings["min_uplift"]) and all((guardrails["non_sensitive_features_only"], guardrails["independent_episode_split"], guardrails["label_diversity"], guardrails["max_weight_change"], guardrails["prediction_shift_ok"]))
            digest = hashlib.sha256(_json({"parent": champion["version"], "weights": bounded, "episodes": len(episode_ids)}).encode()).hexdigest()[:10]
            version = f"release-learner-{digest}"
            summary = {"sample_count": len(episode_ids), "outcome_count": len(sample_rows), "baseline_log_loss": baseline_loss, "candidate_log_loss": candidate_loss, "uplift": uplift, "feature_schema_version": FEATURE_SCHEMA_VERSION}
            conn.execute(
                """INSERT OR IGNORE INTO recommendation_policies
                   (version, parent_version, status, weights_json, training_summary_json, created_by)
                   VALUES (?, ?, 'draft', ?, ?, ?)""",
                (version, champion["version"], _json(bounded), _json(summary), actor),
            )
            cursor = conn.execute(
                """INSERT INTO recommendation_evaluations
                   (candidate_version, champion_version, sample_count, baseline_metric, candidate_metric, uplift,
                    guardrails_json, report_json, status, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (version, champion["version"], len(episode_ids), baseline_loss, candidate_loss, uplift, _json(guardrails), _json(summary), "passed" if passed else "failed", actor),
            )
            self._audit(conn, "recommendation_policy_evaluated", actor, "Offline holdout evaluation", {"version": version, "evaluation_id": cursor.lastrowid, "status": "passed" if passed else "failed"})
            conn.commit()
            result = dict(conn.execute("SELECT * FROM recommendation_evaluations WHERE id = ?", (cursor.lastrowid,)).fetchone())
        return result

    def promote(self, version: str, *, actor: str, reason: str, expected_row_version: int, automatic: bool = False) -> dict[str, Any]:
        if not reason.strip():
            raise LearningError("A promotion reason is required")
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            conn.execute("BEGIN IMMEDIATE")
            settings = conn.execute("SELECT * FROM recommendation_learning_settings WHERE id = 1").fetchone()
            if automatic and (not settings["automation_enabled"] or settings["kill_switch"]):
                raise LearningError("Automatic promotion is disabled by the learning safety controls")
            candidate = conn.execute("SELECT * FROM recommendation_policies WHERE version = ?", (version,)).fetchone()
            if not candidate or candidate["status"] not in {"draft", "approved"}:
                raise LearningError("Only a draft or approved policy can be promoted")
            if int(candidate["row_version"]) != int(expected_row_version):
                raise LearningError("Policy changed; refresh before promoting")
            evaluation = conn.execute(
                "SELECT * FROM recommendation_evaluations WHERE candidate_version = ? AND status = 'passed' ORDER BY id DESC LIMIT 1", (version,)
            ).fetchone()
            if not evaluation:
                raise LearningError("Policy must pass offline evaluation before promotion")
            current = conn.execute("SELECT * FROM recommendation_policies WHERE status = 'active'").fetchone()
            conn.execute("UPDATE recommendation_policies SET status = 'retired', row_version = row_version + 1 WHERE status = 'active'")
            conn.execute(
                """UPDATE recommendation_policies SET status = 'active', approved_by = ?, approval_reason = ?,
                   approved_at = CURRENT_TIMESTAMP, row_version = row_version + 1 WHERE version = ?""", (actor, reason, version),
            )
            action = "auto_activated" if automatic else "activated"
            conn.execute(
                "INSERT INTO recommendation_deployments (policy_version, previous_version, action, actor, reason, evaluation_id) VALUES (?, ?, ?, ?, ?, ?)",
                (version, current["version"] if current else None, action, actor, reason, evaluation["id"]),
            )
            self._audit(conn, "recommendation_policy_activated", actor, reason, {"version": version, "previous_version": current["version"] if current else None})
            conn.commit()
        return self.status()["active_policy"]

    def rollback(self, *, actor: str, reason: str) -> dict[str, Any]:
        if not reason.strip():
            raise LearningError("A rollback reason is required")
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            conn.execute("BEGIN IMMEDIATE")
            active = conn.execute("SELECT * FROM recommendation_policies WHERE status = 'active'").fetchone()
            deployment = conn.execute("SELECT * FROM recommendation_deployments WHERE policy_version = ? ORDER BY id DESC LIMIT 1", (active["version"],)).fetchone() if active else None
            previous = conn.execute("SELECT * FROM recommendation_policies WHERE version = ?", (deployment["previous_version"],)).fetchone() if deployment and deployment["previous_version"] else None
            if not active or not previous:
                raise LearningError("No previous deployed policy is available for rollback")
            conn.execute("UPDATE recommendation_policies SET status = 'retired', row_version = row_version + 1 WHERE id = ?", (active["id"],))
            conn.execute("UPDATE recommendation_policies SET status = 'active', row_version = row_version + 1 WHERE id = ?", (previous["id"],))
            conn.execute("INSERT INTO recommendation_deployments (policy_version, previous_version, action, actor, reason) VALUES (?, ?, 'rolled_back', ?, ?)", (previous["version"], active["version"], actor, reason))
            self._audit(conn, "recommendation_policy_rolled_back", actor, reason, {"version": previous["version"], "previous_version": active["version"]})
            conn.commit()
        return self.status()["active_policy"]

    def update_settings(self, payload: dict[str, Any], *, actor: str) -> dict[str, Any]:
        values = {
            "automation_enabled": 1 if payload.get("automation_enabled") is True else 0,
            "kill_switch": 1 if payload.get("kill_switch", True) is True else 0,
            "min_samples": int(payload.get("min_samples", 30)),
            "min_uplift": _finite_float(payload.get("min_uplift", 0.03), field="Minimum uplift"),
            "max_weight_change": _finite_float(payload.get("max_weight_change", 0.25), field="Maximum weight change"),
        }
        if not 20 <= values["min_samples"] <= 10000 or not 0 <= values["min_uplift"] <= 1 or not 0 < values["max_weight_change"] <= 0.5:
            raise LearningError("Learning safety settings are outside their allowed bounds")
        with connect_database(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """UPDATE recommendation_learning_settings SET automation_enabled = ?, kill_switch = ?, min_samples = ?,
                   min_uplift = ?, max_weight_change = ?, updated_by = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1""",
                (*values.values(), actor),
            )
            self._audit(conn, "recommendation_learning_settings_updated", actor, "Safety controls updated", {"version": "settings", **values})
            conn.commit()
        return self.status()["settings"]

    def run_cycle(self, *, actor: str = "learning-automation") -> dict[str, Any]:
        """Run one idempotent automation cycle; schedulers may invoke this safely."""
        status = self.status()
        settings = status["settings"]
        if not settings.get("automation_enabled") or settings.get("kill_switch"):
            return {"status": "blocked", "reason": "automation_disabled_or_killed", "active_policy": status["active_policy"]}
        if status["monitoring"]["alert"]:
            active = status.get("active_policy") or {}
            if active.get("version") and active.get("version") != "release-planner-v1":
                restored = self.rollback(actor=actor, reason="Automatic rollback after outcome-drift guardrail alert")
                return {"status": "rolled_back", "reason": "outcome_drift_alert", "active_policy": restored}
            return {"status": "blocked", "reason": "outcome_drift_alert", "active_policy": active}
        evaluation = self.evaluate(actor=actor)
        if evaluation["status"] != "passed":
            return {"status": "not_promoted", "reason": evaluation["status"], "evaluation": evaluation}
        candidate = next(
            policy for policy in self.status()["policies"] if policy["version"] == evaluation["candidate_version"]
        )
        active = self.promote(
            candidate["version"], actor=actor,
            reason=f"Bounded automatic promotion after evaluation {evaluation['id']}",
            expected_row_version=candidate["row_version"], automatic=True,
        )
        return {"status": "promoted", "evaluation": evaluation, "active_policy": active}
