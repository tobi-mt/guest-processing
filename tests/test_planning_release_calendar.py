"""Static contracts for the interactive release calendar and safe transcript review."""

from pathlib import Path


STATIC_ROOT = Path(__file__).parents[1] / "src" / "guest_database_manager" / "static"


def test_planning_exposes_calendar_navigation_legend_and_details_dialog() -> None:
    html = (STATIC_ROOT / "planning.html").read_text(encoding="utf-8")

    for element_id in (
        "calendar-previous",
        "calendar-today",
        "calendar-next",
        "release-calendar",
        "episode-details-modal",
        "episode-details-body",
        "episode-details-edit",
    ):
        assert f'id="{element_id}"' in html
    assert 'aria-modal="true"' in html
    assert "Scheduled" in html
    assert "Released" in html
    assert "Readiness risk" in html


def test_planning_exposes_explicit_stable_release_sort_modes() -> None:
    html = (STATIC_ROOT / "planning.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")
    sort_javascript = (STATIC_ROOT / "planning-sort.js").read_text(encoding="utf-8")

    for sort_mode in (
        "release_asc",
        "release_desc",
        "episode_number_asc",
        "episode_number_desc",
        "status_release",
        "updated_desc",
    ):
        assert f'value="{sort_mode}"' in html
    assert "PlanningSort.compareEpisodes" in javascript
    assert "stableTieBreak" in sort_javascript
    assert 'mode === "release_desc"' in sort_javascript


def test_transcript_sync_is_a_review_then_apply_workflow() -> None:
    html = (STATIC_ROOT / "planning.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")

    assert "Review Transcript Matches" in html
    assert "Transcript sync never overwrites it" in html
    assert "Apply Selected Matches" in javascript
    assert "preview_only: false" in javascript
    assert "approved_matches: approvedMatches" in javascript


def test_calendar_uses_distinct_status_markers_and_safe_details_rendering() -> None:
    javascript = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")
    css = (STATIC_ROOT / "operations.css").read_text(encoding="utf-8")

    assert 'return "released"' in javascript
    assert 'return "risk"' in javascript
    assert 'return "scheduled"' in javascript
    assert "data-calendar-episode" in javascript
    assert "openEpisodeDetailsModal" in javascript
    assert ".calendar-event-dot.scheduled" in css
    assert ".calendar-event-dot.released" in css
    assert ".calendar-event-dot.risk" in css
