const episodeForm = document.getElementById("episode-form");
const episodeImportForm = document.getElementById("episode-import-form");
const askSyncForm = document.getElementById("ask-sync-form");
const planningExportForm = document.getElementById("planning-export-form");
const episodeSubmitButton = document.getElementById("episode-submit-button");
const episodeResetButton = document.getElementById("episode-reset-button");
const exportListName = document.getElementById("export-list-name");
const exportFields = document.getElementById("export-fields");
const episodeCategoryOptions = document.getElementById("episode-category-options");
const planningTeamMembers = document.getElementById("planning-team-members");
const episodeMessage = document.getElementById("episode-message");
const planningWorkspaceMessage = document.getElementById("planning-workspace-message");
const episodeImportMessage = document.getElementById("episode-import-message");
const askSyncMessage = document.getElementById("ask-sync-message");
const askSyncBreakdown = document.getElementById("ask-sync-breakdown");
const askSyncAmbiguous = document.getElementById("ask-sync-ambiguous");
const planningExportMessage = document.getElementById("planning-export-message");
const planningWeeklySystem = document.getElementById("planning-weekly-system");
const workspaceActionQueue = document.getElementById("workspace-action-queue");
const aiCopilotStatus = document.getElementById("planning-ai-copilot-status");
const episodeList = document.getElementById("episode-list");
const releaseCalendar = document.getElementById("release-calendar");
const releaseCalendarTitle = document.getElementById("release-calendar-title");
const calendarPreviousButton = document.getElementById("calendar-previous");
const calendarTodayButton = document.getElementById("calendar-today");
const calendarNextButton = document.getElementById("calendar-next");
const productionRail = document.getElementById("production-rail");
const productionStageClear = document.getElementById("production-stage-clear");
const recommendationList = document.getElementById("recommendation-list");
const refreshButton = document.getElementById("planning-refresh-button");
const recommendationSearchInput = document.getElementById("recommendation-search");
const recommendationCategoryFilter = document.getElementById("recommendation-category-filter");
const recommendationSort = document.getElementById("recommendation-sort");
const recommendationResultsMeta = document.getElementById("recommendation-results-meta");
const recommendationLoadMoreButton = document.getElementById("recommendation-load-more");
const rejectedRecommendationsPanel = document.getElementById("rejected-recommendations-panel");
const rejectedRecommendationsCount = document.getElementById("rejected-recommendations-count");
const rejectedRecommendationList = document.getElementById("rejected-recommendation-list");
const recommendationPresetButtons = Array.from(document.querySelectorAll("[data-recommendation-preset]"));
const episodeSearchInput = document.getElementById("episode-search");
const episodeCategoryFilter = document.getElementById("episode-category-filter");
const episodeYearFilter = document.getElementById("episode-year-filter");
const episodeReleaseFilter = document.getElementById("episode-release-filter");
const episodeProductionFilter = document.getElementById("episode-production-filter");
const episodeTranscriptFilter = document.getElementById("episode-transcript-filter");
const episodeSort = document.getElementById("episode-sort");
const episodeResultsMeta = document.getElementById("episode-results-meta");
window.PerformanceUtils?.installSavedViews(document.getElementById("planning-saved-views"), "planning");
const episodeLoadMoreButton = document.getElementById("episode-load-more");
const episodePresetButtons = Array.from(document.querySelectorAll("[data-episode-preset]"));
const planningTabButtons = Array.from(document.querySelectorAll("[data-planning-tab]"));
const planningTabPanels = Array.from(document.querySelectorAll("[data-planning-panel]"));
const scheduleModal = document.getElementById("schedule-modal");
const scheduleForm = document.getElementById("schedule-form");
const scheduleModalMessage = document.querySelector("[data-schedule-modal-message]");
const episodeDetailsModal = document.getElementById("episode-details-modal");
const episodeDetailsTitle = document.getElementById("episode-details-title");
const episodeDetailsBody = document.getElementById("episode-details-body");
const episodeDetailsClose = document.getElementById("episode-details-close");
const episodeDetailsDismiss = document.getElementById("episode-details-dismiss");
const episodeDetailsEdit = document.getElementById("episode-details-edit");
const episodeEditorModal = document.getElementById("episode-editor-modal");
const episodeEditorSection = document.getElementById("episode-editor-section");
const episodeEditorCreate = document.getElementById("episode-editor-create");
const episodeEditorClose = document.getElementById("episode-editor-close");
const episodeEditorTitle = document.getElementById("episode-editor-title");
const episodeConflictPanel = document.getElementById("episode-conflict-panel");
const episodeConflictSummary = document.getElementById("episode-conflict-summary");
const episodeConflictFields = document.getElementById("episode-conflict-fields");
const episodeConflictUseLatest = document.getElementById("episode-conflict-use-latest");
const episodeConflictKeepDraft = document.getElementById("episode-conflict-keep-draft");
const IS_FILE_PROTOCOL = window.location.protocol === "file:";

let latestPlanningPayload = {
  stats: {},
  episodes: [],
  recommendations: [],
  rejected_recommendations: [],
  available_categories: [],
};
let activeRecommendationPreset = "all";
let activeEpisodePreset = "all";
let activeProductionStage = "";
let activeEpisodeEditorId = null;
let activeEpisodeFeedback = { id: null, text: "", tone: "" };
let activeEpisodeBaseline = null;
let activeEpisodeConflict = null;
let activeEpisodeActionFeedback = { id: null, text: "", tone: "" };
let visibleRecommendationCount = 6;
let visibleEpisodeCount = 10;
let pendingEpisodeIdFromUrl = null;
let pendingPlanningSuccessMessage = "";
let activePlanningTab = "release_planning";
let aiCopilotHydrationInFlight = false;
let planningRefreshInFlight = false;
let calendarCursor = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
let selectedCalendarEpisodeId = null;
let calendarReturnFocus = null;
let episodeEditorReturnFocus = null;
let pendingAskSyncRequest = null;
const PLANNING_PAYLOAD_CACHE_KEY = "mirror-talk-planning-payload-v20260605-intelligence-nostore";
const LEGACY_PLANNING_PAYLOAD_CACHE_KEYS = [
  "mirror-talk-planning-payload",
  "mirror-talk-planning-payload-v20260605-intelligence",
];

const RECOMMENDATION_PAGE_SIZE = 6;
const EPISODE_PAGE_SIZE = 10;
const PRODUCTION_RAIL_STAGES = [
  ["recorded", "Recorded"],
  ["editing", "Editing"],
  ["assets_needed", "Assets needed"],
  ["ready", "Ready"],
  ["scheduled", "Scheduled"],
];
const OUTREACH_STEPS = [
  ["monday_preparation", "Monday · Preparation and positioning", "Titles, thumbnails, clips, blog, and email"],
  ["tuesday_launch", "Tuesday 17:00 · Podcast and YouTube launch", "Publish the full episode and anchor the cycle"],
  ["tuesday_distribution", "Tuesday evening · Clip, email, and social push", "Use the first-night momentum window"],
  ["wednesday_momentum", "Wednesday · Momentum and engagement", "Second clip, community replies, and carousel"],
  ["thursday_blog", "Thursday 11:00 · Website blog post", "Publish the SEO-focused long-form version"],
  ["thursday_amplification", "Thursday afternoon · Blog promotion", "Third clip plus blog amplification"],
  ["friday_newsletter", "Friday 15:00 · Substack newsletter", "Personal and reflective newsletter touchpoint"],
  ["friday_reflection", "Friday afternoon · Reflection posts", "Relationship-building social posts and replies"],
  ["weekend_review", "Weekend · Analytics and planning", "Review performance and prepare the next cycle"],
];

const EXPORT_FIELD_CONFIG = {
  guests: [
    ["full_name", "Full Name"],
    ["email", "Email"],
    ["website", "Website"],
    ["profession", "Profession"],
    ["social_media_handles", "Social Handles"],
    ["background", "Background"],
    ["passionate_topics", "Passionate Topics"],
    ["email_status", "Decision"],
    ["original_file_name", "Source"],
    ["date_added", "Date Added"],
  ],
  interviews: [
    ["guest_name", "Guest Name"],
    ["guest_email", "Guest Email"],
    ["title", "Title"],
    ["scheduled_for", "Scheduled For"],
    ["timezone", "Timezone"],
    ["join_url", "Join URL"],
    ["confirmation_status", "Confirmation"],
    ["reminder_status", "Reminder Status"],
    ["calendar_event_id", "Calendar Event ID"],
    ["calendar_source", "Calendar Source"],
  ],
  episodes: [
    ["guest_name", "Guest Name"],
    ["guest_email", "Guest Email"],
    ["website", "Website"],
    ["episode_title", "Working Title"],
    ["published_title", "Published Title"],
    ["topic", "Topic"],
    ["category", "Category"],
    ["interview_date", "Interview Date"],
    ["release_date", "Release Date"],
    ["release_status", "Release Status"],
    ["production_status", "Production Status"],
    ["promotion_status", "Promotion Status"],
    ["priority_score", "Priority Score"],
    ["legacy_episode_number", "Episode Number"],
    ["riverside_status", "Riverside Status"],
    ["show_notes_url", "Show Notes URL"],
    ["release_files_url", "Files URL"],
    ["transcript_text", "Transcript"],
    ["transcript_source_id", "Transcript Source ID"],
    ["transcript_synced_at", "Transcript Synced At"],
    ["outreach_plan", "Outreach Plan"],
    ["source_file_name", "Source File"],
    ["recommendation_reason", "Recommendation Reason"],
  ],
  recommendations: [
    ["guest_name", "Guest Name"],
    ["guest_email", "Guest Email"],
    ["episode_title", "Episode Title"],
    ["topic", "Topic"],
    ["category", "Category"],
    ["interview_date", "Interview Date"],
    ["production_status", "Production Status"],
    ["promotion_status", "Promotion Status"],
    ["priority_score", "Priority Score"],
    ["recommended_release_date", "Recommended Release Date"],
    ["recommendation_reason", "Recommendation Reason"],
  ],
};

function readCachedPayload(cacheKey) {
  return null;
}

function storeCachedPayload(cacheKey, payload) {
  // Episode records can contain transcripts and private contact data; retain
  // them in memory only for the life of this page.
}

function dashboardCsrfToken() {
  const item = document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith("dashboard_csrf="));
  return item ? decodeURIComponent(item.split("=", 2)[1] || "") : "";
}

function dashboardRequestHeaders(options = {}, isReadRequest = false, includeJson = true) {
  return {
    ...(includeJson ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {}),
    ...(!isReadRequest ? { "X-CSRF-Token": dashboardCsrfToken() } : {}),
  };
}

const stats = {
  total: document.getElementById("plan-episodes-total"),
  released: document.getElementById("plan-episodes-released"),
  scheduled: document.getElementById("plan-episodes-scheduled"),
  unreleased: document.getElementById("plan-episodes-unreleased"),
  promoReady: document.getElementById("plan-episodes-promo-ready"),
  needsAssets: document.getElementById("plan-episodes-need-assets"),
};

function buildScopedLink(path, value) {
  return `${path}?q=${encodeURIComponent(value || "")}`;
}

function setPlanningTab(tabName) {
  activePlanningTab = tabName;
  planningTabButtons.forEach((button) => {
    const isActive = button.dataset.planningTab === tabName;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
    button.setAttribute("tabindex", isActive ? "0" : "-1");
  });
  planningTabPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.planningPanel === tabName);
  });
}

function replaceEpisodeInPayload(savedEpisode) {
  if (!savedEpisode?.id) {
    return;
  }
  const replaceById = (item) => (String(item.id || "") === String(savedEpisode.id) ? { ...item, ...savedEpisode } : item);
  const episodes = latestPlanningPayload.episodes || [];
  const recommendations = latestPlanningPayload.recommendations || [];
  latestPlanningPayload.episodes = episodes.some((item) => String(item.id || "") === String(savedEpisode.id))
    ? episodes.map(replaceById)
    : [{ ...savedEpisode }, ...episodes];
  latestPlanningPayload.recommendations = recommendations.map(replaceById);
}

function cleanEpisodePayloadForSave(payload) {
  const cleaned = { ...payload };
  cleaned.working_title = String(cleaned.episode_title || "").trim();
  if (cleaned.transcript_omitted && !cleaned.transcript_text) {
    delete cleaned.transcript_text;
  }
  delete cleaned.transcript_omitted;
  delete cleaned.transcript_available;
  return cleaned;
}

function validateEpisodePayloadForSave(payload) {
  if (!String(payload.guest_name || "").trim()) {
    throw new Error("Please add the guest name before saving this episode.");
  }
  if (!String(payload.episode_title || "").trim()) {
    throw new Error("Please add the episode title before saving this episode.");
  }
}

function updatePlanningStats(payload) {
  if (!payload?.stats) return;
  stats.total.textContent = payload.stats.episodes_total ?? 0;
  stats.released.textContent = payload.stats.episodes_released ?? 0;
  stats.scheduled.textContent = payload.stats.episodes_scheduled ?? 0;
  stats.unreleased.textContent = payload.stats.episodes_unreleased ?? 0;
  stats.promoReady.textContent = payload.stats.episodes_promo_ready ?? 0;
  stats.needsAssets.textContent = payload.stats.episodes_need_assets ?? 0;
}

function clearLegacyPlanningPayloadCaches() {
  LEGACY_PLANNING_PAYLOAD_CACHE_KEYS.forEach((key) => {
    try {
      window.localStorage.removeItem(key);
    } catch (error) {
      // Local storage can be unavailable in private or restricted browser contexts.
    }
  });
}

