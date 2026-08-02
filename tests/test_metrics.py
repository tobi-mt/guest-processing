from datetime import datetime, timezone

from guest_database_manager.metrics import build_operational_metrics


def test_metrics_publish_definitions_freshness_and_distributions(temp_db):
    guest_id = temp_db.insert_guest({"full_name": "Metric Guest", "email": "metric@example.com"})
    with temp_db._connect() as conn:
        conn.execute(
            """UPDATE guest_applications SET submitted_at = '2026-08-01 08:00:00',
               decided_at = '2026-08-01 20:00:00', status = 'accepted' WHERE guest_id = ?""",
            (guest_id,),
        )
        conn.execute(
            """INSERT INTO interviews (guest_id, guest_name, scheduled_for, status, confirmation_status)
               VALUES (?, 'Metric Guest', '2026-08-03 12:00:00', 'scheduled', 'confirmed')""",
            (guest_id,),
        )
        conn.execute(
            """INSERT INTO episodes
               (guest_id, guest_name, episode_title, interview_date, release_date, release_status, production_status,
                promotion_status, original_planned_release_date)
               VALUES (?, 'Metric Guest', 'Metric Episode', '2026-07-01', '2026-07-11', 'released', 'released',
                       'released', '2026-07-12')""",
            (guest_id,),
        )

    metrics = build_operational_metrics(
        temp_db.db_path, now=datetime(2026, 8, 2, tzinfo=timezone.utc)
    )

    assert metrics["freshness"] == "live"
    assert metrics["values"]["guest_decision_lead_hours"]["median"] == 12
    assert metrics["values"]["interview_to_release_days"]["median"] == 10
    assert metrics["values"]["confirmation_coverage_pct"] == 100
    assert metrics["values"]["on_time_release_pct"] == 100
    assert metrics["quality"]["on_time_release_baseline_count"] == 1
    assert metrics["definitions"]["guest_decision_lead_hours"]["owner"]
