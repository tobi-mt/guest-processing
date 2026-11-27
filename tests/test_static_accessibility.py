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


def test_booking_slot_selection_is_explicit_and_conflicts_are_contextual() -> None:
    """Guests should get an obvious selected state without seeing internal calendar details."""
    javascript = (STATIC_ROOT / "booking.js").read_text(encoding="utf-8")
    html = (STATIC_ROOT / "booking.html").read_text(encoding="utf-8")

    assert 'button.textContent = `Selected: ${slotTime} · ${slotTimezone}`;' in javascript
    assert 'bookingSubmit.focus({ preventScroll: true });' in javascript
    assert 'button.disabled = true;' in javascript
    assert "existing calendar event" not in javascript
    assert "safety window" not in javascript
    assert 'brand-system.css?v=20261018.1' in html
    assert 'booking.css?v=20261018.1' in html
    assert 'booking.js?v=20261016.3' in html


def test_partner_async_submit_handlers_retain_the_form_reference() -> None:
    """Async submit completion must not read the browser-cleared event.currentTarget."""
    javascript = (STATIC_ROOT / "partners.js").read_text(encoding="utf-8")
    html = (STATIC_ROOT / "partners.html").read_text(encoding="utf-8")

    assert javascript.count("const target = event.currentTarget;") == 2
    assert "event.currentTarget.reset()" not in javascript
    assert 'partners.js?v=20261016.1' in html


def test_intake_continue_uses_immediate_browser_validation_feedback() -> None:
    """Validation failures must not look like an unresponsive Continue button."""
    javascript = (STATIC_ROOT / "intake.js").read_text(encoding="utf-8")

    assert "function showFieldValidation(field, customMessage = \"\")" in javascript
    assert "field.reportValidity();" in javascript
    assert "showFieldValidation(selfAttestationField, errorText);" in javascript
    assert 'intake.js?v=20261016.1' in (STATIC_ROOT / "intake.html").read_text(encoding="utf-8")


def test_intake_attestation_state_is_preserved_and_submitted_explicitly() -> None:
    """A checked self-attestation must survive draft restore and reach the API."""
    javascript = (STATIC_ROOT / "intake.js").read_text(encoding="utf-8")

    assert 'values[field.name] = field.checked;' in javascript
    assert 'field.checked = value === true || value === field.value;' in javascript
    assert 'if (!validateSelfAttestation())' in javascript
    assert 'payload.self_attestation = selfAttestationField?.checked ? "yes" : "";' in javascript


def test_intake_omits_conditional_helper_fields_from_submission() -> None:
    """Hidden or stale conditional details must not reach server-side spam validation."""
    javascript = (STATIC_ROOT / "intake.js").read_text(encoding="utf-8")

    for field_name in (
        "faith_detail",
        "alignment_detail",
        "experience_detail",
        "favorite_quote_detail",
        "social_other",
    ):
        assert f'"{field_name}",' in javascript
    assert ".forEach((fieldName) => delete payload[fieldName]);" in javascript


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
    assert 'brand-system.css?v=20261018.1' in source
    assert 'intake.css?v=20261018.1' in source


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


def test_workspace_navigation_cannot_overlap_page_actions_at_narrow_desktop_widths() -> None:
    """The fixed desktop toolbar must yield before zoom and split-screen layouts collide."""
    styles = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "workspace-shell.js").read_text(encoding="utf-8")

    assert '.classList.add("has-workspace-shell")' in javascript
    assert ".has-workspace-shell .page-shell" in styles
    responsive = styles[styles.index("@media (max-width: 1050px)") :]
    assert ".workspace-utility-bar { display: none; }" in responsive
    assert ".mobile-workspace-nav" in responsive
    assert ".has-workspace-shell .page-shell { padding-top: 32px; }" in responsive


def test_operations_hero_uses_reusable_ai_status_styles() -> None:
    source = (STATIC_ROOT / "operations.html").read_text(encoding="utf-8")

    ai_card = re.search(r'<div id="ai-features-card"([^>]*)>', source)
    assert ai_card
    assert 'class="ai-status-card"' in ai_card.group(1)
    assert "style=" not in ai_card.group(1)