function buildPlanningApiUrl(path) {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}_=${Date.now()}`;
}

function refreshPlanningQuietly() {
  if (planningRefreshInFlight) return;
  planningRefreshInFlight = true;
  window.setTimeout(async () => {
    try {
      const payload = await fetchJSON(buildPlanningApiUrl("/api/planning?compact=true&refresh=true"));
      latestPlanningPayload = payload;
      updatePlanningStats(payload);
      storeCachedPayload(PLANNING_PAYLOAD_CACHE_KEY, payload);
      const mainFormEditing = Boolean(episodeForm?.elements?.id?.value);
      if (!activeEpisodeEditorId && !mainFormEditing) {
        renderPlanning();
      }
    } catch (error) {
      console.warn("Quiet planning refresh failed:", error);
    } finally {
      planningRefreshInFlight = false;
    }
  }, 20);
}

async function fetchJSON(url, options = {}) {
  const isReadRequest = !options.method || String(options.method).toUpperCase() === "GET";
  let lastError = null;
  // Increased timeout for large datasets (528 episodes) - 60s for reads, 45s for writes
  const requestTimeoutMs = isReadRequest ? 60000 : 45000;

  for (let attempt = 0; attempt < (isReadRequest ? 2 : 1); attempt += 1) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), requestTimeoutMs);
    try {
      const response = await fetch(url, {
        credentials: "same-origin",
        signal: controller.signal,
        ...options,
        headers: dashboardRequestHeaders(options, isReadRequest),
      });
      const rawText = await response.text();
      let data = {};
      if (rawText) {
        try {
          data = JSON.parse(rawText);
        } catch (error) {
          data = { error: rawText.trim() };
        }
      }
      if (!response.ok) {
        const requestError = new Error(data.error || "Request failed");
        requestError.status = response.status;
        requestError.payload = data;
        throw requestError;
      }
      window.clearTimeout(timeoutId);
      return data;
    } catch (error) {
      window.clearTimeout(timeoutId);
      if (error.name === "AbortError") {
        lastError = new Error("This request took too long. Please refresh and try again.");
      } else {
        lastError = error;
      }
      if (!isReadRequest || attempt > 0) {
        break;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 350));
    }
  }

  throw lastError || new Error("Request failed");
}

async function postForm(url, formData) {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: dashboardRequestHeaders({}, false, false),
    body: formData,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

async function downloadExport(payload) {
  const response = await fetch("/api/exports", {
    method: "POST",
    credentials: "same-origin",
    headers: dashboardRequestHeaders({}, false),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "Export failed");
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename=\"([^\"]+)\"/);
  const filename = match ? match[1] : "mirror-talk-export";
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(objectUrl);
}

function setMessage(node, text, tone = "") {
  if (!node) return;
  node.textContent = text;
  node.className = `message ${tone}`.trim();
  if (node === episodeMessage && planningWorkspaceMessage) {
    planningWorkspaceMessage.textContent = text;
    planningWorkspaceMessage.className = `message ${tone}`.trim();
  }
}

function enforceHostedMode() {
  if (!IS_FILE_PROTOCOL) {
    return false;
  }
  const warning = "This page is opened as a local file, so interactive planning actions are unavailable. Please use the live app URL (for example: https://.../planning).";
  setMessage(episodeMessage, warning, "error");
  setMessage(planningExportMessage, warning, "error");
  document.querySelectorAll("button, input, select, textarea").forEach((element) => {
    element.disabled = true;
  });
  return true;
}

function confirmCriticalAction(message) {
  return window.confirm(message);
}

function promptExactMatch(label, subject) {
  const typedValue = window.prompt(`Type "${label}" to ${subject}.`);
  if (typedValue === null) {
    return null;
  }
  return typedValue.trim() === label ? typedValue.trim() : false;
}

function normalizeText(value) {
  return String(value || "").trim().toLowerCase();
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderAuditTimeline(events) {
  if (!events.length) return "<p>No activity has been recorded yet.</p>";
  return `<ol class="activity-timeline">${events.map((event) => `
    <li><strong>${escapeHtml(String(event.event_type || "updated").replaceAll("_", " "))}</strong>
    <span>${escapeHtml(event.created_at || "")}</span>
    <p>${escapeHtml(event.actor || "system")} via ${escapeHtml(event.source || "application")}${event.reason ? ` — ${escapeHtml(event.reason)}` : ""}</p></li>
  `).join("")}</ol>`;
}

function renderLinkedValue(value, fallback = "Not set") {
  const text = String(value || "").trim();
  if (!text) {
    return escapeHtml(fallback);
  }
  if (/^https?:\/\//i.test(text)) {
    return `<a class="inline-link" href="${escapeHtml(text)}" target="_blank" rel="noopener">${escapeHtml(text)}</a>`;
  }
  if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text)) {
    return `<a class="inline-link" href="mailto:${escapeHtml(text)}">${escapeHtml(text)}</a>`;
  }
  return escapeHtml(text);
}

function parseDate(value) {
  if (!value) return null;
  const date = new Date(String(value).replace(" ", "T"));
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDateTime(value) {
  if (!value) return "Not set";
  const rawValue = String(value).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(rawValue)) {
    const parts = rawValue.split("-").map((part) => Number(part));
    const date = new Date(parts[0], parts[1] - 1, parts[2]);
    return date.toLocaleDateString("en-GB", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }
  const date = parseDate(value);
  if (!date) return value;
  return date.toLocaleString("en-GB", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDateForDateInput(value) {
  if (!value) return "";
  return String(value).slice(0, 10);
}

function formatDateForDateTimeInput(value) {
  if (!value) return "";
  const normalized = String(value).replace(" ", "T");
  return normalized.slice(0, 16);
}

function transcriptExpectedSoon(episode) {
  const releaseStatus = normalizeText(episode.release_status);
  if (releaseStatus === "released") {
    return true;
  }
  if (releaseStatus !== "scheduled") {
    return false;
  }
  const releaseDate = parseDate(episode.release_date);
  if (!releaseDate) {
    return false;
  }
  const millisecondsUntilRelease = releaseDate.getTime() - Date.now();
  const daysUntilRelease = millisecondsUntilRelease / (1000 * 60 * 60 * 24);
  return daysUntilRelease <= 14;
}

function transcriptStatusLabel(episode) {
  if (episode.transcript_text || episode.transcript_available) {
    return "Available";
  }
  if (transcriptExpectedSoon(episode)) {
    return "Missing";
  }
  return "Not expected yet";
}

function episodeHasTranscript(episode) {
  return Boolean(episode.transcript_text || episode.transcript_available);
}

function getEpisodeYear(episode) {
  const releaseYear = parseDate(episode.release_date);
  if (releaseYear) return String(releaseYear.getFullYear());
  const interviewYear = parseDate(episode.interview_date);
  return interviewYear ? String(interviewYear.getFullYear()) : "";
}

function updateResultsMeta(node, shown, total, emptyMessage, filteredMessage) {
  if (!total) {
    node.textContent = emptyMessage;
    return;
  }
  if (shown === total) {
    node.textContent = `Showing all ${total} item${total === 1 ? "" : "s"}.`;
    return;
  }
  node.textContent = `Showing ${shown} of ${total} item${total === 1 ? "" : "s"} after filtering. ${filteredMessage}`;
}

function updatePresetButtons(buttons, activeValue, dataName) {
  buttons.forEach((button) => {
    button.classList.toggle("active", button.dataset[dataName] === activeValue);
  });
}

async function hydrateEpisodeForEditing(episode) {
  if (!episode?.transcript_omitted) {
    return episode;
  }
  const fullEpisode = await fetchJSON(`/api/episodes/${episode.id}`);
  replaceEpisodeInPayload(fullEpisode);
  return fullEpisode;
}

async function focusEpisodeEditor(episode, successMessage = "") {
  setPlanningTab("release_planning");
  const fullEpisode = await hydrateEpisodeForEditing(episode);
  loadEpisodeIntoForm(fullEpisode);
  if (successMessage) {
    setMessage(episodeMessage, successMessage, "success");
  }
}

function createFieldMarkup(label, inputMarkup, fullWidth = false) {
  return `
    <label class="${fullWidth ? "full-width" : ""}">
      <span>${label}</span>
      ${inputMarkup}
    </label>
  `;
}

function actionFeedbackMarkup(feedback) {
  if (!feedback?.text) {
    return "";
  }
  return `<p class="composer-feedback ${feedback.tone || ""}">${feedback.text}</p>`;
}

function renderSkeletonCards(container, count = 3, withRecommendationTone = false) {
  if (!container) return;
  const cardClass = withRecommendationTone ? "operations-card recommendation-card skeleton-card" : "operations-card skeleton-card";
  container.innerHTML = Array.from({ length: count }).map(() => `
    <article class="${cardClass}" aria-hidden="true">
      <div class="skeleton-line medium"></div>
      <div class="skeleton-line short"></div>
      <div class="skeleton-line long"></div>
      <div class="skeleton-line long"></div>
    </article>
  `).join("");
}

function deriveRecommendationSignals(episode) {
  const text = normalizeText(episode.recommendation_reason);
  const signals = [];
  if (text.includes("needs promo assets") || text.includes("promotion readiness is still unclear")) {
    signals.push({ label: "Promo Risk", tone: "warning" });
  }
  if (text.includes("same guest appeared very recently") || text.includes("same guest has already been featured")) {
    signals.push({ label: "Guest Recency", tone: "warning" });
  }
  if (text.includes("already warm in the recent release mix") || text.includes("dominates")) {
    signals.push({ label: "Category Fatigue", tone: "warning" });
  }
  if (episode.seasonal_fit?.reason || text.includes("seasonal focus")) {
    signals.push({ label: "Seasonal Fit", tone: "good" });
  }
  if (text.includes("ready to publish") || text.includes("promotion assets look ready")) {
    signals.push({ label: "Release Ready", tone: "good" });
  }
  return signals;
}

function renderSeasonalFit(seasonalFit) {
  if (!seasonalFit?.reason) {
    return "";
  }
  const matchedKeywords = (seasonalFit.matched_keywords || []).filter(Boolean);
  return `
    <div class="operations-preview">
      <strong class="insight-label">Seasonal fit</strong>
      <p>${escapeHtml(seasonalFit.reason)}</p>
      <p><strong>Target month:</strong> ${escapeHtml(seasonalFit.month || "Unknown")}</p>
      ${matchedKeywords.length ? `<p><strong>Proof from this episode:</strong> matched ${matchedKeywords.map((keyword) => `<code>${escapeHtml(keyword)}</code>`).join(", ")}</p>` : ""}
    </div>
  `;
}

function renderPromoReadiness(readiness) {
  if (!readiness) {
    return "";
  }
  const strengths = (readiness.strengths || []).slice(0, 2).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const blockers = (readiness.blockers || []).slice(0, 2).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  return `
    <div class="operations-preview">
      <p><strong>Promotion Readiness:</strong> ${readiness.score}/100 · ${readiness.label}</p>
      ${strengths ? `<div class="insight-stack"><strong class="insight-label">Ready signals</strong><ul>${strengths}</ul></div>` : ""}
      ${blockers ? `<div class="insight-stack caution"><strong class="insight-label">Still blocking</strong><ul>${blockers}</ul></div>` : ""}
    </div>
  `;
}

function renderGuestResearchCopilot(research) {
  if (!research?.summary && !(research?.likely_topics || []).length) {
    return "";
  }
  const isLowSignalSource = (source) => {
    const values = [source?.title, source?.description, source?.heading]
      .map((value) => normalizeText(value))
      .filter(Boolean);
    if (!values.length) {
      return false;
    }
    const genericLabels = new Set(["facebook", "instagram"]);
    return values.every((value) => genericLabels.has(value));
  };
  const topics = (research.likely_topics || []).slice(0, 4);
  const timelySignals = (research.timely_signals || []).slice(0, 3);
  const sources = (research.sources || []).filter((source) => !isLowSignalSource(source)).slice(0, 3);
  const mode = normalizeText(research.research_mode) || "manual";
  const freshness = research.freshness || {};
  return `
    <div class="operations-preview">
      <strong class="insight-label">Guest copilot context</strong>
      <p><strong>Research source:</strong> ${escapeHtml(mode === "auto" ? "Auto-researched during planning" : "Manually researched")}
      ${freshness.label ? ` · <span class="inline-muted">${escapeHtml(freshness.label)}</span>` : ""}</p>
      ${research.summary ? `<p>${escapeHtml(research.summary)}</p>` : ""}
      ${topics.length ? `<p><strong>Likely themes:</strong> ${topics.map((item) => `<code>${escapeHtml(item)}</code>`).join(", ")}</p>` : ""}
      ${timelySignals.length ? `<div class="insight-stack"><strong class="insight-label">Why this guest may be timely</strong><ul>${timelySignals.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
      ${sources.length ? `<p><strong>Sources checked:</strong> ${sources.map((source) => {
        const label = source.title || source.host || source.url || "Public source";
        return source.url
          ? `<a class="inline-link" href="${escapeHtml(source.url)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>`
          : escapeHtml(label);
      }).join(", ")}</p>` : ""}
    </div>
  `;
}

function renderAiCopilotStatus(statusPayload) {
  if (!aiCopilotStatus) {
    return;
  }
  const status = statusPayload?.status || "unknown";
  const tone = status === "active" || status === "configured" ? "success" : status === "fallback" ? "warning" : "";
  const monthContext = statusPayload?.current_month_context;
  const observances = (monthContext?.observances || []).slice(0, 3);
  const christianMoments = (monthContext?.christian_moments || []).slice(0, 2);
  const liveHeadlines = (monthContext?.live_headlines || []).slice(0, 3);
  const liveSource = String(monthContext?.live_signal_source || "").trim();
  const liveUpdatedAt = monthContext?.live_signals_updated_at ? formatDateTime(monthContext.live_signals_updated_at) : "";
  const diagnostics = statusPayload?.diagnostics || {};
  const filteredOut = Number(diagnostics.filtered_out_candidates || 0);
  const trusted = Number(diagnostics.trusted_recommendations || diagnostics.candidate_count || 0);
  const humanSuppressed = Number(diagnostics.human_suppressed_candidates || 0);
  aiCopilotStatus.className = `operations-preview ai-copilot-status ${tone}`.trim();
  aiCopilotStatus.innerHTML = `
    <strong class="insight-label">AI scheduling copilot</strong>
    <p><strong>Status:</strong> ${escapeHtml(status.replaceAll("_", " "))}</p>
    ${statusPayload?.message ? `<p>${escapeHtml(statusPayload.message)}</p>` : ""}
    ${statusPayload?.model ? `<p><strong>Model:</strong> ${escapeHtml(statusPayload.model)}</p>` : ""}
    ${monthContext?.month_label ? `<p><strong>Current month lens:</strong> ${escapeHtml(monthContext.month_label)} · ${escapeHtml(monthContext.theme || "")}</p>` : ""}
    ${observances.length ? `<p><strong>Editorial observances:</strong> ${observances.map((item) => `<code>${escapeHtml(item)}</code>`).join(", ")}</p>` : ""}
    ${filteredOut ? `<p><strong>Recommendation safeguards:</strong> ${escapeHtml(String(trusted))} trusted recommendation${trusted === 1 ? "" : "s"} shown · ${escapeHtml(String(filteredOut))} stale or mismatched candidate${filteredOut === 1 ? "" : "s"} filtered out.</p>` : ""}
    ${humanSuppressed ? `<p><strong>Editorial feedback:</strong> ${escapeHtml(String(humanSuppressed))} rejected candidate${humanSuppressed === 1 ? " is" : "s are"} suppressed from ranking, research, and AI review.</p>` : ""}
    ${liveHeadlines.length ? `<div class="insight-stack"><strong class="insight-label">Live web signals${liveSource ? ` · ${escapeHtml(liveSource)}` : ""}</strong><ul>${liveHeadlines.map((item) => `<li>${escapeHtml(item.title || item)}</li>`).join("")}</ul>${liveUpdatedAt ? `<p class="inline-muted">Updated ${escapeHtml(liveUpdatedAt)}</p>` : ""}</div>` : ""}
    ${christianMoments.length ? `<p><strong>Faith calendar:</strong> ${christianMoments.map((item) => `<code>${escapeHtml(item)}</code>`).join(", ")}</p>` : ""}
  `;
}

