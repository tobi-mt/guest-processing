"""Regression checks for the dynamic HTML sinks exercised by browser tests."""

from pathlib import Path


STATIC = Path(__file__).parents[1] / "src" / "guest_database_manager" / "static"


def test_operations_interview_identity_fields_are_escaped_before_inner_html():
    source = (STATIC / "operations.js").read_text(encoding="utf-8")
    assert '<h3>${escapeHtml(interview.guest_name || "Unnamed guest")}</h3>' in source
    assert '<p>${escapeHtml(interview.title || "Mirror Talk interview")}</p>' in source
    assert 'value="${escapeHtml(interview.guest_name || "")}"' in source
    assert '<pre>${escapeHtml(preview.body)}</pre>' in source


def test_planning_episode_and_generated_copy_fields_are_escaped_before_inner_html():
    source = (STATIC / "planning.js").read_text(encoding="utf-8")
    assert '<h3>${escapeHtml(episode.episode_title || "Untitled episode")}</h3>' in source
    assert '<p>${escapeHtml(episode.guest_name || "Guest not set")}</p>' in source
    assert "${escapeHtml(copyAssist.social_caption || \"\")}" in source
    assert "${escapeHtml(copyAssist.newsletter_blurb || \"\")}" in source


def test_dashboard_email_composer_escapes_guest_name():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert '<h4>${escapeHtml(guest.full_name || "Guest")}</h4>' in source
