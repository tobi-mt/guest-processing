"""Fast accessibility contract checks for the three critical workspaces."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


STATIC_ROOT = Path(__file__).parents[1] / "src" / "guest_database_manager" / "static"
WORKSPACES = ("index.html", "operations.html", "planning.html", "booking.html")


def _strip_markup(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


@pytest.mark.parametrize("filename", WORKSPACES)
def test_workspace_has_unique_literal_ids(filename: str) -> None:
    source = (STATIC_ROOT / filename).read_text(encoding="utf-8")
    ids = re.findall(r'\bid=["\']([^"\']+)["\']', source)

    duplicates = sorted({element_id for element_id in ids if ids.count(element_id) > 1})
    assert duplicates == []


@pytest.mark.parametrize("filename", WORKSPACES)
def test_literal_buttons_have_accessible_names(filename: str) -> None:
    source = (STATIC_ROOT / filename).read_text(encoding="utf-8")
    unnamed: list[str] = []

    for match in re.finditer(r"<button\b([^>]*)>(.*?)</button>", source, re.I | re.S):
        attributes, content = match.groups()
        has_aria_name = re.search(r'\baria-label=["\'][^"\']+["\']', attributes, re.I)
        if not has_aria_name and not _strip_markup(content):
            unnamed.append(match.group(0)[:120])

    assert unnamed == []


@pytest.mark.parametrize("filename", WORKSPACES)
def test_literal_form_controls_are_labelled(filename: str) -> None:
    source = (STATIC_ROOT / filename).read_text(encoding="utf-8")
    label_blocks = [
        (match.start(), match.end())
        for match in re.finditer(r"<label\b[^>]*>.*?</label>", source, re.I | re.S)
    ]
    labelled_ids = set(re.findall(r'<label\b[^>]*\bfor=["\']([^"\']+)["\']', source, re.I))
    unlabelled: list[str] = []

    for match in re.finditer(r"<(input|select|textarea)\b([^>]*)>", source, re.I | re.S):
        tag, attributes = match.groups()
        if tag.lower() == "input" and re.search(
            r'\btype=["\']hidden["\']', attributes, re.I
        ):
            continue
        inside_label = any(start <= match.start() < end for start, end in label_blocks)
        has_aria_name = re.search(r'\baria-label=["\'][^"\']+["\']', attributes, re.I)
        control_id = re.search(r'\bid=["\']([^"\']+)["\']', attributes, re.I)
        referenced = bool(control_id and control_id.group(1) in labelled_ids)
        if not (inside_label or has_aria_name or referenced):
            unlabelled.append(match.group(0)[:120])

    assert unlabelled == []


@pytest.mark.parametrize("filename", WORKSPACES)
def test_assets_are_versioned_and_private_workspaces_are_keyboard_ready(filename: str) -> None:
    source = (STATIC_ROOT / filename).read_text(encoding="utf-8")

    asset_urls = [
        url
        for url in re.findall(r'(?:src|href)=["\'](/static/[^"\']+)["\']', source)
        if re.search(r"\.(?:css|js)(?:\?|$)", url)
    ]
    assert asset_urls
    assert all("?v=" in url for url in asset_urls)
    if 'role="tablist"' in source:
        assert 'role="tab"' in source
        assert 'aria-selected="true"' in source


def test_accessibility_media_preferences_are_supported() -> None:
    styles = "\n".join(
        (STATIC_ROOT / filename).read_text(encoding="utf-8")
        for filename in ("styles.css", "operations.css")
    )

    assert "prefers-reduced-motion: reduce" in styles
    assert "forced-colors: active" in styles


def test_booking_confirmation_form_stays_hidden_after_a_booking_is_found() -> None:
    styles = (STATIC_ROOT / "booking.css").read_text(encoding="utf-8")

    assert ".booking-form.hidden" in styles
    assert re.search(r"\.booking-form\.hidden\s*\{\s*display:\s*none", styles)


def test_intake_continue_uses_immediate_browser_validation_feedback() -> None:
    """Validation failures must not look like an unresponsive Continue button."""
    javascript = (STATIC_ROOT / "intake.js").read_text(encoding="utf-8")

    assert "function showFieldValidation(field, customMessage = \"\")" in javascript
    assert "field.reportValidity();" in javascript
    assert "showFieldValidation(selfAttestationField, errorText);" in javascript
    assert 'intake.js?v=20260817.1' in (STATIC_ROOT / "intake.html").read_text(encoding="utf-8")


def test_workspace_heroes_use_compact_responsive_stats_layouts() -> None:
    dashboard = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    operations = (STATIC_ROOT / "operations.html").read_text(encoding="utf-8")
    planning = (STATIC_ROOT / "planning.html").read_text(encoding="utf-8")
    styles = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")
    operations_styles = (STATIC_ROOT / "operations.css").read_text(encoding="utf-8")

    assert 'class="hero dashboard-hero"' in dashboard
    assert 'class="hero operations-hero interview-hero"' in operations
    assert 'class="hero operations-hero planning-hero"' in planning
    assert all('class="hero-card stats-card"' in source for source in (dashboard, operations, planning))
    assert "align-items: start" in styles
    assert "@media (max-width: 1050px)" in styles
    assert ".dashboard-insights" in styles
    assert ".planning-hero .metric-grid" in operations_styles
    assert ".interview-hero .metric-grid" in operations_styles


def test_operations_hero_uses_reusable_ai_status_styles() -> None:
    source = (STATIC_ROOT / "operations.html").read_text(encoding="utf-8")

    ai_card = re.search(r'<div id="ai-features-card"([^>]*)>', source)
    assert ai_card
    assert 'class="ai-status-card"' in ai_card.group(1)
    assert "style=" not in ai_card.group(1)


def test_dashboard_result_modal_has_dialog_semantics_and_focus_management() -> None:
    html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'id="ai-modal" class="modal hidden" role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'aria-labelledby="ai-modal-title"' in html
    assert 'aria-label="Close result dialog"' in html
    assert "aiModalClose?.focus()" in javascript
    assert 'event.key === "Escape"' in javascript
    assert "event.stopPropagation()" in javascript
    assert "window.requestAnimationFrame" in javascript
    assert "returnFocus.focus()" in javascript


def test_work_queue_cards_progressively_disclose_secondary_actions() -> None:
    dashboard = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    operations_javascript = (STATIC_ROOT / "operations.js").read_text(encoding="utf-8")
    styles = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")
    operations_styles = (STATIC_ROOT / "operations.css").read_text(encoding="utf-8")

    assert 'class="guest-card-details"' in dashboard
    assert "Review profile and actions" in dashboard
    assert 'class="interview-more-actions"' in operations_javascript
    assert "Communication, calendar, and record actions" in operations_javascript
    assert ".guest-card-details > summary" in styles
    assert ".interview-more-actions > summary" in operations_styles


def test_mobile_planning_keeps_calendar_and_workflow_labels_readable() -> None:
    styles = (STATIC_ROOT / "operations.css").read_text(encoding="utf-8")

    assert ".calendar-grid {\n    min-width: 0;" in styles
    assert ".production-rail.production-rail" in styles
    assert "grid-template-columns: 22px 34px minmax(0, 1fr);" in styles


def test_dashboard_renders_release_timing_and_dated_guest_events() -> None:
    javascript = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert "Prospective release timing" in javascript
    assert "Dated launches and appearances" in javascript
    assert "release_timing_recommendation" in javascript