function renderAiSchedulingCopilot(aiCopilot) {
  if (!aiCopilot?.summary && !(aiCopilot?.source_evidence || []).length) {
    return "";
  }
  const whyNow = (aiCopilot.why_now || []).slice(0, 3);
  const watchouts = (aiCopilot.watchouts || []).slice(0, 3);
  const sourceEvidence = (aiCopilot.source_evidence || []).slice(0, 4);
  const guidanceMode = normalizeText(aiCopilot.guidance_mode) || "model";
  const guidanceLabel = guidanceMode === "grounded_fallback" ? "Grounded fallback guidance" : "Direct model analysis";
  return `
    <div class="operations-preview">
      <strong class="insight-label">AI scheduling copilot</strong>
      <div class="signal-list">
        <span class="signal-chip ${guidanceMode === "grounded_fallback" ? "warning" : "good"}">${escapeHtml(guidanceLabel)}</span>
      </div>
      ${aiCopilot.summary ? `<p>${escapeHtml(aiCopilot.summary)}</p>` : ""}
      <p><strong>Alignment score:</strong> ${escapeHtml(aiCopilot.alignment_score || 0)}/100${aiCopilot.model ? ` · ${escapeHtml(aiCopilot.model)}` : ""}</p>
      ${aiCopilot.monthly_theme ? `<p><strong>Monthly theme angle:</strong> ${escapeHtml(aiCopilot.monthly_theme)}</p>` : ""}
      ${sourceEvidence.length ? `<div class="insight-stack"><strong class="insight-label">Evidence used</strong><ul>${sourceEvidence.map((item) => `<li><strong>${escapeHtml(item.source)}:</strong> ${escapeHtml(item.detail)}</li>`).join("")}</ul></div>` : ""}
      ${whyNow.length ? `<div class="insight-stack"><strong class="insight-label">AI why now</strong><ul>${whyNow.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
      ${watchouts.length ? `<div class="insight-stack caution"><strong class="insight-label">AI watchouts</strong><ul>${watchouts.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
    </div>
  `;
}

function getRecommendationMonthlyAngle(episode) {
  const storedTheme = String(episode.ai_monthly_angle_theme || "").trim();
  if (storedTheme) {
    return storedTheme;
  }
  const aiTheme = String(episode.ai_copilot?.monthly_theme || "").trim();
  if (aiTheme) {
    return aiTheme;
  }
  const seasonalMonth = String(episode.seasonal_fit?.month || "").trim();
  const seasonalReason = String(episode.seasonal_fit?.reason || "").trim();
  if (seasonalMonth && seasonalReason) {
    return `${seasonalMonth}: ${seasonalReason}`;
  }
  if (seasonalReason) {
    return seasonalReason;
  }
  const monthContext = latestPlanningPayload.ai_copilot_status?.current_month_context || {};
  const monthLabel = String(monthContext.month_label || "").trim();
  const monthTheme = String(monthContext.theme || "").trim();
  if (monthLabel && monthTheme) {
    return `${monthLabel}: ${monthTheme}`;
  }
  return monthTheme || monthLabel || "General monthly release fit";
}

function renderMonthlyAngleDecision(episode, options = {}) {
  const state = normalizeText(episode.ai_monthly_angle_state);
  const hasSavedOrAiTheme = Boolean(String(episode.ai_monthly_angle_theme || episode.ai_copilot?.monthly_theme || "").trim());
  if (!state && !options.always && !hasSavedOrAiTheme) {
    return "";
  }
  const theme = getRecommendationMonthlyAngle(episode);
  const label = state === "pinned" ? "Pinned" : state === "rejected" ? "Rejected" : "Unreviewed";
  const tone = state === "pinned" ? "good" : state === "rejected" ? "warning" : "";
  const detail = state || options.always
    ? `<p><strong>Theme:</strong> ${escapeHtml(theme)}</p>`
    : "";
  return `
    <div class="operations-preview">
      <strong class="insight-label">Monthly angle review</strong>
      <div class="signal-list">
        <span class="signal-chip ${tone}">${escapeHtml(label)}</span>
      </div>
      ${detail}
    </div>
  `;
}

function renderCopyAssist(copyAssist) {
  if (!copyAssist) {
    return "";
  }
  return `
    <div class="operations-preview">
      <strong class="insight-label">Promo Copy Assist</strong>
      <p>${escapeHtml(copyAssist.summary || "")}</p>
      <p><strong>Social:</strong> ${escapeHtml(copyAssist.social_caption || "")}</p>
      <p><strong>Newsletter:</strong> ${escapeHtml(copyAssist.newsletter_blurb || "")}</p>
      ${copyAssist.show_notes_intro ? `<p><strong>Show notes intro:</strong> ${escapeHtml(copyAssist.show_notes_intro)}</p>` : ""}
      ${copyAssist.quote_pull ? `<p><strong>Quote pull:</strong> ${escapeHtml(copyAssist.quote_pull)}</p>` : ""}
    </div>
  `;
}

function normalizeOutreachPlan(value) {
  const emptyPlan = Object.fromEntries(OUTREACH_STEPS.map(([key]) => [key, false]));
  if (!value) {
    return emptyPlan;
  }
  let parsed = value;
  if (typeof value === "string") {
    try {
      parsed = JSON.parse(value);
    } catch (_error) {
      parsed = {};
    }
  }
  if (!parsed || typeof parsed !== "object") {
    return emptyPlan;
  }
  return Object.fromEntries(
    OUTREACH_STEPS.map(([key]) => [key, Boolean(parsed[key])]),
  );
}

function collectOutreachPlanFromForm() {
  const checklist = document.getElementById("outreach-checklist");
  if (!checklist) {
    return normalizeOutreachPlan(episodeForm?.elements?.outreach_plan?.value);
  }
  const plan = {};
  checklist.querySelectorAll("input[data-outreach-key]").forEach((input) => {
    plan[input.dataset.outreachKey] = Boolean(input.checked);
  });
  return plan;
}

function parseLegacyEpisodeNumber(value) {
  const text = String(value || "").trim();
  const matches = [...text.matchAll(/\d+/g)];
  if (!matches.length) {
    return null;
  }
  return Number.parseInt(matches[matches.length - 1][0], 10);
}

function formatEpisodeNumberLabel(value, fallbackNumber) {
  const text = String(value || "").trim();
  if (text) {
    return /^\d+$/.test(text) ? `#${text}` : text;
  }
  return fallbackNumber ? `#${fallbackNumber}` : "#TBD";
}

function computeNextLegacyEpisodeNumber(episodes, currentEpisodeId = "") {
  let maxNumber = 0;
  (episodes || []).forEach((episode) => {
    if (currentEpisodeId && String(episode.id || "") === String(currentEpisodeId)) {
      return;
    }
    const parsed = parseLegacyEpisodeNumber(episode.legacy_episode_number);
    if (parsed && parsed > maxNumber) {
      maxNumber = parsed;
    }
  });
  return maxNumber > 0 ? String(maxNumber + 1) : "1";
}

function compareEpisodeSequence(left, right, preferredDateField = "release_date") {
  const leftPrimary = parseDate(left?.[preferredDateField]);
  const rightPrimary = parseDate(right?.[preferredDateField]);
  if (leftPrimary && rightPrimary) {
    return leftPrimary - rightPrimary;
  }
  if (leftPrimary && !rightPrimary) {
    return -1;
  }
  if (!leftPrimary && rightPrimary) {
    return 1;
  }

  const leftFallback = parseDate(left?.release_date) || parseDate(left?.recommended_release_date) || parseDate(left?.interview_date);
  const rightFallback = parseDate(right?.release_date) || parseDate(right?.recommended_release_date) || parseDate(right?.interview_date);
  if (leftFallback && rightFallback) {
    return leftFallback - rightFallback;
  }
  if (leftFallback && !rightFallback) {
    return -1;
  }
  if (!leftFallback && rightFallback) {
    return 1;
  }

  return Number(left?.id || 0) - Number(right?.id || 0);
}

function buildEpisodeNumberMap(episodes, recommendations) {
  const episodeNumberMap = new Map();
  const byId = new Map();
  const register = (episode, { mergeWithExisting = false } = {}) => {
    if (!episode?.id) {
      return;
    }
    const key = String(episode.id);
    if (!byId.has(key)) {
      byId.set(key, episode);
      return;
    }
    if (!mergeWithExisting) {
      return;
    }

    const existing = byId.get(key) || {};
    // Preserve canonical episode fields, only fill gaps from recommendation rows.
    byId.set(key, {
      ...episode,
      ...existing,
      release_status: existing.release_status || episode.release_status,
    });
  };

  (episodes || []).forEach((episode) => register(episode));
  (recommendations || []).forEach((episode) => register(episode, { mergeWithExisting: true }));

  const allEpisodes = Array.from(byId.values());
  const released = allEpisodes
    .filter((episode) => normalizeText(episode.release_status) === "released")
    .sort((left, right) => compareEpisodeSequence(left, right, "release_date"));

  let nextNumber = 0;
  released.forEach((episode, index) => {
    const parsedNumber = parseLegacyEpisodeNumber(episode.legacy_episode_number);
    const number = parsedNumber || nextNumber + 1 || index + 1;
    nextNumber = number;
    episodeNumberMap.set(String(episode.id), {
      number,
      label: `Episode ${formatEpisodeNumberLabel(episode.legacy_episode_number, number)} (Actual)`,
    });
  });

  const futureEpisodes = allEpisodes
    .filter((episode) => normalizeText(episode.release_status) !== "released")
    .sort((left, right) => {
      const leftProjectedDate = parseDate(left?.release_date)
        || parseDate(left?.recommended_release_date)
        || parseDate(left?.interview_date);
      const rightProjectedDate = parseDate(right?.release_date)
        || parseDate(right?.recommended_release_date)
        || parseDate(right?.interview_date);

      if (leftProjectedDate && rightProjectedDate) {
        if (leftProjectedDate.getTime() !== rightProjectedDate.getTime()) {
          return leftProjectedDate - rightProjectedDate;
        }
      } else if (leftProjectedDate && !rightProjectedDate) {
        return -1;
      } else if (!leftProjectedDate && rightProjectedDate) {
        return 1;
      }

      const leftIsScheduled = normalizeText(left?.release_status) === "scheduled";
      const rightIsScheduled = normalizeText(right?.release_status) === "scheduled";
      if (leftIsScheduled !== rightIsScheduled) {
        return leftIsScheduled ? -1 : 1;
      }

      const byPriority = Number(right?.priority_score || 0) - Number(left?.priority_score || 0);
      if (byPriority !== 0) {
        return byPriority;
      }

      return Number(left?.id || 0) - Number(right?.id || 0);
    });
  futureEpisodes.forEach((episode) => {
    if (episodeNumberMap.has(String(episode.id))) {
      return;
    }
    const parsedNumber = parseLegacyEpisodeNumber(episode.legacy_episode_number);
    const isScheduled = normalizeText(episode.release_status) === "scheduled";
    nextNumber = parsedNumber || nextNumber + 1;
    episodeNumberMap.set(String(episode.id), {
      number: nextNumber,
      label: `Episode ${formatEpisodeNumberLabel(episode.legacy_episode_number, nextNumber)} (${isScheduled ? "Prospective" : "Queued"})`,
    });
  });

  return episodeNumberMap;
}

function getEpisodeNumberLabel(episode, episodeNumberMap) {
  if (!episode?.id) {
    return "Episode #TBD";
  }
  const entry = episodeNumberMap.get(String(episode.id));
  return entry?.label || "Episode #TBD";
}

function suggestPriorityScoreForEpisode(episodeLike = {}) {
  const releaseStatus = normalizeText(episodeLike.release_status);
  const productionStatus = normalizeText(episodeLike.production_status);
  const promotionStatus = normalizeText(episodeLike.promotion_status);

  if (releaseStatus === "released") return 10;
  if (releaseStatus === "scheduled") return 8;
  if (productionStatus === "released") return 10;
  if (productionStatus === "ready" && promotionStatus === "ready") return 8;
  if (productionStatus === "ready") return 7;
  if (productionStatus === "editing") return 6;
  if (productionStatus === "recorded" && promotionStatus === "needs_assets") return 5;
  if (productionStatus === "recorded") return 5;
  return 3;
}

function clampPriorityScore(value, fallback = 0) {
  const parsed = Number.parseFloat(String(value ?? "").trim());
  if (Number.isNaN(parsed)) {
    return fallback;
  }
  return Math.max(0, Math.min(10, parsed));
}

function renderWeeklySystemPanel(system) {
  if (!planningWeeklySystem || !system) {
    return;
  }
  const steps = (system.steps || [])
    .map((step) => `<li><strong>${step.day}${step.time_label ? ` · ${step.time_label}` : ""}</strong>: ${step.title}. ${step.description}</li>`)
    .join("");
  const principles = (system.principles || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const metrics = (system.metrics || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  planningWeeklySystem.innerHTML = `
    <div class="insight-stack">
      <strong class="insight-label">What this tab is for</strong>
      <ul>
        <li>Use this as the operating model for a normal Mirror Talk release week.</li>
        <li>Keep episode editing focused on guest, title, scheduling, and release readiness instead of campaign task tracking.</li>
        <li>The recommendation cards use this rhythm to suggest what should happen next, but they do not complete anything automatically.</li>
      </ul>
    </div>
    <div class="insight-stack">
      <strong class="insight-label">Weekly timetable</strong>
      <ul>${steps}</ul>
    </div>
    <div class="insight-stack">
      <strong class="insight-label">Core principles</strong>
      <ul>${principles}</ul>
    </div>
    <div class="insight-stack">
      <strong class="insight-label">Key metrics</strong>
      <ul>${metrics}</ul>
    </div>
  `;
}

function renderAskSyncBreakdown(result) {
  if (!result) {
    askSyncBreakdown.classList.add("hidden");
    askSyncBreakdown.innerHTML = "";
    askSyncAmbiguous.classList.add("hidden");
    askSyncAmbiguous.innerHTML = "";
    return;
  }
  const items = [
    ["Matched by title", result.matched_by_title ?? 0],
    ["Matched by guest", result.matched_by_guest ?? 0],
    ["Updated transcript", result.updated_transcript ?? 0],
    ["Updated published title only", result.updated_title_only ?? 0],
    ["Skipped ambiguous", result.skipped_ambiguous ?? 0],
  ];
  const proposals = result.preview_only ? (result.proposed_matches || []) : [];
  const proposalMarkup = proposals.map((proposal) => {
    const local = proposal.local_episode || {};
    const remote = proposal.remote_episode || {};
    const changes = proposal.changes || {};
    const changeLabels = [
      changes.transcript ? "add transcript" : "keep existing transcript",
      changes.published_title ? "store published title" : "published title unchanged",
    ];
    return `
      <label class="sync-match-card">
        <input type="checkbox" data-ask-sync-match
          data-local-episode-id="${Number(local.id || 0)}"
          data-remote-episode-ref="${escapeHtml(remote.ref || "")}" checked />
        <span>
          <strong>${escapeHtml(local.working_title || "Untitled local episode")}</strong>
          <small>${escapeHtml(local.guest_name || "Unknown guest")} · ${escapeHtml(local.release_status || "unplanned")} ${local.release_date ? `· ${escapeHtml(formatDateTime(local.release_date))}` : ""}</small>
          <span class="sync-arrow" aria-hidden="true">→</span>
          <strong>${escapeHtml(remote.title || "Untitled Ask episode")}</strong>
          <small>${escapeHtml(formatMatchMethod(proposal.method))} · score ${Number(proposal.score || 0)} · ${escapeHtml(changeLabels.join(" · "))}</small>
        </span>
      </label>
    `;
  }).join("");
  askSyncBreakdown.classList.remove("hidden");
  askSyncBreakdown.innerHTML = `
    <strong class="insight-label">${result.preview_only ? "Review proposed matches" : "Sync breakdown"}</strong>
    <ul>${items.map(([label, value]) => `<li>${label}: ${value}</li>`).join("")}</ul>
    ${result.preview_only ? `
      <p>No episode data has changed. Select only the matches you have verified.</p>
      <div class="sync-match-list">${proposalMarkup || "<p>No safe matches are ready to apply.</p>"}</div>
      <div class="form-actions">
        <button id="ask-sync-apply" type="button" class="primary-button" ${proposals.length ? "" : "disabled"}>Apply Selected Matches</button>
      </div>
    ` : ""}
  `;
  const applyButton = document.getElementById("ask-sync-apply");
  if (applyButton) {
    applyButton.addEventListener("click", applySelectedAskSyncMatches);
  }
  renderAskSyncAmbiguous(result.ambiguous_matches || []);
}

async function applySelectedAskSyncMatches() {
  if (!pendingAskSyncRequest) return;
  const approvedMatches = Array.from(
    askSyncBreakdown.querySelectorAll("[data-ask-sync-match]:checked"),
    (input) => ({
      local_episode_id: Number(input.dataset.localEpisodeId || 0),
      remote_episode_ref: input.dataset.remoteEpisodeRef || "",
    }),
  ).filter((item) => item.local_episode_id && item.remote_episode_ref);
  if (!approvedMatches.length) {
    setMessage(askSyncMessage, "Select at least one verified match before applying.", "error");
    return;
  }
  const applyButton = document.getElementById("ask-sync-apply");
  applyButton.disabled = true;
  applyButton.textContent = "Applying...";
  setMessage(askSyncMessage, "Applying verified transcript matches...", "pending");
  try {
    const result = await fetchJSON("/api/ask-mirror-talk/sync", {
      method: "POST",
      body: JSON.stringify({
        ...pendingAskSyncRequest,
        preview_only: false,
        approved_matches: approvedMatches,
      }),
    });
    setMessage(
      askSyncMessage,
      `Applied ${result.updated} verified match${result.updated === 1 ? "" : "es"}. Working titles and release metadata were preserved.`,
      "success",
    );
    pendingAskSyncRequest = null;
    renderAskSyncBreakdown(result);
    await loadPlanning();
  } catch (error) {
    setMessage(askSyncMessage, error.message || "Failed to apply transcript matches", "error");
    applyButton.disabled = false;
    applyButton.textContent = "Apply Selected Matches";
  }
}

function formatMatchMethod(method) {
  const labels = {
    title: "Exact title",
    guest_title: "Guest name in title",
    guest_description: "Guest name in description",
    guest_partial: "Mostly matching guest name",
    guest_name_fragment: "Partial guest-name fragment",
  };
  return labels[method] || "Match signal";
}

function renderAskSyncAmbiguous(items) {
  if (!items.length) {
    askSyncAmbiguous.classList.add("hidden");
    askSyncAmbiguous.innerHTML = "";
    return;
  }

  const cards = items
    .map((item) => {
      const local = item.local_episode || {};
      const localDate = local.release_date || local.interview_date;
      const candidates = (item.candidates || [])
        .map((candidate) => {
          const parts = [
            `Score ${candidate.score ?? 0}`,
            formatMatchMethod(candidate.method),
          ];
          if (candidate.published_at) {
            parts.push(`Published ${formatDateTime(candidate.published_at)}`);
          }
          if (candidate.date_gap_days !== null && candidate.date_gap_days !== undefined) {
            parts.push(`Date gap ${candidate.date_gap_days}d`);
          }
          parts.push(candidate.has_transcript ? "Transcript available" : "No transcript");
          return `
            <li>
              <strong>${escapeHtml(candidate.title || "Untitled Ask episode")}</strong>
              <span>${escapeHtml(parts.join(" · "))}</span>
            </li>
          `;
        })
        .join("");

      return `
        <article class="mini-card">
          <strong>${escapeHtml(local.title || "Untitled local episode")}</strong>
          <p>${escapeHtml(local.guest_name || "Unknown guest")}${localDate ? ` · ${escapeHtml(formatDateTime(localDate))}` : ""}</p>
          <ul>${candidates}</ul>
        </article>
      `;
    })
    .join("");

  askSyncAmbiguous.classList.remove("hidden");
  askSyncAmbiguous.innerHTML = `
    <strong class="insight-label">Ambiguous matches needing review</strong>
    <p>The sync found multiple plausible Ask Mirror Talk episodes for these records, so it skipped them rather than guessing.</p>
    <div class="stack-list">${cards}</div>
  `;
}

function renderEpisodeBadges(episode) {
  const badges = [];
  if (normalizeText(episode.source_type) === "ask_mirror_talk_sync") {
    badges.push('<span class="signal-chip good">Ask Synced</span>');
  }
  if (episode.transcript_text) {
    badges.push('<span class="signal-chip good">Transcript Available</span>');
  } else if (transcriptExpectedSoon(episode)) {
    badges.push('<span class="signal-chip warning">Missing Transcript</span>');
  }
  return badges.length ? `<div class="signal-list">${badges.join("")}</div>` : "";
}

function renderOutreachSummary(summary) {
  if (!summary) {
    return "";
  }
  const completed = (summary.completed_labels || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const pending = (summary.pending_labels || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  return `
    <div class="operations-preview">
      <strong class="insight-label">Outreach status for this episode</strong>
      <p><strong>${summary.progress_label}</strong></p>
      <p>${escapeHtml(summary.next_step || "")}</p>
      <p class="helper-copy">Mark a step complete only after it has actually been published, sent, posted, or reviewed.</p>
      ${completed ? `<div class="insight-stack"><strong class="insight-label">Already done</strong><ul>${completed}</ul></div>` : ""}
      ${pending ? `<div class="insight-stack"><strong class="insight-label">Still ahead in this launch cycle</strong><ul>${pending}</ul></div>` : ""}
    </div>
  `;
}

function renderReleaseComposer(node, episode, preview) {
  node.classList.remove("hidden");
  node.innerHTML = `
    <div class="inline-editor-title">Release Email</div>
    <label class="full-width">
      <span>Subject</span>
      <input data-release-field="subject" type="text" value="${escapeHtml(preview.subject || "")}" />
    </label>
    <label class="full-width">
      <span>Email Body</span>
      <textarea data-release-field="body" rows="12">${escapeHtml(preview.body || "")}</textarea>
    </label>
    <div class="inline-editor-actions full-width">
      <button type="button" class="primary-button" data-release-composer-action="send">Send Edited Release Email</button>
      <button type="button" class="ghost-button" data-release-composer-action="close">Close</button>
    </div>
    <p class="message" data-release-composer-message aria-live="polite"></p>
  `;

  const subjectField = node.querySelector("[data-release-field='subject']");
  const bodyField = node.querySelector("[data-release-field='body']");
  const sendButton = node.querySelector("[data-release-composer-action='send']");
  const closeButton = node.querySelector("[data-release-composer-action='close']");
  const messageNode = node.querySelector("[data-release-composer-message]");

  closeButton.addEventListener("click", () => {
    node.classList.add("hidden");
    node.innerHTML = "";
  });

  sendButton.addEventListener("click", async () => {
    sendButton.disabled = true;
    sendButton.textContent = "Sending...";
    setMessage(messageNode, "Sending edited release email...", "pending");
    try {
      await fetchJSON(`/api/episodes/${episode.id}/send-release-email`, {
        method: "POST",
        body: JSON.stringify({
          subject: subjectField.value,
          body: bodyField.value,
        }),
      });
      setMessage(
        episodeMessage,
        `Release email sent to ${episode.guest_name || episode.guest_email}. The published follow-up is complete for this episode.`,
        "success",
      );
      activeEpisodeActionFeedback = {
        id: episode.id,
        text: `Release email sent to ${episode.guest_name || episode.guest_email}.`,
        tone: "success",
      };
        node.innerHTML = `<p class="composer-feedback success">Release email sent to ${escapeHtml(episode.guest_name || episode.guest_email)}.</p>`;
      await loadPlanning();
    } catch (error) {
      setMessage(messageNode, error.message, "error");
      sendButton.disabled = false;
      sendButton.textContent = "Send Edited Release Email";
      setMessage(episodeMessage, error.message, "error");
    }
  });
}

function splitRecommendationInsights(reason) {
  const text = String(reason || "").trim();
  if (!text) {
    return {
      strengths: [],
      cautions: [],
      summary: "Good fit for the next release slot.",
    };
  }

  const sentences = text
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
  const cautionPatterns = [
    "needs promo assets",
    "promotion readiness is still unclear",
    "same guest appeared very recently",
    "same guest has already been featured",
    "already warm in the recent release mix",
    "dominates",
    "fatigue",
    "risk",
    "missing",
    "however",
    "but",
  ];
  const strengths = [];
  const cautions = [];

  sentences.forEach((sentence) => {
    const normalized = normalizeText(sentence);
    if (cautionPatterns.some((pattern) => normalized.includes(pattern))) {
      cautions.push(sentence);
    } else {
      strengths.push(sentence);
    }
  });

  return {
    strengths: strengths.slice(0, 2),
    cautions: cautions.slice(0, 2),
    summary: sentences[0] || text,
  };
}

function populateSelect(selectNode, values, defaultLabel) {
  const currentValue = selectNode.value;
  selectNode.innerHTML = `<option value="">${defaultLabel}</option>`;
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    selectNode.appendChild(option);
  });
  selectNode.value = values.includes(currentValue) ? currentValue : "";
}

function populatePlanningFilters(categories, episodes) {
  const sortedCategories = [...new Set((categories || []).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b),
  );
  populateSelect(recommendationCategoryFilter, sortedCategories, "All Categories");
  populateSelect(episodeCategoryFilter, sortedCategories, "All Categories");

  const years = Array.from(new Set((episodes || []).map(getEpisodeYear).filter(Boolean))).sort(
    (a, b) => Number(b) - Number(a),
  );
  populateSelect(episodeYearFilter, years, "All Years");
}

function renderTeamMemberOptions(container, members) {
  if (!container) return;
  container.replaceChildren();
  (members || []).forEach((member) => {
    const option = document.createElement("option");
    option.value = member.username || "";
    option.label = `${member.label || member.username || "Team member"} · ${member.role || "member"}`;
    container.appendChild(option);
  });
}

function resetEpisodeForm() {
  episodeForm.reset();
  episodeForm.elements.id.value = "";
  episodeForm.elements.interview_id.value = "";
  episodeForm.elements.outreach_plan.value = JSON.stringify(normalizeOutreachPlan(null));
  episodeForm.elements.release_status.value = "unplanned";
  episodeForm.elements.production_status.value = "idea";
  episodeForm.elements.promotion_status.value = "unknown";
  episodeForm.elements.editorial_disposition.value = "active";
  episodeForm.elements.priority_score.value = String(clampPriorityScore(suggestPriorityScoreForEpisode({}), 3));
  episodeForm.elements.legacy_episode_number.value = computeNextLegacyEpisodeNumber(latestPlanningPayload.episodes || []);
  episodeSubmitButton.textContent = "Save Episode";
  episodeResetButton.hidden = true;
  activeEpisodeBaseline = null;
  clearEpisodeConflict();
  if (episodeEditorTitle) episodeEditorTitle.textContent = "Add episode";
}

function clearEpisodeConflict() {
  activeEpisodeConflict = null;
  episodeConflictPanel?.classList.add("hidden");
  if (episodeConflictFields) episodeConflictFields.textContent = "";
}

function episodeEditorSnapshot() {
  if (!episodeForm) return {};
  return Object.fromEntries(new FormData(episodeForm).entries());
}

function conflictFieldLabels(conflictCurrent) {
  const latest = conflictCurrent || {};
  const baseline = activeEpisodeBaseline || {};
  const labels = {
    guest_name: "guest name",
    guest_email: "guest email",
    episode_title: "working title",
    published_title: "published title",
    topic: "topic",
    category: "category",
    interview_date: "interview date",
    recording_date: "recording date",
    owner: "owner",
    release_date: "release date",
    release_status: "release status",
    production_status: "production status",
    promotion_status: "promotion status",
    editorial_disposition: "editorial disposition",
    priority_score: "priority",
    show_notes_url: "show notes",
    release_files_url: "files link",
    recommendation_reason: "recommendation reason",
    notes: "notes",
  };
  return Object.entries(labels)
    .filter(([field]) => String(latest[field] ?? "") !== String(baseline[field] ?? ""))
    .map(([, label]) => label);
}

function showEpisodeConflict(conflict) {
  activeEpisodeConflict = conflict;
  const changedFields = conflictFieldLabels(conflict?.current);
  episodeConflictPanel?.classList.remove("hidden");
  if (episodeConflictSummary) {
    episodeConflictSummary.textContent = "Someone or an automated workflow saved a newer version. Your draft is still intact.";
  }
  if (episodeConflictFields) {
    episodeConflictFields.textContent = changedFields.length
      ? `Newer fields: ${changedFields.join(", ")}.`
      : "The stored version changed. Load it or rebase your draft before saving.";
  }
  episodeConflictPanel?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function promoteInlineConflictToEditor(episode, draftPayload, conflict) {
  loadEpisodeIntoForm(episode);
  const staleBaseline = episodeEditorSnapshot();
  loadEpisodeIntoForm({ ...episode, ...draftPayload, id: episode.id });
  activeEpisodeBaseline = staleBaseline;
  showEpisodeConflict(conflict);
  activeEpisodeEditorId = null;
  setMessage(
    episodeMessage,
    "A newer version exists. Your quick-edit draft is open in the full editor so you can resolve it safely.",
    "warning",
  );
}

function openEpisodeEditor({ restoreFocusTo = document.activeElement } = {}) {
  if (!episodeEditorModal) return;
  if (episodeEditorModal.classList.contains("hidden")) {
    episodeEditorReturnFocus = restoreFocusTo instanceof HTMLElement ? restoreFocusTo : null;
  }
  episodeEditorModal.classList.remove("hidden");
  const focusTarget = episodeForm?.elements?.id?.value
    ? episodeForm.elements.episode_title
    : episodeForm?.elements?.guest_name;
  focusTarget?.focus({ preventScroll: true });
}

function closeEpisodeEditor({ restoreFocus = true } = {}) {
  if (!episodeEditorModal || episodeEditorModal.classList.contains("hidden")) return;
  episodeEditorModal.classList.add("hidden");
  if (restoreFocus && episodeEditorReturnFocus?.isConnected) {
    episodeEditorReturnFocus.focus();
  }
  episodeEditorReturnFocus = null;
}

function initializeEpisodeEditor() {
  const editorContent = episodeEditorModal?.querySelector(".episode-editor-modal-content");
  if (editorContent && episodeEditorSection) {
    editorContent.appendChild(episodeEditorSection);
  }
}

function loadEpisodeIntoForm(episode, { releaseDate = "", releaseStatus = "" } = {}) {
  clearEpisodeConflict();
  const effectiveReleaseStatus = releaseStatus || episode.release_status || "unplanned";
  const effectiveProductionStatus = episode.production_status || "idea";
  const effectivePromotionStatus = episode.promotion_status || "unknown";
  episodeForm.elements.id.value = episode.id || "";
  episodeForm.elements.row_version.value = episode.row_version || "";
  episodeForm.elements.interview_id.value = episode.interview_id || "";
  episodeForm.elements.guest_name.value = episode.guest_name || "";
  episodeForm.elements.guest_email.value = episode.guest_email || "";
  episodeForm.elements.website.value = episode.website || "";
  episodeForm.elements.episode_title.value = episode.episode_title || "";
  episodeForm.elements.published_title.value = episode.published_title || "";
  episodeForm.elements.topic.value = episode.topic || "";
  episodeForm.elements.category.value = episode.category || "";
  episodeForm.elements.interview_date.value = formatDateForDateInput(episode.interview_date);
  episodeForm.elements.recording_date.value = formatDateForDateInput(episode.recording_date);
  episodeForm.elements.owner.value = episode.owner || "";
  episodeForm.elements.release_date.value = formatDateForDateTimeInput(releaseDate || episode.release_date);
  episodeForm.elements.release_status.value = effectiveReleaseStatus;
  episodeForm.elements.production_status.value = effectiveProductionStatus;
  episodeForm.elements.promotion_status.value = effectivePromotionStatus;
  episodeForm.elements.editorial_disposition.value = episode.editorial_disposition || "active";
  const suggestedPriorityScore = suggestPriorityScoreForEpisode({
    release_status: effectiveReleaseStatus,
    production_status: effectiveProductionStatus,
    promotion_status: effectivePromotionStatus,
  });
  episodeForm.elements.priority_score.value = String(
    Number(episode.priority_score || 0) > 0
      ? clampPriorityScore(episode.priority_score, suggestedPriorityScore)
      : clampPriorityScore(suggestedPriorityScore, 3)
  );
  episodeForm.elements.legacy_episode_number.value = episode.legacy_episode_number
    || computeNextLegacyEpisodeNumber(latestPlanningPayload.episodes || [], episode.id || "");
  episodeForm.elements.riverside_status.value = episode.riverside_status || "";
  episodeForm.elements.show_notes_url.value = episode.show_notes_url || "";
  episodeForm.elements.release_files_url.value = episode.release_files_url || "";
  episodeForm.elements.transcript_text.value = episode.transcript_text || "";
  episodeForm.elements.outreach_plan.value = JSON.stringify(normalizeOutreachPlan(episode.outreach_plan));
  episodeForm.elements.recommendation_reason.value = episode.recommendation_reason || "";
  episodeForm.elements.notes.value = episode.notes || "";
  episodeSubmitButton.textContent = "Update Episode";
  episodeResetButton.hidden = false;
  if (episodeEditorTitle) episodeEditorTitle.textContent = "Edit episode";
  activeEpisodeBaseline = episodeEditorSnapshot();
  openEpisodeEditor();
}

function renderEpisodeInlineEditor(container, episode) {
  container.innerHTML = `
    <div class="inline-editor-title">Quick Edit Episode</div>
    <form class="inline-editor-form" data-inline-episode-form novalidate>
      <input name="row_version" type="hidden" value="${Number(episode.row_version || 1)}" />
      ${createFieldMarkup("Episode Title", `<input name="episode_title" type="text" value="${escapeHtml(episode.episode_title || "")}" required />`, true)}
      ${createFieldMarkup("Published Title", `<input name="published_title" type="text" value="${escapeHtml(episode.published_title || "")}" />`, true)}
      ${createFieldMarkup("Guest Name", `<input name="guest_name" type="text" value="${escapeHtml(episode.guest_name || "")}" required />`)}
      ${createFieldMarkup("Guest Email", `<input name="guest_email" type="text" inputmode="email" autocapitalize="off" spellcheck="false" value="${escapeHtml(episode.guest_email || "")}" />`)}
      ${createFieldMarkup("Category", `<input name="category" type="text" list="episode-category-options" value="${escapeHtml(episode.category || "")}" />`)}
      ${createFieldMarkup("Release Date", `<input name="release_date" type="datetime-local" value="${formatDateForDateTimeInput(episode.release_date)}" />`)}
      ${createFieldMarkup("Release Status", `
        <select name="release_status">
          <option value="unplanned" ${normalizeText(episode.release_status) === "unplanned" ? "selected" : ""}>Unplanned</option>
          <option value="scheduled" ${normalizeText(episode.release_status) === "scheduled" ? "selected" : ""}>Scheduled</option>
          <option value="released" ${normalizeText(episode.release_status) === "released" ? "selected" : ""}>Released</option>
        </select>
      `)}
      ${createFieldMarkup("Production", `
        <select name="production_status">
          <option value="idea" ${normalizeText(episode.production_status) === "idea" ? "selected" : ""}>Idea</option>
          <option value="recorded" ${normalizeText(episode.production_status) === "recorded" ? "selected" : ""}>Recorded</option>
          <option value="editing" ${normalizeText(episode.production_status) === "editing" ? "selected" : ""}>Editing</option>
          <option value="ready" ${normalizeText(episode.production_status) === "ready" ? "selected" : ""}>Ready</option>
          <option value="released" ${normalizeText(episode.production_status) === "released" ? "selected" : ""}>Released</option>
        </select>
      `)}
      ${createFieldMarkup("Promotion", `
        <select name="promotion_status">
          <option value="unknown" ${normalizeText(episode.promotion_status) === "unknown" ? "selected" : ""}>Unknown</option>
          <option value="needs_assets" ${normalizeText(episode.promotion_status) === "needs_assets" ? "selected" : ""}>Needs Assets</option>
          <option value="ready" ${normalizeText(episode.promotion_status) === "ready" ? "selected" : ""}>Ready</option>
          <option value="released" ${normalizeText(episode.promotion_status) === "released" ? "selected" : ""}>Released</option>
        </select>
      `)}
      ${createFieldMarkup("Priority", `<input name="priority_score" type="number" min="0" max="10" step="0.5" value="${clampPriorityScore(episode.priority_score, suggestPriorityScoreForEpisode(episode))}" />`)}
      ${createFieldMarkup("Disposition", `
        <select name="editorial_disposition">
          <option value="active" ${normalizeText(episode.editorial_disposition) === "active" ? "selected" : ""}>Active</option>
          <option value="hold" ${normalizeText(episode.editorial_disposition) === "hold" ? "selected" : ""}>Hold</option>
          <option value="archive" ${normalizeText(episode.editorial_disposition) === "archive" ? "selected" : ""}>Archive</option>
          <option value="retire" ${normalizeText(episode.editorial_disposition) === "retire" ? "selected" : ""}>Retire</option>
        </select>
      `)}
      ${createFieldMarkup("Topic", `<input name="topic" type="text" value="${escapeHtml(episode.topic || "")}" />`, true)}
      ${createFieldMarkup("Show Note / Blogpost URL", `<input name="show_notes_url" type="text" inputmode="url" autocapitalize="off" spellcheck="false" value="${escapeHtml(episode.show_notes_url || "")}" />`, true)}
      ${createFieldMarkup("Files URL", `<input name="release_files_url" type="text" inputmode="url" autocapitalize="off" spellcheck="false" value="${escapeHtml(episode.release_files_url || "")}" />`, true)}
      ${createFieldMarkup("Transcript", `<textarea name="transcript_text" rows="5">${escapeHtml(episode.transcript_text || "")}</textarea>`, true)}
      ${createFieldMarkup("Notes", `<textarea name="notes" rows="3">${escapeHtml(episode.notes || "")}</textarea>`, true)}
      <div class="inline-editor-actions full-width">
        <button type="submit" class="primary-button">Save Changes</button>
        <button type="button" class="secondary-button" data-inline-episode-schedule>Schedule Recommended Slot</button>
        <button type="button" class="ghost-button" data-inline-episode-cancel>Close</button>
      </div>
      <p class="message" data-inline-episode-message aria-live="polite"></p>
    </form>
  `;

  const form = container.querySelector("[data-inline-episode-form]");
  const messageNode = container.querySelector("[data-inline-episode-message]");
  const scheduleButton = container.querySelector("[data-inline-episode-schedule]");
  const cancelButton = container.querySelector("[data-inline-episode-cancel]");
  const saveButton = form.querySelector("button[type='submit']");

  if (activeEpisodeFeedback.id === episode.id && activeEpisodeFeedback.text) {
    setMessage(messageNode, activeEpisodeFeedback.text, activeEpisodeFeedback.tone);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(form).entries());
    payload.priority_score = String(
      clampPriorityScore(payload.priority_score, suggestPriorityScoreForEpisode(payload))
    );
    saveButton.disabled = true;
    saveButton.textContent = "Saving...";
    try {
      validateEpisodePayloadForSave(payload);
      const savedEpisode = await fetchJSON(`/api/episodes/${episode.id}`, {
        method: "POST",
        body: JSON.stringify(cleanEpisodePayloadForSave(payload)),
      });
      replaceEpisodeInPayload(savedEpisode);
      activeEpisodeFeedback = {
        id: episode.id,
        text: `Saved ${payload.episode_title || "episode"}.`,
        tone: "success",
      };
      setMessage(episodeMessage, `Updated ${payload.episode_title || "episode"}.`, "success");
      activeEpisodeEditorId = episode.id;
      renderPlanning();
      refreshPlanningQuietly();
    } catch (error) {
      if (error.status === 409 && error.payload?.conflict) {
        promoteInlineConflictToEditor(episode, payload, error.payload.conflict);
      } else {
        setMessage(messageNode, error.message, "error");
      }
      saveButton.disabled = false;
      saveButton.textContent = "Save Changes";
    }
  });

  scheduleButton.addEventListener("click", async () => {
    const recommendation = (latestPlanningPayload.recommendations || []).find((item) => Number(item.id) === Number(episode.id));
    if (!recommendation?.recommended_release_date) {
      setMessage(messageNode, "No recommended release slot is available for this episode yet.", "error");
      return;
    }

    const payload = Object.fromEntries(new FormData(form).entries());
    payload.priority_score = String(
      clampPriorityScore(payload.priority_score, suggestPriorityScoreForEpisode(payload))
    );
    payload.release_date = formatDateForDateTimeInput(recommendation.recommended_release_date);
    payload.release_status = "scheduled";
    scheduleButton.disabled = true;
    scheduleButton.textContent = "Scheduling...";

    try {
      const savedEpisode = await fetchJSON(`/api/episodes/${episode.id}`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      replaceEpisodeInPayload(savedEpisode);
      activeEpisodeFeedback = {
        id: episode.id,
        text: `Scheduled for ${formatDateTime(recommendation.recommended_release_date)}.`,
        tone: "success",
      };
      setMessage(
        episodeMessage,
        `Scheduled ${payload.episode_title || "episode"} for ${formatDateTime(recommendation.recommended_release_date)}.`,
        "success",
      );
      activeEpisodeEditorId = episode.id;
      renderPlanning();
      refreshPlanningQuietly();
    } catch (error) {
      if (error.status === 409 && error.payload?.conflict) {
        promoteInlineConflictToEditor(episode, payload, error.payload.conflict);
      } else {
        setMessage(messageNode, error.message, "error");
      }
      scheduleButton.disabled = false;
      scheduleButton.textContent = "Schedule Recommended Slot";
    }
  });

  cancelButton.addEventListener("click", () => {
    activeEpisodeEditorId = null;
    activeEpisodeFeedback = { id: null, text: "", tone: "" };
    renderPlanning();
  });
}

function renderCategoryOptions(categories) {
  episodeCategoryOptions.innerHTML = "";
  (categories || []).forEach((category) => {
    const option = document.createElement("option");
    option.value = category;
    episodeCategoryOptions.appendChild(option);
  });
}

function renderExportFields() {
  const fields = EXPORT_FIELD_CONFIG[exportListName.value] || [];
  exportFields.innerHTML = "";
  fields.forEach(([fieldName, label], index) => {
    const option = document.createElement("label");
    option.className = "export-field-option";
    option.innerHTML = `
      <input type="checkbox" name="fields" value="${fieldName}" ${index < 4 ? "checked" : ""} />
      <span>${label}</span>
    `;
    exportFields.appendChild(option);
  });
}

function filterEpisodes(episodes) {
  const searchTerm = normalizeText(episodeSearchInput.value);
  const category = episodeCategoryFilter.value;
  const year = episodeYearFilter.value;
  const releaseStatus = episodeReleaseFilter.value;
  const productionStatus = episodeProductionFilter.value;
  const transcriptStatus = episodeTranscriptFilter.value;
  const sortMode = episodeSort.value || "release_asc";

  const filtered = episodes.filter((episode) => {
    const haystack = [
      episode.guest_name,
      episode.guest_email,
      episode.episode_title,
      episode.topic,
      episode.category,
    ].map(normalizeText).join(" ");
    if (searchTerm && !haystack.includes(searchTerm)) {
      return false;
    }
    if (category && normalizeText(episode.category) !== normalizeText(category)) {
      return false;
    }
    if (year && getEpisodeYear(episode) !== year) {
      return false;
    }
    if (releaseStatus && normalizeText(episode.release_status) !== releaseStatus) {
      return false;
    }
    if (productionStatus && normalizeText(episode.production_status) !== productionStatus) {
      return false;
    }
    if (transcriptStatus === "has_transcript" && !episodeHasTranscript(episode)) {
      return false;
    }
    if (transcriptStatus === "missing_transcript" && (episodeHasTranscript(episode) || !transcriptExpectedSoon(episode))) {
      return false;
    }
    if (activeProductionStage && getProductionStage(episode) !== activeProductionStage) {
      return false;
    }
    if (activeEpisodePreset === "ready_to_schedule") {
      if (!(
        normalizeText(episode.production_status) === "ready" &&
        !["scheduled", "released"].includes(normalizeText(episode.release_status))
      )) {
        return false;
      }
    }
    if (activeEpisodePreset === "scheduled" && normalizeText(episode.release_status) !== "scheduled") {
      return false;
    }
    if (activeEpisodePreset === "needs_assets" && normalizeText(episode.promotion_status) !== "needs_assets") {
      return false;
    }
    if (activeEpisodePreset === "released_archive" && normalizeText(episode.release_status) !== "released") {
      return false;
    }
    if (
      activeEpisodePreset === "disposition_review"
      && (normalizeText(episode.release_status) === "released" || normalizeText(episode.editorial_disposition || "active") !== "active")
    ) {
      return false;
    }
    return true;
  });

  filtered.sort((left, right) => window.PlanningSort.compareEpisodes(left, right, sortMode));

  return filtered;
}

function filterRecommendations(recommendations) {
  const searchTerm = normalizeText(recommendationSearchInput.value);
  const category = recommendationCategoryFilter.value;
  const sortMode = recommendationSort.value || "score";

  const filtered = recommendations.filter((episode) => {
    // IMPORTANT: Exclude released episodes from Scheduling Intelligence
    // They should never appear in recommendations
    const releaseStatus = normalizeText(episode.release_status);
    if (releaseStatus === "released") {
      return false;
    }
    
    const haystack = [
      episode.guest_name,
      episode.guest_email,
      episode.episode_title,
      episode.topic,
      episode.category,
      episode.recommendation_reason,
    ].map(normalizeText).join(" ");
    if (searchTerm && !haystack.includes(searchTerm)) {
      return false;
    }
    if (category && normalizeText(episode.category) !== normalizeText(category)) {
      return false;
    }
    if (activeRecommendationPreset === "ready" && normalizeText(episode.promotion_status) !== "ready") {
      return false;
    }
    if (activeRecommendationPreset === "needs_assets" && normalizeText(episode.promotion_status) !== "needs_assets") {
      return false;
    }
    if (activeRecommendationPreset === "seasonal" && !normalizeText(episode.recommendation_reason).includes("season")) {
      return false;
    }
    return true;
  });

  filtered.sort((left, right) => {
    if (sortMode === "recommended_date") {
      const leftDate = parseDate(left.recommended_release_date);
      const rightDate = parseDate(right.recommended_release_date);
      if (!leftDate && !rightDate) return 0;
      if (!leftDate) return 1;
      if (!rightDate) return -1;
      return leftDate - rightDate;
    }
    if (sortMode === "interview_date") {
      const leftDate = parseDate(left.interview_date);
      const rightDate = parseDate(right.interview_date);
      if (!leftDate && !rightDate) return 0;
      if (!leftDate) return 1;
      if (!rightDate) return -1;
      return rightDate - leftDate;
    }
    if (sortMode === "guest_name") {
      return normalizeText(left.guest_name).localeCompare(normalizeText(right.guest_name));
    }
    return Number(right.priority_score || 0) - Number(left.priority_score || 0);
  });

  return filtered;
}

function openScheduleModal(episode) {
  scheduleForm.elements.episode_id.value = episode.id;
  scheduleForm.elements.release_date.value = formatDateForDateTimeInput(episode.release_date);
  scheduleForm.elements.release_date.focus();
  setMessage(scheduleModalMessage, "", "");
  scheduleModal.classList.remove("hidden");
}

function closeScheduleModal() {
  scheduleModal.classList.add("hidden");
  scheduleForm.reset();
  setMessage(scheduleModalMessage, "", "");
}

function deriveEpisodeNextAction(episode) {
  const releaseStatus = normalizeText(episode.release_status);
  const productionStatus = normalizeText(episode.production_status);
  const promotionStatus = normalizeText(episode.promotion_status);
  const releaseDate = parseDate(episode.release_date);
  const releaseIsDue = releaseDate && releaseDate <= new Date();
  if (releaseStatus === "released") {
    return {
      label: "Review post-release workflow",
      reason: episode.outreach_summary?.next_step || "Confirm guest follow-up and distribution are complete.",
      action: "form",
      button: "Review episode",
      tone: "complete",
    };
  }
  if (releaseStatus === "scheduled") {
    if (productionStatus !== "ready" || promotionStatus !== "ready") {
      return {
        label: "Resolve release blockers",
        reason: "The episode has a release date, but production or promotion is not ready.",
        action: "form",
        button: "Fix readiness",
        tone: "urgent",
      };
    }
    if (releaseIsDue) {
      return {
        label: "Confirm publication",
        reason: "The scheduled release time has arrived and all readiness gates pass.",
        action: "release",
        button: "Mark released",
        tone: "high",
      };
    }
    return {
      label: "Verify the release plan",
      reason: `Scheduled for ${formatDateTime(episode.release_date)} and currently ready.`,
      action: "form",
      button: "Review plan",
      tone: "normal",
    };
  }
  if (productionStatus === "ready") {
    return {
      label: "Choose a release slot",
      reason: promotionStatus === "ready" ? "Production and promotional assets are ready." : "Production is ready; review remaining promotion needs while scheduling.",
      action: "schedule",
      button: "Schedule episode",
      tone: promotionStatus === "ready" ? "high" : "normal",
    };
  }
  if (promotionStatus === "needs_assets") {
    return {
      label: "Complete promotional assets",
      reason: "The release cannot be considered ready until its promotional package is complete.",
      action: "form",
      button: "Update assets",
      tone: "high",
    };
  }
  if (["recorded", "editing"].includes(productionStatus)) {
    return {
      label: productionStatus === "recorded" ? "Start production" : "Advance the edit",
      reason: `The episode is currently in the ${productionStatus} stage.`,
      action: "edit",
      button: "Quick edit",
      tone: "normal",
    };
  }
  return {
    label: "Complete episode setup",
    reason: "Confirm the title, topic, owner, and production stage.",
    action: "form",
    button: "Open full editor",
    tone: "normal",
  };
}

function renderEpisodes(episodes, totalCount, episodeNumberMap) {
  episodeList.innerHTML = "";
  updateResultsMeta(
    episodeResultsMeta,
    episodes.length,
    totalCount,
    "",
    activeProductionStage
      ? `Production stage: ${productionStageLabel(activeProductionStage)}. Select the stage again or use Clear stage to return to the full list.`
      : "Use search, category, year, or status filters to focus the planning queue."
  );

  const visibleEpisodes = episodes.slice(0, visibleEpisodeCount);
  if (!episodes.length) {
    episodeList.innerHTML = totalCount
      ? "<p class='guest-summary'>No episodes match the current planning controls.</p>"
      : "<p class='guest-summary'>No episodes tracked yet. Add or import one from the planning tools above.</p>";
    episodeLoadMoreButton.classList.add("hidden");
    return;
  }

  visibleEpisodes.forEach((episode) => {
    const isReleased = normalizeText(episode.release_status) === "released";
    const isScheduled = normalizeText(episode.release_status) === "scheduled";
    const episodeNumberLabel = getEpisodeNumberLabel(episode, episodeNumberMap);
    const hasEmail = Boolean(episode.guest_email);
    const hasShowNotes = Boolean(normalizeText(episode.show_notes_url));
    const hasFilesLink = Boolean(normalizeText(episode.release_files_url));
    const releaseEmailReady = hasEmail && isReleased && hasShowNotes && hasFilesLink;
    const releaseActionLabel = releaseEmailReady ? "Send Release Email" : "Prepare Release Email";
    const releaseTone = isReleased ? "success" : isScheduled ? "pending" : "warning";
    const nextAction = deriveEpisodeNextAction(episode);
    const card = document.createElement("article");
    card.className = "operations-card";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h3>${escapeHtml(episode.episode_title || "Untitled episode")}</h3>
          <p>${escapeHtml(episode.guest_name || "Guest not set")}</p>
        </div>
        <div class="card-status-chips">
          <span class="status-chip ${releaseTone}">${escapeHtml(episode.release_status || "unplanned")}</span>
          <span class="status-chip">${escapeHtml(episode.production_status || "idea")}</span>
          <span class="status-chip">${escapeHtml(episode.promotion_status || "unknown")}</span>
        </div>
      </div>
      ${renderEpisodeBadges(episode)}
      <div class="episode-card-summary">
        <span>${episodeNumberLabel}</span>
        <span>Category: ${escapeHtml(episode.category || "Not set")}</span>
        <span>Release: ${formatDateTime(episode.release_date)}</span>
        <span>Owner: ${escapeHtml(episode.owner || "Unassigned")}</span>
        <span>Readiness: ${episode.promotion_readiness?.score ?? 0}/100</span>
      </div>
      <div class="episode-next-action ${escapeHtml(nextAction.tone)}">
        <div>
          <span class="insight-label">Next action</span>
          <h4>${escapeHtml(nextAction.label)}</h4>
          <p>${escapeHtml(nextAction.reason)}</p>
        </div>
        <button type="button" class="primary-button" data-episode-primary-action="${escapeHtml(nextAction.action)}">${escapeHtml(nextAction.button)}</button>
      </div>
      <details class="episode-card-disclosure">
        <summary>Details, evidence, and all actions</summary>
        <div class="operations-meta">
          <span>Published title: ${escapeHtml(episode.published_title || "Not set")}</span>
          <span>Topic: ${escapeHtml(episode.topic || "Not set")}</span>
          <span>Email: ${renderLinkedValue(episode.guest_email)}</span>
          <span>Website: ${renderLinkedValue(episode.website)}</span>
          <span>Interviewed: ${formatDateTime(episode.interview_date)}</span>
          <span>Disposition: ${escapeHtml(episode.editorial_disposition || "active")}</span>
          <span>Priority: ${episode.priority_score ?? 0}</span>
          <span>Show Notes: ${renderLinkedValue(episode.show_notes_url, "Missing")}</span>
          <span>Files: ${renderLinkedValue(episode.release_files_url, "Missing")}</span>
          <span>Transcript: ${transcriptStatusLabel(episode)}</span>
          <span>Source: ${escapeHtml(episode.source_file_name || "Manual entry")}</span>
        </div>
        ${renderPromoReadiness(episode.promotion_readiness)}
        ${renderAiSchedulingCopilot(episode.ai_copilot)}
        ${renderMonthlyAngleDecision(episode)}
        ${renderGuestResearchCopilot(episode.guest_research)}
        ${renderCopyAssist(episode.copy_assist)}
        <div class="context-links">
          <a class="context-link" href="${buildScopedLink("/dashboard", episode.guest_name || episode.guest_email)}">View Guest</a>
          <a class="context-link" href="${buildScopedLink("/operations", episode.guest_name || episode.guest_email)}">View Interview Ops</a>
        </div>
        <div class="operations-actions">
          <div class="action-group">
            <span class="action-group-label">Episode workflow</span>
            <button type="button" class="secondary-button" data-episode-action="edit">${activeEpisodeEditorId === episode.id ? "Hide Quick Edit" : "Quick Edit"}</button>
            <button type="button" class="ghost-button" data-episode-action="form">Open Full Editor</button>
            <button type="button" class="ghost-button" data-episode-action="activity">Activity</button>
            <button type="button" class="ghost-button" data-episode-action="refresh">Refresh</button>
            ${isScheduled && normalizeText(episode.production_status) === "ready" && normalizeText(episode.promotion_status) === "ready" ? `<button type="button" class="primary-button" data-episode-action="release">Mark Released</button>` : ""}
            ${!isReleased ? `<button type="button" class="ghost-button" data-episode-action="accelerate">Accelerate</button>` : ""}
            <button type="button" class="ghost-button" data-episode-action="hold">Hold</button>
            <button type="button" class="ghost-button" data-episode-action="archive">Archive</button>
            <button type="button" class="ghost-button" data-episode-action="retire">Retire</button>
            ${!isReleased ? `${!isScheduled ? `<button type="button" class="secondary-button" data-episode-action="schedule">Schedule for Release</button>` : `<button type="button" class="secondary-button" data-episode-action="reschedule">Change Release Date</button><button type="button" class="ghost-button" data-episode-action="unschedule">Unschedule</button>`}` : ""}
          </div>
          <div class="action-group">
            <span class="action-group-label">Guest communication</span>
            <button type="button" class="ghost-button" data-episode-action="preview-appreciation" ${hasEmail ? "" : "disabled"}>Preview Thank You</button>
            <button type="button" class="secondary-button" data-episode-action="send-appreciation" ${hasEmail ? "" : "disabled"}>Send Thank You</button>
            <button type="button" class="ghost-button" data-episode-action="preview-release-email" ${hasEmail ? "" : "disabled"}>Preview Release Email</button>
            <button type="button" class="secondary-button" data-episode-action="send-release-email" ${hasEmail ? "" : "disabled"}>${releaseActionLabel}</button>
            <button type="button" class="ghost-button danger-button" data-episode-action="delete">Delete</button>
          </div>
        </div>
      </details>
      <div class="card-action-feedback">${activeEpisodeActionFeedback.id === episode.id ? actionFeedbackMarkup(activeEpisodeActionFeedback) : ""}</div>
      <div class="operations-preview hidden" data-episode-appreciation-preview></div>
      <div class="operations-preview hidden" data-episode-release-preview></div>
      <div class="inline-editor hidden" data-episode-editor></div>
    `;

    const editButton = card.querySelector("[data-episode-action='edit']");
    const formButton = card.querySelector("[data-episode-action='form']");
    const activityButton = card.querySelector("[data-episode-action='activity']");
    const refreshButton = card.querySelector("[data-episode-action='refresh']");
    const releaseButton = card.querySelector("[data-episode-action='release']");
    const accelerateButton = card.querySelector("[data-episode-action='accelerate']");
    const dispositionButtons = Array.from(card.querySelectorAll("[data-episode-action='hold'], [data-episode-action='archive'], [data-episode-action='retire']"));
    const scheduleButton = card.querySelector("[data-episode-action='schedule']");
    const rescheduleButton = card.querySelector("[data-episode-action='reschedule']");
    const unscheduleButton = card.querySelector("[data-episode-action='unschedule']");
    const previewAppreciationButton = card.querySelector("[data-episode-action='preview-appreciation']");
    const sendAppreciationButton = card.querySelector("[data-episode-action='send-appreciation']");
    const previewReleaseButton = card.querySelector("[data-episode-action='preview-release-email']");
    const sendReleaseButton = card.querySelector("[data-episode-action='send-release-email']");
    const deleteButton = card.querySelector("[data-episode-action='delete']");
    const primaryActionButton = card.querySelector("[data-episode-primary-action]");
    const editorNode = card.querySelector("[data-episode-editor]");
    const actionFeedbackNode = card.querySelector(".card-action-feedback");
    const appreciationPreviewNode = card.querySelector("[data-episode-appreciation-preview]");
    const releasePreviewNode = card.querySelector("[data-episode-release-preview]");
    editButton.addEventListener("click", async () => {
      if (activeEpisodeEditorId === episode.id) {
        activeEpisodeEditorId = null;
        renderPlanning();
        return;
      }
      activeEpisodeEditorId = episode.id;
      if (episode.transcript_omitted) {
        activeEpisodeFeedback = { id: episode.id, text: "Loading full episode details...", tone: "pending" };
        renderPlanning();
        try {
          await hydrateEpisodeForEditing(episode);
        } catch (error) {
          activeEpisodeFeedback = { id: episode.id, text: error.message, tone: "error" };
        }
      }
      renderPlanning();
    });
    formButton.addEventListener("click", async () => {
      const fullEpisode = await hydrateEpisodeForEditing(episode);
      loadEpisodeIntoForm(fullEpisode);
      setMessage(
        episodeMessage,
        `Opened ${episode.episode_title || episode.guest_name || "episode"} in the full editor.`,
        "success",
      );
    });
    activityButton.addEventListener("click", async () => {
      showAIModal(`Activity: ${episode.episode_title || episode.guest_name || "Episode"}`, "<p class='loading'>Loading activity…</p>");
      try {
        const activity = await fetchJSON(`/api/audit-events?entity_type=episode&entity_id=${encodeURIComponent(episode.id)}`);
        showAIModal(`Activity: ${episode.episode_title || episode.guest_name || "Episode"}`, renderAuditTimeline(activity.events || []));
      } catch (error) {
        showAIModal("Activity unavailable", `<p class="error">${escapeHtml(error.message)}</p>`);
      }
    });
    refreshButton.addEventListener("click", () => loadPlanning({ forceRefresh: true }));
    primaryActionButton?.addEventListener("click", () => {
      const actionTargets = {
        edit: editButton,
        form: formButton,
        release: releaseButton,
        schedule: scheduleButton,
        reschedule: rescheduleButton,
      };
      actionTargets[primaryActionButton.dataset.episodePrimaryAction]?.click();
    });
    if (accelerateButton) accelerateButton.addEventListener("click", () => openScheduleModal(episode));
    if (releaseButton) {
      releaseButton.addEventListener("click", async () => {
        if (!confirmCriticalAction(`Mark ${episode.episode_title || "this episode"} as released?`)) return;
        try {
          const savedEpisode = await fetchJSON(`/api/episodes/${episode.id}`, {
            method: "POST",
            body: JSON.stringify({
              row_version: episode.row_version,
              release_status: "released",
              production_status: "released",
              promotion_status: "released",
            }),
          });
          replaceEpisodeInPayload(savedEpisode);
          renderPlanning();
          setMessage(episodeMessage, `${episode.episode_title || "Episode"} marked released.`, "success");
        } catch (error) {
          setMessage(episodeMessage, error.message, "error");
        }
      });
    }
    dispositionButtons.forEach((button) => {
      button.addEventListener("click", async () => {
        const disposition = button.dataset.episodeAction;
        if (!confirmCriticalAction(`${disposition[0].toUpperCase()}${disposition.slice(1)} ${episode.episode_title || "this episode"}?`)) return;
        try {
          const savedEpisode = await fetchJSON(`/api/episodes/${episode.id}`, {
            method: "POST",
            body: JSON.stringify({row_version: episode.row_version, editorial_disposition: disposition}),
          });
          replaceEpisodeInPayload(savedEpisode);
          renderPlanning();
          setMessage(episodeMessage, `${episode.episode_title || "Episode"} disposition set to ${disposition}.`, "success");
        } catch (error) {
          setMessage(episodeMessage, error.message, "error");
        }
      });
    });
    if (scheduleButton) {
      scheduleButton.addEventListener("click", () => {
        openScheduleModal(episode);
      });
    }
    if (rescheduleButton) {
      rescheduleButton.addEventListener("click", () => {
        openScheduleModal(episode);
      });
    }
    if (unscheduleButton) {
      unscheduleButton.addEventListener("click", async () => {
        if (!confirmCriticalAction(`Unschedule ${episode.episode_title || "this episode"}?`)) {
          return;
        }
        unscheduleButton.disabled = true;
        unscheduleButton.textContent = "Unscheduling...";
        activeEpisodeActionFeedback = {
          id: episode.id,
          text: `Unscheduling ${episode.episode_title || "episode"}...`,
          tone: "pending",
        };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
        try {
          const savedEpisode = await fetchJSON(`/api/episodes/${episode.id}`, {
            method: "POST",
            body: JSON.stringify({
              release_status: "unplanned",
              release_date: null,
            }),
          });
          replaceEpisodeInPayload(savedEpisode);
          activeEpisodeActionFeedback = {
            id: episode.id,
            text: `Unscheduled ${episode.episode_title || "episode"}.`,
            tone: "success",
          };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
          setMessage(episodeMessage, `Unscheduled ${episode.episode_title || "episode"}.`, "success");
          renderPlanning();
          refreshPlanningQuietly();
        } catch (error) {
          activeEpisodeActionFeedback = { id: episode.id, text: error.message, tone: "error" };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
          setMessage(episodeMessage, error.message, "error");
          unscheduleButton.disabled = false;
          unscheduleButton.textContent = "Unschedule";
        }
      });
    }
    if (activeEpisodeEditorId === episode.id) {
      editorNode.classList.remove("hidden");
      renderEpisodeInlineEditor(editorNode, episode);
    }
    if (previewAppreciationButton) {
      previewAppreciationButton.addEventListener("click", async () => {
        if (!episode.guest_email) {
          setMessage(episodeMessage, "This episode does not have a guest email yet.", "error");
          return;
        }

        previewAppreciationButton.disabled = true;
        previewAppreciationButton.textContent = "Loading...";
        activeEpisodeActionFeedback = {
          id: episode.id,
          text: `Loading thank-you preview for ${episode.guest_name || "guest"}...`,
          tone: "pending",
        };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
        try {
          const preview = await fetchJSON(`/api/episodes/${episode.id}/appreciation-template`);
          appreciationPreviewNode.classList.remove("hidden");
          appreciationPreviewNode.innerHTML = `
            <h4>${escapeHtml(preview.subject)}</h4>
            <p>To: ${renderLinkedValue(episode.guest_email)}</p>
            <pre>${escapeHtml(preview.body)}</pre>
          `;
          releasePreviewNode.classList.add("hidden");
          releasePreviewNode.innerHTML = "";
          activeEpisodeActionFeedback = {
            id: episode.id,
            text: `Thank-you preview ready for ${episode.guest_name || "guest"}.`,
            tone: "success",
          };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
        } catch (error) {
          activeEpisodeActionFeedback = { id: episode.id, text: error.message, tone: "error" };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
          setMessage(episodeMessage, error.message, "error");
        } finally {
          previewAppreciationButton.disabled = false;
          previewAppreciationButton.textContent = "Preview Thank You";
        }
      });
    }
    if (sendAppreciationButton) {
      sendAppreciationButton.addEventListener("click", async () => {
        if (!episode.guest_email) {
          setMessage(episodeMessage, "This episode does not have a guest email yet.", "error");
          return;
        }
        if (!confirmCriticalAction(`Send the thank-you email to ${episode.guest_name || episode.guest_email || "this guest"} now?`)) {
          return;
        }

        sendAppreciationButton.disabled = true;
        sendAppreciationButton.textContent = "Sending...";
        activeEpisodeActionFeedback = {
          id: episode.id,
          text: `Sending thank-you email to ${episode.guest_name || episode.guest_email}...`,
          tone: "pending",
        };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
        try {
          await fetchJSON(`/api/episodes/${episode.id}/send-appreciation`, {
            method: "POST",
            body: JSON.stringify({}),
          });
          sendAppreciationButton.disabled = false;
          sendAppreciationButton.textContent = "Send Thank You";
          appreciationPreviewNode.classList.remove("hidden");
          appreciationPreviewNode.innerHTML = `<p class="composer-feedback success">Thank-you email sent to ${escapeHtml(episode.guest_name || episode.guest_email)}.</p>`;
          releasePreviewNode.classList.add("hidden");
          releasePreviewNode.innerHTML = "";
          activeEpisodeActionFeedback = {
            id: episode.id,
            text: `Thank-you email sent to ${episode.guest_name || episode.guest_email}.`,
            tone: "success",
          };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
          setMessage(
            episodeMessage,
            `Thank-you email sent to ${episode.guest_name || episode.guest_email}. Next, you can keep shaping the release plan here whenever the episode is ready.`,
            "success",
          );
        } catch (error) {
          activeEpisodeActionFeedback = { id: episode.id, text: error.message, tone: "error" };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
          setMessage(episodeMessage, error.message, "error");
          sendAppreciationButton.disabled = false;
          sendAppreciationButton.textContent = "Send Thank You";
        }
      });
    }
    if (previewReleaseButton) {
      previewReleaseButton.addEventListener("click", async () => {
        if (!episode.guest_email) {
          setMessage(episodeMessage, "This episode does not have a guest email yet.", "error");
          return;
        }

        previewReleaseButton.disabled = true;
        previewReleaseButton.textContent = "Loading...";
        activeEpisodeActionFeedback = {
          id: episode.id,
          text: `Loading release email preview for ${episode.guest_name || "guest"}...`,
          tone: "pending",
        };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
        try {
          const preview = await fetchJSON(`/api/episodes/${episode.id}/release-email-template`);
          renderReleaseComposer(releasePreviewNode, episode, preview);
          appreciationPreviewNode.classList.add("hidden");
          appreciationPreviewNode.innerHTML = "";
          activeEpisodeActionFeedback = {
            id: episode.id,
            text: `Release email ready to review and edit for ${episode.guest_name || "guest"}.`,
            tone: "success",
          };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
        } catch (error) {
          activeEpisodeActionFeedback = { id: episode.id, text: error.message, tone: "error" };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
          setMessage(episodeMessage, error.message, "error");
        } finally {
          previewReleaseButton.disabled = false;
          previewReleaseButton.textContent = "Preview Release Email";
        }
      });
    }
    if (sendReleaseButton) {
      sendReleaseButton.addEventListener("click", async () => {
        if (!episode.guest_email) {
          setMessage(episodeMessage, "This episode does not have a guest email yet.", "error");
          return;
        }

        if (!releaseEmailReady) {
          setPlanningTab("release_planning");
          const fullEpisode = await hydrateEpisodeForEditing(episode);
          loadEpisodeIntoForm(fullEpisode);
          if (!isReleased) {
            setMessage(
              episodeMessage,
              "Mark the episode as released first, then add the show notes link and files link before sending the release email.",
              "pending",
            );
            episodeForm.elements.release_status.focus({ preventScroll: true });
          } else if (!hasShowNotes) {
            setMessage(
              episodeMessage,
              "Add the show notes or blogpost link first, then you can send the release email from here.",
              "pending",
            );
            episodeForm.elements.show_notes_url.focus({ preventScroll: true });
          } else {
            setMessage(
              episodeMessage,
              "Add the files link first, then you can send the release email from here.",
              "pending",
            );
            episodeForm.elements.release_files_url.focus({ preventScroll: true });
          }
          return;
        }
        if (!confirmCriticalAction(`Send the release email to ${episode.guest_name || episode.guest_email || "this guest"} now?`)) {
          return;
        }

        sendReleaseButton.disabled = true;
        sendReleaseButton.textContent = "Sending...";
        activeEpisodeActionFeedback = {
          id: episode.id,
          text: `Sending release email to ${episode.guest_name || episode.guest_email}...`,
          tone: "pending",
        };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
        try {
          await fetchJSON(`/api/episodes/${episode.id}/send-release-email`, {
            method: "POST",
            body: JSON.stringify({}),
          });
          sendReleaseButton.disabled = false;
          sendReleaseButton.textContent = "Send Release Email";
          releasePreviewNode.classList.remove("hidden");
          releasePreviewNode.innerHTML = `<p class="composer-feedback success">Release email sent to ${escapeHtml(episode.guest_name || episode.guest_email)}.</p>`;
          appreciationPreviewNode.classList.add("hidden");
          appreciationPreviewNode.innerHTML = "";
          activeEpisodeActionFeedback = {
            id: episode.id,
            text: `Release email sent to ${episode.guest_name || episode.guest_email}.`,
            tone: "success",
          };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
          setMessage(
            episodeMessage,
            `Release email sent to ${episode.guest_name || episode.guest_email}. The published follow-up is complete for this episode.`,
            "success",
          );
          await loadPlanning();
        } catch (error) {
          activeEpisodeActionFeedback = { id: episode.id, text: error.message, tone: "error" };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
          setMessage(episodeMessage, error.message, "error");
          sendReleaseButton.disabled = false;
          sendReleaseButton.textContent = "Send Release Email";
        }
      });
    }
    deleteButton.addEventListener("click", async () => {
      const label = episode.episode_title || episode.guest_name || "this episode";
      const typedLabel = promptExactMatch(label, "delete this episode");
      if (typedLabel === null) {
        return;
      }
      if (typedLabel === false) {
        setMessage(episodeMessage, `Deletion cancelled. Type ${label} exactly to remove this episode.`, "error");
        return;
      }

      deleteButton.disabled = true;
      deleteButton.textContent = "Deleting...";
      activeEpisodeActionFeedback = { id: episode.id, text: `Deleting ${label}...`, tone: "pending" };
      actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
      try {
        const savedEpisode = await fetchJSON(`/api/episodes/${episode.id}`, {
          method: "DELETE",
          body: JSON.stringify({ confirm_label: typedLabel }),
        });
        latestPlanningPayload.episodes = (latestPlanningPayload.episodes || []).filter((item) => String(item.id || "") !== String(episode.id));
        latestPlanningPayload.recommendations = (latestPlanningPayload.recommendations || []).filter((item) => String(item.id || "") !== String(episode.id));
        activeEpisodeActionFeedback = { id: episode.id, text: `${label} deleted.`, tone: "success" };
        setMessage(episodeMessage, `Deleted ${label}.`, "success");
        renderPlanning();
        refreshPlanningQuietly();
      } catch (error) {
        activeEpisodeActionFeedback = { id: episode.id, text: error.message, tone: "error" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
        setMessage(episodeMessage, error.message, "error");
        deleteButton.disabled = false;
        deleteButton.textContent = "Delete";
      }
    });

    episodeList.appendChild(card);
  });

  episodeLoadMoreButton.classList.toggle("hidden", visibleEpisodes.length >= episodes.length);
  if (!episodeLoadMoreButton.classList.contains("hidden")) {
    episodeLoadMoreButton.textContent = `Load More Episodes (${episodes.length - visibleEpisodes.length} remaining)`;
  }
}

function renderRecommendations(recommendations, totalCount, episodeNumberMap) {
  recommendationList.innerHTML = "";
  updateResultsMeta(
    recommendationResultsMeta,
    recommendations.length,
    totalCount,
    "Import the yearly release CSVs and the Not Yet Released queue to generate recommendations.",
    "Adjust search, category, or sort to inspect the strongest release candidates."
  );

  const visibleRecommendations = recommendations.slice(0, visibleRecommendationCount);
  if (!recommendations.length) {
    recommendationList.innerHTML = totalCount
      ? "<p class='guest-summary'>No recommendations match the current controls.</p>"
      : "<p class='guest-summary'>Import the yearly release CSVs and the Not Yet Released queue to generate recommendations.</p>";
    recommendationLoadMoreButton.classList.add("hidden");
    return;
  }

  visibleRecommendations.forEach((episode, index) => {
    const signals = deriveRecommendationSignals(episode);
    const insights = splitRecommendationInsights(episode.recommendation_reason);
    const episodeNumberLabel = getEpisodeNumberLabel(episode, episodeNumberMap);
    const card = document.createElement("article");
    card.className = "operations-card recommendation-card";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h3>#${index + 1} ${escapeHtml(episode.episode_title || episode.topic || "Untitled episode")}</h3>
          <p>${escapeHtml(episode.guest_name || "Guest not set")}</p>
        </div>
        <div class="card-status-chips">
          <span class="status-chip pending">Score ${episode.priority_score ?? 0}</span>
          <span class="status-chip">${escapeHtml(episode.production_status || "idea")}</span>
          <span class="status-chip">${escapeHtml(episode.promotion_status || "unknown")}</span>
        </div>
      </div>
      <div class="recommendation-decision">
        <div>
          <span class="insight-label">Recommended release decision</span>
          <h4>${formatDateTime(episode.recommended_release_date)}</h4>
          <p>${escapeHtml(insights.summary || "This is the strongest available fit for the next release slot.")}</p>
        </div>
        <div class="recommendation-primary-actions">
          <button type="button" class="primary-button" data-recommendation-action="schedule">Use Recommended Slot</button>
          <button type="button" class="secondary-button" data-recommendation-action="edit">Review in editor</button>
        </div>
      </div>
      ${signals.length ? `<div class="signal-list">${signals.map((signal) => `<span class="signal-chip ${signal.tone}">${signal.label}</span>`).join("")}</div>` : ""}
      <details class="recommendation-evidence">
        <summary>Why this recommendation</summary>
        <div class="operations-meta">
          <span>${episodeNumberLabel}</span>
          <span>Category: ${escapeHtml(episode.category || "Not set")}</span>
          <span>Interviewed: ${formatDateTime(episode.interview_date)}</span>
          <span>Production: ${escapeHtml(episode.production_status || "idea")}</span>
          <span>Promo: ${escapeHtml(episode.promotion_status || "unknown")}</span>
        </div>
        <div class="operations-preview">
        ${insights.strengths.length ? `<div class="insight-stack"><strong class="insight-label">Why now</strong><ul>${insights.strengths.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
        ${insights.cautions.length ? `<div class="insight-stack caution"><strong class="insight-label">Watchouts</strong><ul>${insights.cautions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
        </div>
        ${episode.why_now?.length ? `<div class="operations-preview"><strong class="insight-label">Why this next</strong><ul>${episode.why_now.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
        ${episode.watchouts?.length ? `<div class="operations-preview"><strong class="insight-label">Why not now</strong><ul>${episode.watchouts.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
        ${renderSeasonalFit(episode.seasonal_fit)}
        ${renderAiSchedulingCopilot(episode.ai_copilot)}
        ${renderMonthlyAngleDecision(episode, { always: true })}
        ${episode.sequence_warnings?.length ? `<div class="operations-preview"><strong class="insight-label">Sequence warnings</strong><ul>${episode.sequence_warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
        ${episode.archive_overlap?.message ? `<div class="operations-preview"><strong class="insight-label">Archive overlap</strong><p>${escapeHtml(episode.archive_overlap.message)}</p></div>` : ""}
        ${episode.topic_cluster_warning?.message ? `<div class="operations-preview"><strong class="insight-label">Recent topic cluster</strong><p>${escapeHtml(episode.topic_cluster_warning.message)}</p></div>` : ""}
        ${renderPromoReadiness(episode.promotion_readiness)}
        ${renderGuestResearchCopilot(episode.guest_research)}
        ${renderCopyAssist(episode.copy_assist)}
        <div class="context-links">
          <a class="context-link" href="${buildScopedLink("/dashboard", episode.guest_name || episode.guest_email)}">View Guest</a>
          <a class="context-link" href="${buildScopedLink("/operations", episode.guest_name || episode.guest_email)}">View Interview Ops</a>
        </div>
        <div class="operations-actions">
          <div class="action-group">
            <span class="action-group-label">Monthly Angle Review</span>
            <button type="button" class="ghost-button" data-recommendation-action="pin-angle">Pin Angle</button>
            <button type="button" class="ghost-button" data-recommendation-action="reject-angle">Reject Angle</button>
            <button type="button" class="ghost-button" data-recommendation-action="clear-angle">Clear Angle Review</button>
          </div>
        </div>
      </details>
      <div class="recommendation-secondary-actions">
        <details class="recommendation-reject-control action-group">
          <summary class="ghost-button">Reject recommendation</summary>
          <form class="recommendation-reject-form">
            <label>
              Why should this stop being recommended?
              <select name="reason" required>
                <option value="">Choose a reason</option>
                <option value="Timing or topic is not suitable">Timing or topic is not suitable</option>
                <option value="Too similar to a recent episode">Too similar to a recent episode</option>
                <option value="Not release-ready or missing assets">Not release-ready or missing assets</option>
                <option value="Editorial mismatch">Editorial mismatch</option>
                <option value="Duplicate or already covered">Duplicate or already covered</option>
                <option value="Other editorial reason">Other editorial reason</option>
              </select>
            </label>
            <label>
              Note <span class="field-hint">(optional)</span>
              <textarea name="note" rows="2" maxlength="500" placeholder="Add context for future review"></textarea>
            </label>
            <p class="field-hint">This hides the episode from future scheduling recommendations and AI review until restored.</p>
            <button type="submit" class="secondary-button danger-button">Confirm rejection</button>
          </form>
        </details>
      </div>
      <div class="card-action-feedback">${activeEpisodeActionFeedback.id === episode.id ? actionFeedbackMarkup(activeEpisodeActionFeedback) : ""}</div>
    `;
    const scheduleButton = card.querySelector("[data-recommendation-action='schedule']");
    const editButton = card.querySelector("[data-recommendation-action='edit']");
    const pinAngleButton = card.querySelector("[data-recommendation-action='pin-angle']");
    const rejectAngleButton = card.querySelector("[data-recommendation-action='reject-angle']");
    const clearAngleButton = card.querySelector("[data-recommendation-action='clear-angle']");
    const rejectRecommendationForm = card.querySelector(".recommendation-reject-form");
    const actionFeedbackNode = card.querySelector(".card-action-feedback");
    scheduleButton.addEventListener("click", async () => {
      scheduleButton.disabled = true;
      scheduleButton.textContent = "Scheduling...";
      activeEpisodeActionFeedback = {
        id: episode.id,
        text: `Scheduling ${episode.episode_title || episode.guest_name || "episode"}...`,
        tone: "pending",
      };
      actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
      try {
        const payload = {
          ...episode,
          release_date: formatDateForDateTimeInput(episode.recommended_release_date),
          release_status: "scheduled",
          enforce_readiness: true,
          priority_score: clampPriorityScore(
            episode.priority_score,
            suggestPriorityScoreForEpisode({
              release_status: "scheduled",
              production_status: episode.production_status,
              promotion_status: episode.promotion_status,
            })
          ),
        };
        const savedEpisode = await fetchJSON(`/api/episodes/${episode.id}`, {
          method: "POST",
          body: JSON.stringify(cleanEpisodePayloadForSave(payload)),
        });
        replaceEpisodeInPayload(savedEpisode);
        activeEpisodeActionFeedback = {
          id: episode.id,
          text: `Scheduled for ${formatDateTime(episode.recommended_release_date)}.`,
          tone: "success",
        };
        setMessage(
          episodeMessage,
          `Scheduled ${episode.episode_title || episode.guest_name || "episode"} for ${formatDateTime(episode.recommended_release_date)}.`,
          "success",
        );
        renderPlanning();
        refreshPlanningQuietly();
      } catch (error) {
        activeEpisodeActionFeedback = { id: episode.id, text: error.message, tone: "error" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
        setMessage(episodeMessage, error.message, "error");
        scheduleButton.disabled = false;
        scheduleButton.textContent = "Use Recommended Slot";
      }
    });
    editButton.addEventListener("click", async () => {
      setPlanningTab("release_planning");
      const fullEpisode = await hydrateEpisodeForEditing(episode);
      loadEpisodeIntoForm(fullEpisode, {
        releaseDate: episode.recommended_release_date,
        releaseStatus: "scheduled",
      });
      setMessage(
        episodeMessage,
        `Loaded ${episode.episode_title || episode.guest_name || "episode"} into the release form with the recommended slot ready for review.`,
        "success",
      );
    });
    rejectRecommendationForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submitButton = rejectRecommendationForm.querySelector("button[type='submit']");
      const formData = new FormData(rejectRecommendationForm);
      const selectedReason = String(formData.get("reason") || "").trim();
      const note = String(formData.get("note") || "").trim();
      if (!selectedReason) return;
      const reason = note ? `${selectedReason} — ${note}` : selectedReason;
      submitButton.disabled = true;
      submitButton.textContent = "Rejecting...";
      try {
        const feedback = await fetchJSON(`/api/episodes/${episode.id}/recommendation-feedback`, {
          method: "POST",
          body: JSON.stringify({
            action: "rejected",
            reason,
            idempotency_key: recommendationRequestKey(),
            recommendation: {
              recommended_release_date: episode.recommended_release_date,
              priority_score: episode.priority_score,
              recommendation_reason: episode.recommendation_reason,
            },
          }),
        });
        latestPlanningPayload.recommendations = (latestPlanningPayload.recommendations || [])
          .filter((item) => String(item.id) !== String(episode.id));
        latestPlanningPayload.rejected_recommendations = [
          {
            ...episode,
            recommendation_feedback_state: feedback.state,
            recommendation_feedback_reason: feedback.reason,
            recommendation_feedback_at: feedback.created_at,
            recommendation_feedback_actor: feedback.actor,
          },
          ...(latestPlanningPayload.rejected_recommendations || [])
            .filter((item) => String(item.id) !== String(episode.id)),
        ];
        setMessage(episodeMessage, `Rejected ${episode.episode_title || episode.guest_name || "episode"}; it will stay out of recommendations until restored.`, "success");
        renderPlanning();
      } catch (error) {
        submitButton.disabled = false;
        submitButton.textContent = "Confirm rejection";
        setMessage(episodeMessage, error.message, "error");
      }
    });
    const setMonthlyAngleDecision = async (state) => {
      const theme = state ? getRecommendationMonthlyAngle(episode) : "";
      const actingButtons = [pinAngleButton, rejectAngleButton, clearAngleButton].filter(Boolean);
      actingButtons.forEach((button) => {
        button.disabled = true;
      });
      activeEpisodeActionFeedback = {
        id: episode.id,
        text: state ? `${state === "pinned" ? "Pinning" : "Rejecting"} monthly angle for ${episode.guest_name || "episode"}...` : `Clearing monthly angle review for ${episode.guest_name || "episode"}...`,
        tone: "pending",
      };
      actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
      try {
        const savedEpisode = await fetchJSON(`/api/episodes/${episode.id}`, {
          method: "POST",
          body: JSON.stringify({
            ai_monthly_angle_state: state,
            ai_monthly_angle_theme: theme,
          }),
        });
        replaceEpisodeInPayload(savedEpisode);
        activeEpisodeActionFeedback = {
          id: episode.id,
          text: state ? `Monthly angle ${state} for ${episode.guest_name || "episode"}.` : `Monthly angle review cleared for ${episode.guest_name || "episode"}.`,
          tone: "success",
        };
        setMessage(
          episodeMessage,
          state ? `${state === "pinned" ? "Pinned" : "Rejected"} the monthly angle for ${episode.guest_name || "episode"}.` : `Cleared the monthly angle review for ${episode.guest_name || "episode"}.`,
          "success",
        );
        renderPlanning();
      } catch (error) {
        activeEpisodeActionFeedback = { id: episode.id, text: error.message, tone: "error" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
        setMessage(episodeMessage, error.message, "error");
        actingButtons.forEach((button) => {
          button.disabled = false;
        });
      }
    };
    pinAngleButton?.addEventListener("click", async () => {
      await setMonthlyAngleDecision("pinned");
    });
    rejectAngleButton?.addEventListener("click", async () => {
      await setMonthlyAngleDecision("rejected");
    });
    clearAngleButton?.addEventListener("click", async () => {
      await setMonthlyAngleDecision("");
    });
    recommendationList.appendChild(card);
  });

  recommendationLoadMoreButton.classList.toggle("hidden", visibleRecommendations.length >= recommendations.length);
  if (!recommendationLoadMoreButton.classList.contains("hidden")) {
    recommendationLoadMoreButton.textContent = `Load More Recommendations (${recommendations.length - visibleRecommendations.length} remaining)`;
  }
}

function recommendationRequestKey() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `recommendation-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function renderRejectedRecommendations(episodes) {
  if (!rejectedRecommendationsPanel || !rejectedRecommendationList || !rejectedRecommendationsCount) return;
  const rejected = Array.isArray(episodes) ? episodes : [];
  rejectedRecommendationsCount.textContent = String(rejected.length);
  rejectedRecommendationsPanel.classList.toggle("hidden", rejected.length === 0);
  rejectedRecommendationList.innerHTML = "";
  rejected.forEach((episode) => {
    const row = document.createElement("article");
    row.className = "rejected-recommendation-row";
    row.innerHTML = `
      <div>
        <h3>${escapeHtml(episode.episode_title || episode.topic || "Untitled episode")}</h3>
        <p>${escapeHtml(episode.guest_name || "Guest not set")} · ${escapeHtml(episode.category || "Category not set")}</p>
        <p><strong>Reason:</strong> ${escapeHtml(episode.recommendation_feedback_reason || "No reason recorded")}</p>
        <small>Rejected ${escapeHtml(formatDateTime(episode.recommendation_feedback_at))}${episode.recommendation_feedback_actor ? ` by ${escapeHtml(episode.recommendation_feedback_actor)}` : ""}</small>
      </div>
      <button type="button" class="secondary-button" data-restore-recommendation>Restore recommendation</button>
    `;
    row.querySelector("[data-restore-recommendation]")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      button.textContent = "Restoring...";
      try {
        await fetchJSON(`/api/episodes/${episode.id}/recommendation-feedback`, {
          method: "POST",
          body: JSON.stringify({
            action: "restored",
            reason: "Restored by editor",
            idempotency_key: recommendationRequestKey(),
          }),
        });
        latestPlanningPayload.rejected_recommendations = rejected.filter((item) => String(item.id) !== String(episode.id));
        setMessage(episodeMessage, `Restored ${episode.episode_title || episode.guest_name || "episode"} to scheduling consideration.`, "success");
        renderPlanning();
        await refreshPlanningQuietly();
      } catch (error) {
        button.disabled = false;
        button.textContent = "Restore recommendation";
        setMessage(episodeMessage, error.message, "error");
      }
    });
    rejectedRecommendationList.appendChild(row);
  });
}

function renderPlanning() {
  const episodes = latestPlanningPayload.episodes || [];
  const recommendations = latestPlanningPayload.recommendations || [];
  const categories = latestPlanningPayload.available_categories || [];
  const episodeNumberMap = buildEpisodeNumberMap(episodes, recommendations);

  window.PerformanceUtils?.renderActionQueue(
    workspaceActionQueue,
    latestPlanningPayload.action_queue,
    { activeDomain: "episode" },
  );

  updatePresetButtons(recommendationPresetButtons, activeRecommendationPreset, "recommendationPreset");
  updatePresetButtons(episodePresetButtons, activeEpisodePreset, "episodePreset");
  populatePlanningFilters(categories, episodes);
  renderTeamMemberOptions(planningTeamMembers, latestPlanningPayload.team_members);
  renderCategoryOptions(categories);
  renderWeeklySystemPanel(latestPlanningPayload.weekly_system);
  renderAiCopilotStatus(latestPlanningPayload.ai_copilot_status);
  renderReleaseWorkspace(episodes);
  renderRecommendations(filterRecommendations(recommendations), recommendations.length, episodeNumberMap);
  renderRejectedRecommendations(latestPlanningPayload.rejected_recommendations || []);
  renderEpisodes(filterEpisodes(episodes), episodes.length, episodeNumberMap);
}

function calendarDateKey(value) {
  const date = value instanceof Date ? value : parseDate(value);
  if (!date) return "";
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function episodeCalendarTone(episode) {
  const releaseStatus = normalizeText(episode.release_status);
  if (releaseStatus === "released") return "released";
  if (
    releaseStatus === "scheduled"
    && (
      normalizeText(episode.production_status) !== "ready"
      || normalizeText(episode.promotion_status) !== "ready"
    )
  ) return "risk";
  return "scheduled";
}

function closeEpisodeDetailsModal({ restoreFocus = true } = {}) {
  if (!episodeDetailsModal) return;
  episodeDetailsModal.classList.add("hidden");
  selectedCalendarEpisodeId = null;
  if (restoreFocus && calendarReturnFocus?.isConnected) calendarReturnFocus.focus();
  calendarReturnFocus = null;
}

function openEpisodeDetailsModal(episode, trigger) {
  if (!episodeDetailsModal || !episodeDetailsBody) return;
  selectedCalendarEpisodeId = Number(episode.id);
  calendarReturnFocus = trigger || null;
  const workingTitle = episode.working_title || episode.episode_title || "Untitled episode";
  episodeDetailsTitle.textContent = workingTitle;
  episodeDetailsBody.innerHTML = `
    <div class="episode-detail-status">
      <span class="status-chip ${episodeCalendarTone(episode)}">${escapeHtml(episode.release_status || "unplanned")}</span>
      <span class="status-chip">${escapeHtml(episode.production_status || "idea")}</span>
      <span class="status-chip">${escapeHtml(episode.promotion_status || "unknown")}</span>
    </div>
    <dl class="episode-detail-grid">
      <div><dt>Working title</dt><dd>${escapeHtml(workingTitle)}</dd></div>
      <div><dt>Published title</dt><dd>${escapeHtml(episode.published_title || "Not set")}</dd></div>
      <div><dt>Guest</dt><dd>${escapeHtml(episode.guest_name || "Not set")}</dd></div>
      <div><dt>Episode number</dt><dd>${escapeHtml(episode.legacy_episode_number || "TBD")}</dd></div>
      <div><dt>Release</dt><dd>${escapeHtml(formatDateTime(episode.release_date))}</dd></div>
      <div><dt>Owner</dt><dd>${escapeHtml(episode.owner || "Unassigned")}</dd></div>
      <div><dt>Category</dt><dd>${escapeHtml(episode.category || "Not set")}</dd></div>
      <div><dt>Transcript</dt><dd>${escapeHtml(transcriptStatusLabel(episode))}</dd></div>
      <div><dt>Show notes</dt><dd>${renderLinkedValue(episode.show_notes_url, "Missing")}</dd></div>
      <div><dt>Release files</dt><dd>${renderLinkedValue(episode.release_files_url, "Missing")}</dd></div>
    </dl>
  `;
  episodeDetailsModal.classList.remove("hidden");
  episodeDetailsClose.focus();
}

function renderReleaseCalendar(episodes) {
  if (!releaseCalendar) return;
  const monthStart = new Date(calendarCursor.getFullYear(), calendarCursor.getMonth(), 1);
  const gridStart = new Date(monthStart);
  gridStart.setDate(1 - gridStart.getDay());
  const todayKey = calendarDateKey(new Date());
  const eventsByDate = new Map();

  episodes
    .filter((episode) => ["scheduled", "released"].includes(normalizeText(episode.release_status)))
    .filter((episode) => parseDate(episode.release_date))
    .forEach((episode) => {
      const key = calendarDateKey(episode.release_date);
      if (!eventsByDate.has(key)) eventsByDate.set(key, []);
      eventsByDate.get(key).push(episode);
    });
  eventsByDate.forEach((items) => items.sort((left, right) => (
    parseDate(left.release_date) - parseDate(right.release_date)
    || Number(left.id || 0) - Number(right.id || 0)
  )));

  releaseCalendarTitle.textContent = monthStart.toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
  const weekdayLabels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    .map((label) => `<div class="calendar-weekday" role="columnheader">${label}</div>`)
    .join("");
  const dayCells = [];
  for (let offset = 0; offset < 42; offset += 1) {
    const date = new Date(gridStart);
    date.setDate(gridStart.getDate() + offset);
    const key = calendarDateKey(date);
    const isOutsideMonth = date.getMonth() !== monthStart.getMonth();
    const events = eventsByDate.get(key) || [];
    const dots = events.map((episode) => {
      const title = episode.working_title || episode.episode_title || "Untitled episode";
      const tone = episodeCalendarTone(episode);
      return `<button type="button" class="calendar-event-dot ${tone}" data-calendar-episode="${Number(episode.id)}" aria-label="${escapeHtml(`${title}, ${episode.release_status}, ${formatDateTime(episode.release_date)}`)}" title="${escapeHtml(title)}"></button>`;
    }).join("");
    dayCells.push(`
      <div class="calendar-day ${isOutsideMonth ? "outside-month" : ""} ${key === todayKey ? "today" : ""}" role="gridcell" aria-label="${escapeHtml(date.toLocaleDateString())}">
        <span class="calendar-day-number">${date.getDate()}</span>
        <div class="calendar-day-events">${dots}</div>
        ${events.length > 3 ? `<small>${events.length} releases</small>` : ""}
      </div>
    `);
  }
  releaseCalendar.innerHTML = `<div class="calendar-grid" role="grid" aria-label="${escapeHtml(releaseCalendarTitle.textContent)}">${weekdayLabels}${dayCells.join("")}</div>`;
  releaseCalendar.querySelectorAll("[data-calendar-episode]").forEach((button) => {
    button.addEventListener("click", () => {
      const episode = episodes.find((item) => Number(item.id) === Number(button.dataset.calendarEpisode));
      if (episode) openEpisodeDetailsModal(episode, button);
    });
  });
}

function getProductionStage(episode) {
  return window.PlanningSort.classifyProductionStage(episode);
}

function productionStageLabel(stageKey) {
  return PRODUCTION_RAIL_STAGES.find(([key]) => key === stageKey)?.[1] || "Production";
}

function renderProductionRail(episodes) {
  if (!productionRail) return;
  const stageCounts = new Map(PRODUCTION_RAIL_STAGES.map(([key]) => [key, 0]));
  episodes.forEach((episode) => {
    const stage = getProductionStage(episode);
    if (stageCounts.has(stage)) stageCounts.set(stage, stageCounts.get(stage) + 1);
  });
  productionRail.innerHTML = PRODUCTION_RAIL_STAGES.map(([key, label]) => {
    const selected = activeProductionStage === key;
    return `
      <button type="button" class="production-rail-stage ${selected ? "active" : ""}" data-production-stage="${key}" aria-pressed="${selected}">
        <span class="production-stage-marker" aria-hidden="true"></span>
        <strong>${stageCounts.get(key) || 0}</strong>
        <span>${escapeHtml(label)}</span>
      </button>
    `;
  }).join("");
  productionStageClear?.classList.toggle("hidden", !activeProductionStage);
  productionRail.querySelectorAll("[data-production-stage]").forEach((button) => {
    button.addEventListener("click", () => {
      const selectedStage = button.dataset.productionStage || "";
      activeProductionStage = activeProductionStage === selectedStage ? "" : selectedStage;
      activeEpisodePreset = "all";
      episodeReleaseFilter.value = "";
      episodeProductionFilter.value = "";
      visibleEpisodeCount = EPISODE_PAGE_SIZE;
      renderPlanning();
      const nextButton = productionRail.querySelector(`[data-production-stage="${selectedStage}"]`);
      nextButton?.focus();
    });
  });
}

function renderReleaseWorkspace(episodes) {
  if (!releaseCalendar || !productionRail) return;
  renderReleaseCalendar(episodes);
  renderProductionRail(episodes);
}

async function hydrateAiSchedulingCopilot() {
  if (aiCopilotHydrationInFlight || !latestPlanningPayload.ai_scheduling_enabled) {
    return;
  }
  aiCopilotHydrationInFlight = true;
  
  // Update status message only, don't re-render the whole page
  const originalStatus = latestPlanningPayload.ai_copilot_status;
  latestPlanningPayload.ai_copilot_status = {
    status: "loading",
    message: "AI copilot is analyzing top candidates and enriching with monthly context...",
  };
  renderAiCopilotStatus(latestPlanningPayload.ai_copilot_status);
  
  try {
    const payload = await fetchJSON(buildPlanningApiUrl("/api/planning/ai-copilot"));
    if (payload?.ai_scheduling_enabled) {
      latestPlanningPayload.ai_copilot_status = payload.ai_copilot_status || latestPlanningPayload.ai_copilot_status;
    }
    if (payload?.ai_scheduling_enabled && Array.isArray(payload.recommendations) && payload.recommendations.length) {
      const rejectedIds = new Set(
        (latestPlanningPayload.rejected_recommendations || []).map((item) => String(item.id)),
      );
      latestPlanningPayload.recommendations = payload.recommendations
        .filter((item) => !rejectedIds.has(String(item.id)));
      if (activePlanningTab === "scheduling_intelligence" && !activeEpisodeEditorId && !episodeForm?.elements?.id?.value) {
        const episodeNumberMap = buildEpisodeNumberMap(latestPlanningPayload.episodes || [], latestPlanningPayload.recommendations || []);
        renderRecommendations(
          filterRecommendations(latestPlanningPayload.recommendations || []),
          (latestPlanningPayload.recommendations || []).length,
          episodeNumberMap,
        );
      }
      renderAiCopilotStatus(latestPlanningPayload.ai_copilot_status);
    } else {
      renderAiCopilotStatus(latestPlanningPayload.ai_copilot_status);
    }
  } catch (error) {
    console.warn("AI scheduling copilot hydration failed:", error);
    latestPlanningPayload.ai_copilot_status = {
      status: "fallback",
      message: "AI scheduling copilot request failed. Showing base recommendations without AI enrichment.",
    };
    renderAiCopilotStatus(latestPlanningPayload.ai_copilot_status);
  } finally {
    aiCopilotHydrationInFlight = false;
  }
}

async function applyEpisodeFocusFromUrl() {
  if (!pendingEpisodeIdFromUrl) {
    return;
  }
  const episode = (latestPlanningPayload.episodes || []).find(
    (item) => String(item.id || "") === String(pendingEpisodeIdFromUrl),
  );
  if (!episode) {
    return;
  }
  setPlanningTab("release_planning");
  const fullEpisode = await hydrateEpisodeForEditing(episode);
  loadEpisodeIntoForm(fullEpisode);
  if (pendingPlanningSuccessMessage) {
    setMessage(episodeMessage, pendingPlanningSuccessMessage, "success");
  }
  pendingEpisodeIdFromUrl = null;
  pendingPlanningSuccessMessage = "";
}

async function loadPlanning() {
  clearLegacyPlanningPayloadCaches();
  if (!latestPlanningPayload.episodes?.length && !latestPlanningPayload.recommendations?.length) {
    renderSkeletonCards(episodeList, 4);
    renderSkeletonCards(recommendationList, 3, true);
    const cachedPayload = readCachedPayload(PLANNING_PAYLOAD_CACHE_KEY);
    // Only use cache if it has meaningful data (not all zeros)
    const hasData = cachedPayload && (
      (cachedPayload.stats?.episodes_total ?? 0) > 0 ||
      (cachedPayload.episodes?.length ?? 0) > 0 ||
      (cachedPayload.recommendations?.length ?? 0) > 0
    );
    
    if (hasData) {
      latestPlanningPayload = cachedPayload;
      updatePlanningStats(cachedPayload);
      renderPlanning();
      setMessage(episodeMessage, "Refreshing planning data...", "pending");
    } else {
      setMessage(episodeMessage, "Loading planning data...", "pending");
    }
  }
  const payload = await fetchJSON(buildPlanningApiUrl("/api/planning?compact=true&refresh=true"));
  latestPlanningPayload = payload;
  updatePlanningStats(payload);
  renderPlanning();
  storeCachedPayload(PLANNING_PAYLOAD_CACHE_KEY, payload);
  if (episodeMessage.classList.contains("pending")) {
    setMessage(episodeMessage, "", "");
  }
  applyEpisodeFocusFromUrl().catch((error) => {
    setMessage(episodeMessage, error.message, "error");
  });
  queueMicrotask(() => {
    hydrateAiSchedulingCopilot().catch(() => {});
  });
}

if (episodeForm && episodeSubmitButton) {
  episodeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(episodeForm).entries());
    const episodeId = payload.id;
    const submitButton = episodeSubmitButton;
    delete payload.id;
    try {
      payload.outreach_plan = JSON.stringify(collectOutreachPlanFromForm());
      payload.priority_score = String(
        clampPriorityScore(payload.priority_score, suggestPriorityScoreForEpisode(payload))
      );
      validateEpisodePayloadForSave(payload);
      submitButton.disabled = true;
      submitButton.textContent = episodeId ? "Saving..." : "Creating...";
      setMessage(episodeMessage, episodeId ? "Saving episode changes..." : "Saving episode...", "pending");
      const savedEpisode = await fetchJSON(episodeId ? `/api/episodes/${episodeId}` : "/api/episodes", {
        method: "POST",
        body: JSON.stringify(cleanEpisodePayloadForSave(payload)),
      });
      replaceEpisodeInPayload(savedEpisode);
      resetEpisodeForm();
      closeEpisodeEditor({ restoreFocus: false });
      setMessage(episodeMessage, episodeId ? "Episode updated." : "Episode saved.", "success");
      renderPlanning();
      refreshPlanningQuietly();
    } catch (error) {
      console.error("Episode save error:", error);
      if (error.status === 409 && error.payload?.conflict) {
        showEpisodeConflict(error.payload.conflict);
        setMessage(episodeMessage, "A newer version exists. Choose how to resolve it; your draft has not been lost.", "warning");
      } else {
        setMessage(episodeMessage, error.message || "Failed to save episode", "error");
      }
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = episodeId ? "Update Episode" : "Save Episode";
    }
  });
} else {
  console.error("Episode form or submit button not found in DOM");
}

episodeConflictUseLatest?.addEventListener("click", async () => {
  const episodeId = activeEpisodeConflict?.id || episodeForm?.elements?.id?.value;
  if (!episodeId) return;
  episodeConflictUseLatest.disabled = true;
  episodeConflictUseLatest.textContent = "Loading latest…";
  try {
    const latestEpisode = await fetchJSON(`/api/episodes/${episodeId}`);
    replaceEpisodeInPayload(latestEpisode);
    loadEpisodeIntoForm(latestEpisode);
    setMessage(episodeMessage, "Latest saved version loaded. Review it before making further changes.", "success");
  } catch (error) {
    setMessage(episodeMessage, error.message || "Could not load the latest version.", "error");
  } finally {
    episodeConflictUseLatest.disabled = false;
    episodeConflictUseLatest.textContent = "Use latest version";
  }
});

episodeConflictKeepDraft?.addEventListener("click", () => {
  const latestRowVersion = activeEpisodeConflict?.current_row_version;
  if (!latestRowVersion) {
    setMessage(episodeMessage, "The latest version could not be identified. Load the latest version instead.", "error");
    return;
  }
  episodeForm.elements.row_version.value = latestRowVersion;
  clearEpisodeConflict();
  setMessage(
    episodeMessage,
    "Your draft is preserved and rebased onto the latest version. Review every field, then select Update Episode again to confirm.",
    "warning",
  );
});

if (episodeResetButton) {
  episodeResetButton.addEventListener("click", () => {
    resetEpisodeForm();
    closeEpisodeEditor();
  });
}

if (episodeImportForm) {
  episodeImportForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(episodeImportForm);
    const submitButton = episodeImportForm.querySelector("button[type='submit']");
    submitButton.disabled = true;
    submitButton.textContent = "Importing...";
    setMessage(episodeImportMessage, "Importing episode CSV...", "pending");
    try {
      const result = await postForm("/api/episodes/import", formData);
      episodeImportForm.reset();
      setMessage(
        episodeImportMessage,
        `Episode import finished. New: ${result.imported}, Updated: ${result.updated}.`,
        "success",
      );
      await loadPlanning();
    } catch (error) {
      console.error("Episode import error:", error);
      setMessage(episodeImportMessage, error.message || "Failed to import episodes", "error");
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "Import Episode CSV";
    }
  });
}

if (askSyncForm) {
  askSyncForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(askSyncForm).entries());
    payload.overwrite_existing = Boolean(askSyncForm.elements.overwrite_existing.checked);
    payload.preview_only = true;
    pendingAskSyncRequest = { ...payload };
    const submitButton = askSyncForm.querySelector("button[type='submit']");
    submitButton.disabled = true;
    submitButton.textContent = "Reviewing...";
    setMessage(askSyncMessage, "Finding safe transcript matches for review...", "pending");
    try {
      const result = await fetchJSON("/api/ask-mirror-talk/sync", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const summary = [
        `${result.matched} proposed match${result.matched === 1 ? "" : "es"}`,
        `${result.unmatched_local} unmatched`,
      ].join(" · ");
      setMessage(askSyncMessage, `${summary}. Nothing has been changed yet.`, "success");
      renderAskSyncBreakdown(result);
    } catch (error) {
      console.error("Ask sync error:", error);
      setMessage(askSyncMessage, error.message || "Failed to sync transcripts", "error");
      renderAskSyncBreakdown(null);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "Review Transcript Matches";
    }
  });
}

if (planningExportForm) {
  planningExportForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const selectedFields = Array.from(
      planningExportForm.querySelectorAll("input[name='fields']:checked"),
      (input) => input.value,
    );
    const submitButton = planningExportForm.querySelector("button[type='submit']");
    submitButton.disabled = true;
    submitButton.textContent = "Preparing...";
    setMessage(planningExportMessage, "Preparing export...", "pending");
    try {
      await downloadExport({
        list_name: exportListName.value,
        format: planningExportForm.elements.format.value,
        fields: selectedFields,
      });
      setMessage(planningExportMessage, "Export is downloading.", "success");
    } catch (error) {
      console.error("Export error:", error);
      setMessage(planningExportMessage, error.message || "Failed to export", "error");
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "Export Selected Fields";
    }
  });
}

if (refreshButton) {
  refreshButton.addEventListener("click", async () => {
    refreshButton.disabled = true;
    refreshButton.textContent = "Refreshing...";
    setMessage(episodeMessage, "Refreshing planning data...", "pending");
    try {
      await loadPlanning();
    } catch (error) {
      setMessage(episodeMessage, error.message, "error");
    } finally {
      refreshButton.disabled = false;
      refreshButton.textContent = "Refresh";
    }
  });
}

[
  recommendationSearchInput,
  recommendationCategoryFilter,
  recommendationSort,
  episodeSearchInput,
  episodeCategoryFilter,
  episodeYearFilter,
  episodeReleaseFilter,
  episodeProductionFilter,
  episodeTranscriptFilter,
  episodeSort,
].forEach((node) => {
  node.addEventListener("input", () => {
    if (node === episodeReleaseFilter || node === episodeProductionFilter) activeProductionStage = "";
    visibleRecommendationCount = RECOMMENDATION_PAGE_SIZE;
    visibleEpisodeCount = EPISODE_PAGE_SIZE;
    renderPlanning();
    window.PerformanceUtils?.updateWorkspaceUrlState({ q: episodeSearchInput.value });
  });
  node.addEventListener("change", () => {
    if (node === episodeReleaseFilter || node === episodeProductionFilter) activeProductionStage = "";
    visibleRecommendationCount = RECOMMENDATION_PAGE_SIZE;
    visibleEpisodeCount = EPISODE_PAGE_SIZE;
    renderPlanning();
  });
});

recommendationLoadMoreButton.addEventListener("click", () => {
  visibleRecommendationCount += RECOMMENDATION_PAGE_SIZE;
  renderPlanning();
});

episodeLoadMoreButton.addEventListener("click", () => {
  visibleEpisodeCount += EPISODE_PAGE_SIZE;
  renderPlanning();
});

recommendationPresetButtons.forEach((button) => {
  button.addEventListener("click", () => {
    activeRecommendationPreset = button.dataset.recommendationPreset || "all";
    visibleRecommendationCount = RECOMMENDATION_PAGE_SIZE;
    renderPlanning();
  });
});

episodePresetButtons.forEach((button) => {
  button.addEventListener("click", () => {
    activeEpisodePreset = button.dataset.episodePreset || "all";
    activeProductionStage = "";
    visibleEpisodeCount = EPISODE_PAGE_SIZE;
    if (activeEpisodePreset === "scheduled") {
      episodeReleaseFilter.value = "scheduled";
    } else if (activeEpisodePreset === "released_archive") {
      episodeReleaseFilter.value = "released";
    } else if (activeEpisodePreset === "ready_to_schedule") {
      episodeProductionFilter.value = "ready";
      episodeReleaseFilter.value = "";
    } else if (activeEpisodePreset === "all") {
      episodeReleaseFilter.value = "";
      episodeProductionFilter.value = "";
    }
    renderPlanning();
  });
});

productionStageClear?.addEventListener("click", () => {
  activeProductionStage = "";
  visibleEpisodeCount = EPISODE_PAGE_SIZE;
  renderPlanning();
  productionRail?.querySelector("[data-production-stage]")?.focus();
});

function applyUrlState() {
  const params = new URLSearchParams(window.location.search);
  const query = params.get("q");
  const preset = params.get("preset");
  const episodeId = params.get("episode_id");
  const source = params.get("source");
  const tab = params.get("tab");

  if (query) {
    episodeSearchInput.value = query;
    recommendationSearchInput.value = query;
  }
  if (preset && episodePresetButtons.some((button) => button.dataset.episodePreset === preset)) {
    activeEpisodePreset = preset;
  }
  if (episodeId) {
    pendingEpisodeIdFromUrl = episodeId;
    activeEpisodePreset = "all";
    activePlanningTab = "release_planning";
    pendingPlanningSuccessMessage =
      source === "operations"
        ? "Interview moved into planning. You can finish the episode details here and send the thank-you email when ready."
        : "";
  }
  if (tab && planningTabButtons.some((button) => button.dataset.planningTab === tab)) {
    activePlanningTab = tab;
  }
  setPlanningTab(activePlanningTab);
}

planningTabButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setPlanningTab(button.dataset.planningTab || "release_planning");
    window.PerformanceUtils?.updateWorkspaceUrlState({ tab: activePlanningTab });
  });
});
window.PerformanceUtils?.installKeyboardTabs(planningTabButtons, setPlanningTab);

