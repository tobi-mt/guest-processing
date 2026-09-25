"""Fast accessibility contract checks for the three critical workspaces."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


STATIC_ROOT = Path(__file__).parents[1] / "src" / "guest_database_manager" / "static"
WORKSPACES = ("index.html", "operations.html", "planning.html", "booking.html", "partners.html", "intake.html")


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
    assert 'intake.js?v=20260925.2' in (STATIC_ROOT / "intake.html").read_text(encoding="utf-8")


def test_intake_attestation_state_is_preserved_and_submitted_explicitly() -> None:
    """A checked self-attestation must survive draft restore and reach the API."""
    javascript = (STATIC_ROOT / "intake.js").read_text(encoding="utf-8")

    assert 'values[field.name] = field.checked;' in javascript
    assert 'field.checked = value === true || value === field.value;' in javascript
    assert 'if (!validateSelfAttestation())' in javascript
    assert 'payload.self_attestation = selfAttestationField?.checked ? "yes" : "";' in javascript


def test_intake_redesign_is_three_steps_and_labels_choice_architecture() -> None:
    """The shorter application must distinguish core questions from optional context."""
    source = (STATIC_ROOT / "intake.html").read_text(encoding="utf-8")

    assert source.count('class="form-step') == 3
    assert "Step 1 of 3" in source
    assert "About 8 to 12 minutes" in source
    assert source.count('class="required-marker"') >= 10
    assert source.count('class="optional-marker"') >= 6
    assert "Follower count is not part of editorial eligibility" in source
    assert "Boundaries do not count against your application" in source
    assert 'intake.css?v=20260925.1' in source


def test_intake_preserves_specific_errors_and_debounces_draft_writes() -> None:
    javascript = (STATIC_ROOT / "intake.js").read_text(encoding="utf-8")

    assert 'const stepNames = ["Contact", "Your Story", "The Episode"];' in javascript
    assert "function scheduleDraftSave()" in javascript
    assert "scheduleDraftSave();" in javascript
    assert "if (event.target === applicationRoleField)" in javascript
    assert 'setMessage("Please complete the highlighted field before submitting."' not in javascript


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


def test_routine_creation_forms_hide_optional_fields_and_offer_safe_defaults() -> None:
    dashboard = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    operations = (STATIC_ROOT / "operations.html").read_text(encoding="utf-8")
    dashboard_js = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    operations_js = (STATIC_ROOT / "operations.js").read_text(encoding="utf-8")
    planning = (STATIC_ROOT / "planning.html").read_text(encoding="utf-8")
    planning_js = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")

    assert "Only a name is required" in dashboard
    assert "Contact and profile details" in dashboard
    assert "Story and editorial context" in dashboard
    assert "Assignment, links, and status" in operations
    assert 'autocomplete="email"' in dashboard
    assert "normalizeOptionalUrl" in dashboard_js
    assert "A soulful conversation with ${guestName}" in operations_js
    assert "!interviewForm.elements.id.value" in operations_js
    assert "That is enough to save an episode" in planning
    assert "Context and classification" in planning
    assert "Dates, owner, and release plan" in planning
    assert "Links, transcript, and notes" in planning
    assert 'data-episode-section="context"' in planning
    assert "episodeTitleInput.dataset.autofilled" in planning_js
    assert "episodeForm.elements.id.value" in planning_js


def test_guest_waiting_state_has_a_separate_dashboard_bucket() -> None:
    dashboard = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    dashboard_js = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'data-guest-preset="waiting_on_guest">Waiting on Guest' in dashboard
    assert 'applicationStatus !== "needs_information"' in dashboard_js
    assert 'preset === "waiting_on_guest"' in dashboard_js
    assert 'return "Waiting on guest"' in dashboard_js
    assert 'waitingOnGuest ? "Waiting on guest"' in dashboard_js


def test_guest_research_eligibility_accepts_both_social_field_names() -> None:
    dashboard_js = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert "function guestHasPublicProfileHint(guest)" in dashboard_js
    assert "normalizeText(guest.social_media_handles)" in dashboard_js
    assert "normalizeText(guest.social_handles)" in dashboard_js
    assert "researchButton && !guestHasPublicProfileHint(guest)" in dashboard_js


def test_guest_ai_review_explains_pillar_confidence_and_evidence() -> None:
    dashboard_js = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'class="pillar-score-row"' in dashboard_js
    assert '<progress max="100"' in dashboard_js
    assert "Why these pillars?" in dashboard_js
    assert "Supporting evidence" in dashboard_js
    assert "Promising conversation angles" in dashboard_js


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


def test_scheduling_intelligence_sidebar_never_requires_horizontal_scrolling() -> None:
    html = (STATIC_ROOT / "planning.html").read_text(encoding="utf-8")
    styles = (STATIC_ROOT / "operations.css").read_text(encoding="utf-8")

    assert 'operations.css?v=20260925.3' in html
    assert "overflow-x: hidden;\n  overflow-y: auto;" in styles
    assert (
        '.operations-form-panel > .workspace-panel[data-planning-panel="scheduling_intelligence"] .guest-form {\n'
        "  grid-template-columns: minmax(0, 1fr);"
    ) in styles
    assert (
        '.operations-form-panel > .workspace-panel[data-planning-panel="scheduling_intelligence"] textarea,'
        in styles
    )
    assert "overflow-wrap: anywhere;" in styles


def test_availability_calendar_preserves_week_context_and_accessible_dates() -> None:
    html = (STATIC_ROOT / "availability.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "availability.js").read_text(encoding="utf-8")
    styles = (STATIC_ROOT / "availability.css").read_text(encoding="utf-8")

    assert 'class="availability-calendar-scroll" tabindex="0" role="region"' in html
    assert 'role="grid" aria-labelledby="calendar-title"' in html
    assert '["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]' in javascript
    assert "function isoWeekNumber(date)" in javascript
    assert 'role="rowheader" aria-label="ISO week ${weekNumber}"' in javascript
    assert 'aria-current="date"' in javascript
    assert 'weekday: "long", year: "numeric", month: "long", day: "numeric"' in javascript
    assert "grid-template-columns: 48px repeat(7" in styles
    assert ".calendar-day.today" in styles
    assert "overflow-x: auto" in styles
    assert "grid-template-columns: repeat(2, 1fr)" not in styles
    assert "availability.css?v=20260922.1" in html
    assert "availability.js?v=20260922.1" in html


def test_dashboard_renders_release_timing_and_dated_guest_events() -> None:
    javascript = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert "Prospective release timing" in javascript
    assert "Dated launches and appearances" in javascript
    assert "release_timing_recommendation" in javascript
    assert "Guest Copilot Research" in javascript
    assert "Not researched yet" in javascript
    assert "await loadGuests();" in javascript


def test_partner_recipient_filter_reveals_actions_and_preserves_selected_recipient() -> None:
    html = (STATIC_ROOT / "partners.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "partners.js").read_text(encoding="utf-8")

    assert 'id="clear-partner-filters"' in html
    assert 'id="partner-stage-filters"' in html
    assert 'id="partner-review-queue"' in html
    assert html.index('id="partner-review-queue"') < html.index('id="partner-tools"')
    assert "filterProspects({revealStage:true})" in javascript
    assert "card.querySelector('.partner-workflow').open = true" in javascript
    assert 'class="partner-recipient"' in javascript
    assert "async function reloadAndReveal(prospectId" in javascript
    assert "clearFilters:Boolean(changesStage)" in javascript
    assert "revealProspect(prospectId)" in javascript
    assert "Continue: ${stageLabel[stage]}" in javascript


def test_growth_dashboard_preserves_zero_values_and_has_import_status() -> None:
    html = (STATIC_ROOT / "planning.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")

    assert 'id="growth-intelligence-dashboard" aria-live="polite"' in html
    assert 'id="analytics-import-message" class="message" aria-live="polite"' in html
    assert 'planning-intelligence.js?v=20260925.2' in html
    assert 'planning.js?v=20260925.2' in html
    assert 'return String(value ?? "")' in javascript
    assert "escapeHtml(reach.organic ?? 0)" in javascript
    assert "escapeHtml(reach.paid ?? 0)" in javascript
    assert "escapeHtml(quality.mfs_ready ?? 0)" in javascript
    assert "escapeHtml(quality.episodes_with_evidence ?? 0)" in javascript
    assert "String(item.actual_share_pct ?? 0)" in javascript
    assert "String(quality.unclassified_released_episodes ?? 0)" in javascript


def test_primary_workspaces_share_search_personal_view_and_mobile_navigation() -> None:
    shell = (STATIC_ROOT / "workspace-shell.js").read_text(encoding="utf-8")
    styles = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")
    for name in ("index.html", "operations.html", "planning.html"):
        html = (STATIC_ROOT / name).read_text(encoding="utf-8")
        assert 'workspace-shell.js?v=20260923.3' in html
        assert 'styles.css?v=20260923.2' in html
    assert 'id="workspace-command-dialog"' in shell
    assert "/api/search?q=" in shell
    assert "/api/personal-briefing?window=" in shell
    assert 'mirror-talk-recent-records' in shell
    assert 'beforeunload' in shell
    assert 'mirror-talk-details-state' in shell
    assert 'data-toggle-density' in shell
    assert ".mobile-workspace-nav" in styles


def test_guided_import_replaces_raw_json_and_exposes_history_and_reviews() -> None:
    html = (STATIC_ROOT / "planning.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "planning-intelligence.js").read_text(encoding="utf-8")
    styles = (STATIC_ROOT / "operations.css").read_text(encoding="utf-8")
    assert "Observation JSON" not in html
    assert 'id="analytics-import-history"' in html
    assert 'id="outcome-review-queue"' in html
    assert "Spotify currently hosts the podcast and its RSS feed" in html
    assert "Other hosting provider" in html
    assert "Do not import the same Spotify period twice" in html
    assert "repeat(auto-fit, minmax(min(100%, 18rem), 1fr))" in styles
    assert "renderImportHistory" in javascript
    assert "renderOutcomeReviews" in javascript
    assert "Audience balance" in javascript
    assert "Blockers" in javascript


def test_learning_console_exposes_shadow_progress_and_safe_automation() -> None:
    html = (STATIC_ROOT / "planning.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")
    assert 'id="learning-shadow-cycle"' in html
    assert "planning.js?v=20260925.2" in html
    assert "operations.css?v=20260925.3" in html
    assert '"/api/recommendation-learning/shadow-cycle"' in javascript
    assert "credible target" in javascript
    assert "promotion ${automationLocked ? \"locked\" : \"enabled\"}" in javascript


def test_editorial_mix_fits_its_card_at_narrow_container_widths() -> None:
    javascript = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")
    styles = (STATIC_ROOT / "operations.css").read_text(encoding="utf-8")

    assert 'class="operations-preview editorial-mix-card"' in javascript
    assert 'data-label="12-release guardrail"' in javascript
    assert ".editorial-mix-card table {\n  table-layout: fixed;" in styles
    assert "@container editorial-mix (max-width: 480px)" in styles
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in styles
    assert "content: attr(data-label);" in styles


def test_scheduling_intelligence_prioritizes_decisions_and_guides_evidence_import() -> None:
    html = (STATIC_ROOT / "planning.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "planning-intelligence.js").read_text(encoding="utf-8")
    planning_javascript = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")
    styles = (STATIC_ROOT / "operations.css").read_text(encoding="utf-8")

    assert 'id="exception-center" class="exception-center" aria-live="polite"' in html
    assert 'id="analytics-import-form"' in html
    assert 'class="provider-export-grid"' in html
    assert 'data-import-provider="spotify"' in html
    assert 'data-import-provider="apple_podcasts"' in html
    assert 'data-import-provider="podcast_host"' in html
    assert 'id="analytics-mapping-fields"' in html
    assert 'id="analytics-preview" class="analytics-preview hidden" aria-live="polite"' in html
    assert 'class="operations-tool scheduling-admin-hub"' in html
    assert 'id="recommendation-comparison-grid"' in html
    assert 'request("/api/growth-intelligence/preview"' in javascript
    assert 'document.querySelectorAll("[data-import-provider]")' in javascript
    assert 'request("/api/exceptions")' in javascript
    assert "renderRecommendationComparison" in javascript
    assert "recommendation_decision" in planning_javascript
    assert ".comparison-grid" in styles
    assert ".analytics-mapping-grid" in styles
    assert ".provider-export-grid" in styles