def test_weekly_confirmations_uses_one_empty_state_message() -> None:
    html = (STATIC_ROOT / "operations.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "operations.js").read_text(encoding="utf-8")

    assert javascript.count("No reminder emails are due for this week.") == 1
    assert "operations.js?v=20261119.1" in html


def test_ai_email_tailoring_exposes_working_success_and_failure_feedback() -> None:
    dashboard = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    operations = (STATIC_ROOT / "operations.js").read_text(encoding="utf-8")
    planning = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")

    for source in (dashboard, operations, planning):
        assert "AI tailoring is working" in source
        assert "AI tailoring complete" in source
        assert "AI tailoring failed" in source
    assert 'aria-live="polite"' in operations
    assert 'aria-live="polite"' in planning


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
    assert "returnFocus.isConnected" in javascript
    assert 'document.querySelector(`[data-action="${CSS.escape(action)}"]`)' in javascript
    assert 'focusTarget?.closest("details")' in javascript
    assert "focusTarget?.focus()" in javascript
    assert "generateInterviewManuscript(guest.id, guest.full_name || \"Guest\", button)" in javascript
    assert "async function generateInterviewManuscript(guestId, guestName, returnFocus = null)" in javascript
    assert 'id="manuscript-settings"' in javascript
    assert '"Conversation Depth"' in javascript
    assert '"Emotional Sensitivity"' in javascript
    assert '"Technical Complexity"' in javascript
    assert '"Primary Emphasis"' in javascript
    assert '"Research Mode"' in javascript


def test_operations_ai_preparation_uses_linked_guest_data_and_accessible_dialog() -> None:
    html = (STATIC_ROOT / "operations.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "operations.js").read_text(encoding="utf-8")

    assert 'id="ai-modal" class="modal hidden" role="dialog"' in html
    assert 'aria-label="Close result dialog"' in html
    assert 'data-interview-action="ai-reminder"' not in javascript
    assert 'data-interview-action="ai-manuscript"' in javascript
    assert '`/api/guests/${interview.guest_id}/ai-interview-questions?num=10`' in javascript
    assert '`/api/guests/${interview.guest_id}/ai-interview-manuscript`' in javascript
    assert "AI-powered email generation coming soon" not in javascript
    assert "Generic interview starter questions" not in javascript
    assert "aiModalClose?.focus()" in javascript
    assert 'event.key === "Escape"' in javascript
    assert "aiModalReturnFocus?.isConnected" in javascript


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


def test_planning_episode_modal_uses_dark_readable_surface() -> None:
    styles = (STATIC_ROOT / "operations.css").read_text(encoding="utf-8")

    assert ".modal-content {" in styles
    assert "background: var(--panel-strong);" in styles
    assert "color: var(--text);" in styles
    assert ".episode-detail-grid dd {" in styles
    assert "color: var(--text);" in styles


def test_planning_learning_and_copilot_surfaces_are_dark_at_source() -> None:
    styles = (STATIC_ROOT / "operations.css").read_text(encoding="utf-8")

    assert ".operations-preview.ai-copilot-status.success" in styles
    assert "background: linear-gradient(145deg, rgba(42, 30, 34, 0.98)" in styles
    assert ".learning-policy-strip," in styles
    assert ".learning-console {" in styles
    assert "linear-gradient(155deg, var(--color-surface-raised), var(--color-surface))" in styles
    assert ".learning-metric-grid {" in styles
    assert ".learning-progress {" in styles
    assert styles.count("background: var(--panel-strong);") >= 4


def test_insight_freshness_badges_have_explicit_dark_theme_contrast() -> None:
    html = (STATIC_ROOT / "insights.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "insights.js").read_text(encoding="utf-8")

    assert "insights.css?v=20261126.4" in html
    assert "insights.js?v=20261127.4" in html
    assert "Copy browser reset" in javascript
    assert "MirrorTalkAnalyticsCollector/${profileName}" in javascript
    assert 'provider === "apple_podcasts" ? "apple_podcasts"' in javascript


def test_web_player_analytics_contract_is_copyable_and_tracks_completion_milestones() -> None:
    html = (STATIC_ROOT / "insights.html").read_text(encoding="utf-8")
    insights = (STATIC_ROOT / "insights.js").read_text(encoding="utf-8")
    tracker = (STATIC_ROOT / "web-player-analytics.js").read_text(encoding="utf-8")
    javascript = insights
    styles = (STATIC_ROOT / "insights.css").read_text(encoding="utf-8")

    assert "insights.js?v=20261127.4" in html
    assert "Copy player tracking snippet" in insights
    assert "web-player-analytics.js?v=20261127.1" in insights
    for event in ("audio_play", "audio_pause", "audio_progress_25", "audio_progress_50", "audio_progress_75", "audio_complete"):
        assert event in tracker or (event.startswith("audio_progress_") and "audio_progress_${threshold}" in tracker)
    assert 'typeof window.gtag !== "function"' in tracker
    assert 'class="trend-hit-target"' in javascript
    assert 'tabindex="0" role="button"' in javascript
    assert "attachTrendInteractions(target)" in javascript
    assert ".chart-gridline" in styles
    assert ".trend-tooltip" in styles
    assert "Connection health" in javascript
    assert "Verified · retrying check" in javascript
    assert "Temporarily unavailable" in javascript
    assert 'id="insight-alerts"' in html
    assert 'id="episode-performance"' in html
    assert 'id="measurement-coverage"' in html
    assert "Downloads and plays over time" in html
    assert "Where your audience listens and watches" in html
    assert 'data-audio-range="all" class="active"' in html
    script = (STATIC_ROOT / "insights.js").read_text(encoding="utf-8")
    for label in (
        "Downloads & plays", "Listening & watch hours", "Countries reached",
        "Platforms available", "Audience relationships", "Growth trend",
    ):
        assert f'"{label}"' in script
    assert "Why these numbers differ:" in script
    assert "measured lifetime downloads, plays or views" in script
    assert "const combined = new Map()" in script
    assert "Listeners are people who played the show during the provider's stated reporting period" in script
    assert ".freshness{" in styles
    assert "background:rgba(255,255,255,.08);color:var(--text)" in styles
    assert ".freshness.current{background:rgba(93,205,169,.14);color:#9ee5cd" in styles
    assert ".freshness.stale{background:rgba(233,189,101,.14);color:#f2c46d" in styles


def test_scheduling_intelligence_sidebar_never_requires_horizontal_scrolling() -> None:
    html = (STATIC_ROOT / "planning.html").read_text(encoding="utf-8")
    styles = (STATIC_ROOT / "operations.css").read_text(encoding="utf-8")

    assert 'operations.css?v=20261120.2' in html
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
    assert "availability.css?v=20261120.2" in html
    assert "availability-window.js?v=20261119.1" in html
    assert "availability.js?v=20261119.1" in html
    assert 'windowPosition === "after" ? "Outside booking window"' in javascript
    assert "error.message" not in javascript
    assert "Availability could not be fully loaded" in javascript
    assert "#calendar-day-dialog" in styles


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
    assert "cards.length === 0 || visible !== 0" in javascript
    assert "partners.js?v=20261016.1" in html


def test_growth_dashboard_preserves_zero_values_without_manual_import_ui() -> None:
    html = (STATIC_ROOT / "insights.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")

    assert 'id="analytics-import-form"' not in html
    assert "Import provider reports" not in html
    assert "planning-intelligence.js" not in html
    assert 'return String(value ?? "")' in javascript
    assert "escapeHtml(reach.organic ?? 0)" in javascript
    assert "escapeHtml(reach.paid ?? 0)" in javascript
    assert "escapeHtml(quality.mfs_ready ?? 0)" in javascript
    assert "escapeHtml(quality.episodes_with_evidence ?? 0)" in javascript
    assert "String(item.actual_share_pct ?? 0)" in javascript
    assert "String(quality.unclassified_released_episodes ?? 0)" in javascript


def test_authenticated_workspaces_share_search_personal_view_and_mobile_navigation() -> None:
    shell = (STATIC_ROOT / "workspace-shell.js").read_text(encoding="utf-8")
    styles = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")
    for name in ("index.html", "operations.html", "planning.html", "partners.html", "insights.html", "availability.html"):
        html = (STATIC_ROOT / name).read_text(encoding="utf-8")
        assert 'workspace-shell.js?v=20261120.2' in html
        assert 'brand-system.css?v=20261018.1' in html
        assert 'styles.css?v=20261120.2' in html
    assert 'id="workspace-command-dialog"' in shell
    assert "/api/search?q=" in shell
    assert "/api/personal-briefing?window=" in shell
    assert 'mirror-talk-recent-records' in shell
    assert 'beforeunload' in shell
    assert 'mirror-talk-details-state' in shell
    assert 'data-toggle-density' in shell
    assert 'aria-current' in shell
    assert 'id="workspace-decision-dialog"' in shell
    assert shell.count('value="cancel" formnovalidate') == 2
    assert ".mobile-workspace-nav" in styles


def test_mobile_workspace_navigation_stays_one_row_and_preserves_admin_access() -> None:
    shell = (STATIC_ROOT / "workspace-shell.js").read_text(encoding="utf-8")
    styles = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")
    settings = (STATIC_ROOT / "account-settings.html").read_text(encoding="utf-8")
    settings_js = (STATIC_ROOT / "account-settings.js").read_text(encoding="utf-8")

    mobile_nav = re.search(r'<nav class="mobile-workspace-nav".*?</nav>', shell)
    assert mobile_nav
    assert mobile_nav.group(0).count("<a ") == 4
    assert mobile_nav.group(0).count("<button ") == 1
    assert 'href="/accounts"' not in mobile_nav.group(0)
    assert "grid-template-columns: repeat(5, minmax(0, 1fr))" in styles
    assert 'id="manage-accounts-link" href="/accounts" hidden' in settings
    assert 'session.role!=="super_admin"' in settings_js


def test_mobile_action_queue_keeps_workspace_context_first_and_collapses_long_lists() -> None:
    styles = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")
    utilities = (STATIC_ROOT / "performance-utils.js").read_text(encoding="utf-8")

    assert "> #workspace-action-queue { order:" not in styles
    assert 'window.matchMedia("(max-width: 700px)").matches ? 3 : 6' in utilities
    assert "filtered.slice(0, collapsedLimit)" in utilities
    assert "filtered.length > collapsedLimit" in utilities
    assert 'responsiveQuery.addEventListener("change"' in utilities
    assert 'container.dataset.expanded = "false"' in utilities


def test_guest_actions_are_grouped_by_user_intent() -> None:
    html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    styles = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")

    for label in ("Guest record", "Preparation", "Workflow", "Decision", "Recovery and removal"):
        assert label in html
    assert "guest-action-group-danger" in html
    assert ".guest-action-group > span" in styles


def test_dynamic_guest_research_surfaces_use_dark_readable_theme() -> None:
    styles = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")

    dark_surface_rule = styles[styles.index(".guest-ai-card {") : styles.index(".guest-planning-meta {")]
    for selector in (
        ".guest-ai-card",
        ".guest-promotion-card",
        ".guest-planning-card",
    ):
        assert selector in dark_surface_rule
    assert "rgba(34, 28, 38, 0.98)" in dark_surface_rule
    assert ".guest-ai-badge.good" in styles
    assert ".guest-ai-badge.warning" in styles


def test_account_surfaces_have_labeled_fields_and_status_regions() -> None:
    accounts = (STATIC_ROOT / "accounts.html").read_text(encoding="utf-8")
    settings = (STATIC_ROOT / "account-settings.html").read_text(encoding="utf-8")
    recovery = (STATIC_ROOT / "account-recovery.html").read_text(encoding="utf-8")
    assert "Create account and invitation" in accounts
    assert 'id="form-message" class="message" aria-live="polite"' in accounts
    assert 'autocomplete="current-password"' in settings
    assert 'autocomplete="one-time-code"' in settings
    assert 'id="mfa-message" aria-live="polite"' in settings
    assert 'autocomplete="new-password"' in recovery
    assert 'id="message" aria-live="polite"' in recovery
    login = (STATIC_ROOT / "dashboard-login.html").read_text(encoding="utf-8")
    auth_styles = (STATIC_ROOT / "auth.css").read_text(encoding="utf-8")
    assert 'brand-system.css?v=20261018.1' in login
    assert 'auth.css?v=20261018.1' in login
    assert "[hidden]" in auth_styles and "display: none !important" in auth_styles
    assert 'auth.css?v=20261120.2' in settings


def test_podcast_reach_uses_automatic_collection_and_keeps_reviews_in_planning() -> None:
    html = (STATIC_ROOT / "insights.html").read_text(encoding="utf-8")
    planning_html = (STATIC_ROOT / "planning.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "planning-intelligence.js").read_text(encoding="utf-8")
    assert "Observation JSON" not in html
    assert 'id="analytics-import-history"' not in html
    assert 'id="data-sources" class="panel disclosure-panel"' in html
    assert "Podcast Reach refreshes connected hosting" in html
    assert 'id="outcome-review-queue"' in planning_html
    assert 'id="outcome-review-message" class="message" aria-live="polite"' in planning_html
    assert "planning-intelligence.js?v=20261018.1" in planning_html
    assert "Import provider reports" not in html
    assert "What content is driving reach" in html
    assert "renderImportHistory" in javascript
    assert "renderOutcomeReviews" in javascript
    assert 'setMessage(message, "Saving your assessment…", "pending")' in javascript
    assert 'setMessage(message, error.message, "error")' in javascript
    assert "Audience balance" in javascript
    assert "Blockers" in javascript


def test_learning_console_exposes_shadow_progress_and_safe_automation() -> None:
    html = (STATIC_ROOT / "planning.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")
    assert 'id="learning-shadow-cycle"' in html
    assert "planning.js?v=20261120.1" in html
    assert "operations.css?v=20261120.2" in html
    assert '"/api/recommendation-learning/shadow-cycle"' in javascript
    assert "credible target" in javascript


def test_episode_badge_respects_transcript_available_when_list_text_is_omitted() -> None:
    """Compact planning payloads must not label hydrated transcripts as missing."""
    javascript = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")

    badge_function = javascript[javascript.index("function renderEpisodeBadges"):javascript.index("function renderOutreachSummary")]
    assert "episodeHasTranscript(episode)" in badge_function
    assert "if (episode.transcript_text)" not in badge_function


def test_recommendations_default_to_chronological_release_slot_order() -> None:
    html = (STATIC_ROOT / "planning.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")
    sort_start = html.index('<select id="recommendation-sort">')
    sort_end = html.index("</select>", sort_start)
    sort_markup = html[sort_start:sort_end]

    assert sort_markup.index('value="recommended_date"') < sort_markup.index('value="score"')
    assert 'recommendationSort.value || "recommended_date"' in javascript
    assert "promotion ${automationLocked ? \"locked\" : \"enabled\"}" in javascript


def test_private_workspaces_redirect_expired_sessions_to_login() -> None:
    for filename in ("app.js", "operations.js", "planning.js"):
        javascript = (STATIC_ROOT / filename).read_text(encoding="utf-8")
        assert "function redirectToDashboardLogin()" in javascript
        assert "response.status === 401" in javascript
        assert "/dashboard-login?next=" in javascript


def test_release_heads_up_is_visible_on_scheduled_episode_cards_and_action_queue() -> None:
    javascript = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")
    assert 'requestedAction === "release_heads_up"' in javascript
    assert "/release-heads-up-template" in javascript
    assert 'data-episode-action="preview-release-heads-up"' in javascript
    assert "Review the draft, then send now or schedule it. Nothing is sent automatically." in javascript
    assert 'if (requestedAction === "release_heads_up")' in javascript
    assert "revealReleaseHeadsUpComposer(episode, preview);" in javascript
    release_branch = javascript.index('if (requestedAction === "release_heads_up")')
    editor_open = javascript.index("loadEpisodeIntoForm(fullEpisode);", release_branch)
    assert javascript.index("return;", release_branch) < editor_open
    assert 'refreshPlanningQuietly({ render: false })' in javascript
    assert "Late guest release notice" in javascript
    assert "Send Now" in javascript
    assert "Schedule Email" in javascript
    assert 'data-heads-up-action="send"' in javascript
    assert 'data-heads-up-action="approve"' not in javascript
    assert "Guest notice queued for immediate delivery." in javascript
    assert "Guest notice sent successfully." in javascript
    assert "The ideal 14-day notice window has passed" in javascript


def test_action_queue_can_reveal_every_returned_action() -> None:
    javascript = (STATIC_ROOT / "performance-utils.js").read_text(encoding="utf-8")
    assert 'container.dataset.expanded === "true"' in javascript
    assert 'data-action-expand' in javascript
    assert "Show all ${escapeUtilityHtml(filtered.length)} actions" in javascript


def test_schedule_dialog_uses_native_modal_and_restores_focus() -> None:
    html = (STATIC_ROOT / "planning.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")
    assert '<dialog id="schedule-modal"' in html
    assert "scheduleModal.showModal()" in javascript
    assert "scheduleModalReturnFocus = document.activeElement" in javascript
    assert "scheduleModalReturnFocus.focus()" in javascript
    assert 'name="guest_email" type="email"' in html


def test_mobile_workspace_identity_precedes_the_action_queue() -> None:
    styles = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")
    assert '.page-shell:has(> #workspace-action-queue) > #workspace-action-queue { order:' not in styles
    assert '.page-shell:has(> #workspace-action-queue) > .hero { order:' not in styles


def test_episode_administration_is_separated_from_guest_communication() -> None:
    javascript = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")
    assert 'class="episode-administration full-width"' in javascript
    assert "More lifecycle and administrative actions" in javascript
    assert "Delete episode" in javascript


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
    insights_html = (STATIC_ROOT / "insights.html").read_text(encoding="utf-8")
    javascript = (STATIC_ROOT / "planning-intelligence.js").read_text(encoding="utf-8")
    planning_javascript = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")
    styles = (STATIC_ROOT / "operations.css").read_text(encoding="utf-8")

    assert 'id="exception-center" class="exception-center" aria-live="polite"' in html
    assert 'id="analytics-import-form"' not in html
    assert 'id="analytics-import-form"' not in insights_html
    assert 'class="provider-export-grid"' not in insights_html
    assert 'id="data-sources" class="panel disclosure-panel"' in insights_html
    assert 'id="demographic-breakdown"' in insights_html
    assert 'id="traffic-source-breakdown"' in insights_html
    assert 'id="listening-app-breakdown"' in insights_html
    assert 'id="episode-performance"' in insights_html
    assert 'id="release-readiness"' in insights_html
    assert "Know what is growing. Decide what to do next." in insights_html
    assert "Open the audience and platform deep dive" in insights_html
    assert "Import provider reports" not in insights_html
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


def test_planning_separates_daily_decisions_from_data_administration() -> None:
    html = (STATIC_ROOT / "planning.html").read_text(encoding="utf-8")

    assert 'data-planning-tab="data_tools"' in html
    assert html.count('data-planning-panel="data_tools"') == 2
    assert "Episode data and recommendation safeguards" in html
    assert "Use the right tool for the job" in html
    assert "intermediate steps are not required" in html
    scheduling_start = html.index('data-planning-panel="scheduling_intelligence"')
    data_tools_start = html.index('data-planning-panel="data_tools"')
    assert 'id="episode-import-form"' not in html[scheduling_start:data_tools_start]


def test_paginated_workspace_counts_distinguish_matches_from_visible_cards() -> None:
    planning = (STATIC_ROOT / "planning.js").read_text(encoding="utf-8")
    operations = (STATIC_ROOT / "operations.js").read_text(encoding="utf-8")

    for javascript in (planning, operations):
        assert "visible < matched" in javascript
        assert "Displaying ${visible} right now" in javascript


def test_standalone_guest_pages_use_the_shared_brand_token_contract() -> None:
    """Booking and intake must use the same brand tokens as authenticated pages."""
    import re

    brand = (STATIC_ROOT / "brand-system.css").read_text(encoding="utf-8")
    brand_definitions = set(re.findall(r"(--[\w-]+)\s*:", brand))
    for filename, html_name in (("booking.css", "booking.html"), ("intake.css", "intake.html")):
        stylesheet = (STATIC_ROOT / filename).read_text(encoding="utf-8")
        html = (STATIC_ROOT / html_name).read_text(encoding="utf-8")
        definitions = brand_definitions | set(re.findall(r"(--[\w-]+)\s*:", stylesheet))
        uses = set(re.findall(r"var\((--[\w-]+)", stylesheet))
        assert 'brand-system.css?v=20261018.1' in html
        assert uses <= definitions, f"{filename} has undefined CSS variables: {sorted(uses - definitions)}"


def test_brand_stripe_scrolls_with_document_instead_of_covering_content() -> None:
    for filename in ("styles.css", "booking.css", "intake.css"):
        stylesheet = (STATIC_ROOT / filename).read_text(encoding="utf-8")
        body_before = stylesheet.split("body::before", 1)[1].split("}", 1)[0]
        assert "position: fixed" not in body_before
        assert "position: absolute" in body_before