renderExportFields();
initializeEpisodeEditor();
resetEpisodeForm();
applyUrlState();
episodeForm.elements.outreach_plan.value = JSON.stringify(normalizeOutreachPlan(null));

calendarPreviousButton?.addEventListener("click", () => {
  calendarCursor = new Date(calendarCursor.getFullYear(), calendarCursor.getMonth() - 1, 1);
  renderReleaseCalendar(latestPlanningPayload.episodes || []);
});
calendarTodayButton?.addEventListener("click", () => {
  const now = new Date();
  calendarCursor = new Date(now.getFullYear(), now.getMonth(), 1);
  renderReleaseCalendar(latestPlanningPayload.episodes || []);
});
calendarNextButton?.addEventListener("click", () => {
  calendarCursor = new Date(calendarCursor.getFullYear(), calendarCursor.getMonth() + 1, 1);
  renderReleaseCalendar(latestPlanningPayload.episodes || []);
});
episodeDetailsClose?.addEventListener("click", () => closeEpisodeDetailsModal());
episodeDetailsDismiss?.addEventListener("click", () => closeEpisodeDetailsModal());
episodeDetailsModal?.addEventListener("click", (event) => {
  if (event.target === episodeDetailsModal) closeEpisodeDetailsModal();
});
episodeDetailsEdit?.addEventListener("click", async () => {
  const episode = (latestPlanningPayload.episodes || []).find(
    (item) => Number(item.id) === Number(selectedCalendarEpisodeId),
  );
  if (!episode) return;
  try {
    const fullEpisode = await hydrateEpisodeForEditing(episode);
    closeEpisodeDetailsModal({ restoreFocus: false });
    loadEpisodeIntoForm(fullEpisode);
    setMessage(episodeMessage, `Loaded ${episode.episode_title || "episode"} into the editor.`, "success");
  } catch (error) {
    setMessage(episodeMessage, error.message || "Could not load episode details", "error");
  }
});
episodeEditorCreate?.addEventListener("click", (event) => {
  setPlanningTab("release_planning");
  resetEpisodeForm();
  openEpisodeEditor({ restoreFocusTo: event.currentTarget });
});
episodeEditorClose?.addEventListener("click", () => {
  resetEpisodeForm();
  closeEpisodeEditor();
});
episodeEditorModal?.addEventListener("click", (event) => {
  if (event.target === episodeEditorModal) {
    resetEpisodeForm();
    closeEpisodeEditor();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && episodeDetailsModal && !episodeDetailsModal.classList.contains("hidden")) {
    closeEpisodeDetailsModal();
  }
  if (event.key === "Escape" && episodeEditorModal && !episodeEditorModal.classList.contains("hidden")) {
    resetEpisodeForm();
    closeEpisodeEditor();
  }
});

// Schedule modal event listener
if (scheduleForm) {
  scheduleForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const episodeId = scheduleForm.elements.episode_id.value;
    const releaseDate = scheduleForm.elements.release_date.value;
    const scheduleOverrideReason = scheduleForm.elements.schedule_override_reason.value.trim();
    
    if (!episodeId || !releaseDate) {
      setMessage(scheduleModalMessage, "Please select a date and time.", "error");
      return;
    }
    
    const submitButton = scheduleForm.querySelector("button[type='submit']");
    submitButton.disabled = true;
    submitButton.textContent = "Scheduling...";
    setMessage(scheduleModalMessage, "Scheduling episode...", "pending");
    
    try {
      const savedEpisode = await fetchJSON(`/api/episodes/${episodeId}`, {
        method: "POST",
        body: JSON.stringify({
          release_date: releaseDate,
          release_status: "scheduled",
          schedule_override_reason: scheduleOverrideReason,
        }),
      });
      replaceEpisodeInPayload(savedEpisode);
      
      setMessage(episodeMessage, `Scheduled for ${formatDateTime(releaseDate)}.`, "success");
      closeScheduleModal();
      renderPlanning();
      refreshPlanningQuietly();
    } catch (error) {
      console.error("Schedule error:", error);
      setMessage(scheduleModalMessage, error.message || "Failed to schedule episode", "error");
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "Confirm Schedule";
    }
  });
}

// Close modal when cancel button is clicked
const modalCancelButton = document.querySelector("[data-modal-action='cancel']");
if (modalCancelButton) {
  modalCancelButton.addEventListener("click", () => {
    closeScheduleModal();
  });
}

if (!enforceHostedMode()) {
  loadPlanning().catch((error) => {
    console.error("Planning load error:", error);
    setMessage(episodeMessage, error.message || "Failed to load planning data", "error");
  });
}
