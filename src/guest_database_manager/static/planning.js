const episodeForm = document.getElementById("episode-form");
const episodeImportForm = document.getElementById("episode-import-form");
const askSyncForm = document.getElementById("ask-sync-form");
const planningExportForm = document.getElementById("planning-export-form");
const episodeSubmitButton = document.getElementById("episode-submit-button");
const episodeResetButton = document.getElementById("episode-reset-button");
const exportListName = document.getElementById("export-list-name");
const exportFields = document.getElementById("export-fields");
const episodeCategoryOptions = document.getElementById("episode-category-options");
const episodeMessage = document.getElementById("episode-message");
const episodeImportMessage = document.getElementById("episode-import-message");
const askSyncMessage = document.getElementById("ask-sync-message");
const askSyncBreakdown = document.getElementById("ask-sync-breakdown");
const askSyncAmbiguous = document.getElementById("ask-sync-ambiguous");
const planningExportMessage = document.getElementById("planning-export-message");
const planningWeeklySystem = document.getElementById("planning-weekly-system");
const aiCopilotStatus = document.getElementById("planning-ai-copilot-status");
const episodeList = document.getElementById("episode-list");
const recommendationList = document.getElementById("recommendation-list");
const refreshButton = document.getElementById("planning-refresh-button");
const recommendationSearchInput = document.getElementById("recommendation-search");
const recommendationCategoryFilter = document.getElementById("recommendation-category-filter");
const recommendationSort = document.getElementById("recommendation-sort");
const recommendationResultsMeta = document.getElementById("recommendation-results-meta");
const recommendationLoadMoreButton = document.getElementById("recommendation-load-more");
const recommendationPresetButtons = Array.from(document.querySelectorAll("[data-recommendation-preset]"));
const episodeSearchInput = document.getElementById("episode-search");
const episodeCategoryFilter = document.getElementById("episode-category-filter");
const episodeYearFilter = document.getElementById("episode-year-filter");
const episodeReleaseFilter = document.getElementById("episode-release-filter");
const episodeProductionFilter = document.getElementById("episode-production-filter");
const episodeTranscriptFilter = document.getElementById("episode-transcript-filter");
const episodeSort = document.getElementById("episode-sort");
const episodeResultsMeta = document.getElementById("episode-results-meta");
const episodeLoadMoreButton = document.getElementById("episode-load-more");
const episodePresetButtons = Array.from(document.querySelectorAll("[data-episode-preset]"));
const planningTabButtons = Array.from(document.querySelectorAll("[data-planning-tab]"));
const planningTabPanels = Array.from(document.querySelectorAll("[data-planning-panel]"));

let latestPlanningPayload = {
  stats: {},
  episodes: [],
  recommendations: [],
  available_categories: [],
};
let activeRecommendationPreset = "all";
let activeEpisodePreset = "all";
let activeEpisodeEditorId = null;
let activeEpisodeFeedback = { id: null, text: "", tone: "" };
let activeEpisodeActionFeedback = { id: null, text: "", tone: "" };
let visibleRecommendationCount = 6;
let visibleEpisodeCount = 10;
let pendingEpisodeIdFromUrl = null;
let pendingPlanningSuccessMessage = "";
let activePlanningTab = "release_planning";
let aiCopilotHydrationInFlight = false;
const PLANNING_PAYLOAD_CACHE_KEY = "mirror-talk-planning-payload";

const RECOMMENDATION_PAGE_SIZE = 6;
const EPISODE_PAGE_SIZE = 10;
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
    ["episode_title", "Episode Title"],
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
  try {
    const raw = window.sessionStorage.getItem(cacheKey);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (error) {
    return null;
  }
}

function storeCachedPayload(cacheKey, payload) {
  try {
    window.sessionStorage.setItem(cacheKey, JSON.stringify(payload));
  } catch (error) {
    // Ignore browser cache failures.
  }
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
  latestPlanningPayload.episodes = (latestPlanningPayload.episodes || []).map(replaceById);
  latestPlanningPayload.recommendations = (latestPlanningPayload.recommendations || []).map(replaceById);
}

async function fetchJSON(url, options = {}) {
  const isReadRequest = !options.method || String(options.method).toUpperCase() === "GET";
  let lastError = null;

  for (let attempt = 0; attempt < (isReadRequest ? 2 : 1); attempt += 1) {
    try {
      const response = await fetch(url, {
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Request failed");
      }
      return data;
    } catch (error) {
      lastError = error;
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
    headers: { "Content-Type": "application/json" },
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
  node.textContent = text;
  node.className = `message ${tone}`.trim();
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
  if (episode.transcript_text) {
    return "Available";
  }
  if (transcriptExpectedSoon(episode)) {
    return "Missing";
  }
  return "Not expected yet";
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

function focusEpisodeEditor(episode, successMessage = "") {
  setPlanningTab("release_planning");
  loadEpisodeIntoForm(episode);
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
  const strengths = (readiness.strengths || []).slice(0, 2).map((item) => `<li>${item}</li>`).join("");
  const blockers = (readiness.blockers || []).slice(0, 2).map((item) => `<li>${item}</li>`).join("");
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
  aiCopilotStatus.className = `operations-preview ai-copilot-status ${tone}`.trim();
  aiCopilotStatus.innerHTML = `
    <strong class="insight-label">AI scheduling copilot</strong>
    <p><strong>Status:</strong> ${escapeHtml(status.replaceAll("_", " "))}</p>
    ${statusPayload?.message ? `<p>${escapeHtml(statusPayload.message)}</p>` : ""}
    ${statusPayload?.model ? `<p><strong>Model:</strong> ${escapeHtml(statusPayload.model)}</p>` : ""}
    ${monthContext?.month_label ? `<p><strong>Current month lens:</strong> ${escapeHtml(monthContext.month_label)} · ${escapeHtml(monthContext.theme || "")}</p>` : ""}
    ${observances.length ? `<p><strong>Editorial observances:</strong> ${observances.map((item) => `<code>${escapeHtml(item)}</code>`).join(", ")}</p>` : ""}
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

function renderMonthlyAngleDecision(episode) {
  const state = normalizeText(episode.ai_monthly_angle_state);
  const theme = String(episode.ai_monthly_angle_theme || episode.ai_copilot?.monthly_theme || "").trim();
  if (!state && !theme) {
    return "";
  }
  const label = state === "pinned" ? "Pinned" : state === "rejected" ? "Rejected" : "Unreviewed";
  const tone = state === "pinned" ? "good" : state === "rejected" ? "warning" : "";
  return `
    <div class="operations-preview">
      <strong class="insight-label">Monthly angle review</strong>
      <div class="signal-list">
        <span class="signal-chip ${tone}">${escapeHtml(label)}</span>
      </div>
      ${theme ? `<p><strong>Theme:</strong> ${escapeHtml(theme)}</p>` : ""}
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
      <p>${copyAssist.summary || ""}</p>
      <p><strong>Social:</strong> ${copyAssist.social_caption || ""}</p>
      <p><strong>Newsletter:</strong> ${copyAssist.newsletter_blurb || ""}</p>
      ${copyAssist.show_notes_intro ? `<p><strong>Show notes intro:</strong> ${copyAssist.show_notes_intro}</p>` : ""}
      ${copyAssist.quote_pull ? `<p><strong>Quote pull:</strong> ${copyAssist.quote_pull}</p>` : ""}
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
  const plan = {};
  outreachChecklist.querySelectorAll("input[data-outreach-key]").forEach((input) => {
    plan[input.dataset.outreachKey] = Boolean(input.checked);
  });
  return plan;
}

function parseLegacyEpisodeNumber(value) {
  const text = String(value || "").trim();
  if (!/^\d+$/.test(text)) {
    return null;
  }
  return Number.parseInt(text, 10);
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
  const principles = (system.principles || []).map((item) => `<li>${item}</li>`).join("");
  const metrics = (system.metrics || []).map((item) => `<li>${item}</li>`).join("");
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
    ["Updated title only", result.updated_title_only ?? 0],
    ["Skipped ambiguous", result.skipped_ambiguous ?? 0],
  ];
  askSyncBreakdown.classList.remove("hidden");
  askSyncBreakdown.innerHTML = `
    <strong class="insight-label">Sync breakdown</strong>
    <ul>${items.map(([label, value]) => `<li>${label}: ${value}</li>`).join("")}</ul>
  `;
  renderAskSyncAmbiguous(result.ambiguous_matches || []);
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
              <strong>${candidate.title || "Untitled Ask episode"}</strong>
              <span>${parts.join(" · ")}</span>
            </li>
          `;
        })
        .join("");

      return `
        <article class="mini-card">
          <strong>${local.title || "Untitled local episode"}</strong>
          <p>${local.guest_name || "Unknown guest"}${localDate ? ` · ${formatDateTime(localDate)}` : ""}</p>
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
  const completed = (summary.completed_labels || []).map((item) => `<li>${item}</li>`).join("");
  const pending = (summary.pending_labels || []).map((item) => `<li>${item}</li>`).join("");
  return `
    <div class="operations-preview">
      <strong class="insight-label">Outreach status for this episode</strong>
      <p><strong>${summary.progress_label}</strong></p>
      <p>${summary.next_step || ""}</p>
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
      node.innerHTML = `<p class="composer-feedback success">Release email sent to ${episode.guest_name || episode.guest_email}.</p>`;
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

function resetEpisodeForm() {
  episodeForm.reset();
  episodeForm.elements.id.value = "";
  episodeForm.elements.interview_id.value = "";
  episodeForm.elements.outreach_plan.value = JSON.stringify(normalizeOutreachPlan(null));
  episodeForm.elements.release_status.value = "unplanned";
  episodeForm.elements.production_status.value = "idea";
  episodeForm.elements.promotion_status.value = "unknown";
  episodeForm.elements.priority_score.value = String(clampPriorityScore(suggestPriorityScoreForEpisode({}), 3));
  episodeForm.elements.legacy_episode_number.value = computeNextLegacyEpisodeNumber(latestPlanningPayload.episodes || []);
  episodeSubmitButton.textContent = "Save Episode";
  episodeResetButton.hidden = true;
}

function loadEpisodeIntoForm(episode, { releaseDate = "", releaseStatus = "" } = {}) {
  const effectiveReleaseStatus = releaseStatus || episode.release_status || "unplanned";
  const effectiveProductionStatus = episode.production_status || "idea";
  const effectivePromotionStatus = episode.promotion_status || "unknown";
  episodeForm.elements.id.value = episode.id || "";
  episodeForm.elements.interview_id.value = episode.interview_id || "";
  episodeForm.elements.guest_name.value = episode.guest_name || "";
  episodeForm.elements.guest_email.value = episode.guest_email || "";
  episodeForm.elements.website.value = episode.website || "";
  episodeForm.elements.episode_title.value = episode.episode_title || "";
  episodeForm.elements.topic.value = episode.topic || "";
  episodeForm.elements.category.value = episode.category || "";
  episodeForm.elements.interview_date.value = formatDateForDateInput(episode.interview_date);
  episodeForm.elements.recording_date.value = formatDateForDateInput(episode.recording_date);
  episodeForm.elements.release_date.value = formatDateForDateTimeInput(releaseDate || episode.release_date);
  episodeForm.elements.release_status.value = effectiveReleaseStatus;
  episodeForm.elements.production_status.value = effectiveProductionStatus;
  episodeForm.elements.promotion_status.value = effectivePromotionStatus;
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
  episodeForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderEpisodeInlineEditor(container, episode) {
  container.innerHTML = `
    <div class="inline-editor-title">Quick Edit Episode</div>
    <form class="inline-editor-form" data-inline-episode-form>
      ${createFieldMarkup("Episode Title", `<input name="episode_title" type="text" value="${episode.episode_title || ""}" required />`, true)}
      ${createFieldMarkup("Guest Name", `<input name="guest_name" type="text" value="${episode.guest_name || ""}" required />`)}
      ${createFieldMarkup("Guest Email", `<input name="guest_email" type="email" value="${episode.guest_email || ""}" />`)}
      ${createFieldMarkup("Category", `<input name="category" type="text" list="episode-category-options" value="${episode.category || ""}" />`)}
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
      ${createFieldMarkup("Topic", `<input name="topic" type="text" value="${episode.topic || ""}" />`, true)}
      ${createFieldMarkup("Show Note / Blogpost URL", `<input name="show_notes_url" type="url" value="${episode.show_notes_url || ""}" />`, true)}
      ${createFieldMarkup("Files URL", `<input name="release_files_url" type="url" value="${episode.release_files_url || ""}" />`, true)}
      ${createFieldMarkup("Transcript", `<textarea name="transcript_text" rows="5">${episode.transcript_text || ""}</textarea>`, true)}
      ${createFieldMarkup("Notes", `<textarea name="notes" rows="3">${episode.notes || ""}</textarea>`, true)}
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
      await fetchJSON(`/api/episodes/${episode.id}`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      activeEpisodeFeedback = {
        id: episode.id,
        text: `Saved ${payload.episode_title || "episode"}.`,
        tone: "success",
      };
      setMessage(episodeMessage, `Updated ${payload.episode_title || "episode"}.`, "success");
      activeEpisodeEditorId = episode.id;
      await loadPlanning();
    } catch (error) {
      setMessage(messageNode, error.message, "error");
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
      await fetchJSON(`/api/episodes/${episode.id}`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
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
      await loadPlanning();
    } catch (error) {
      setMessage(messageNode, error.message, "error");
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
  const sortMode = episodeSort.value || "closest_release";

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
    if (transcriptStatus === "has_transcript" && !episode.transcript_text) {
      return false;
    }
    if (transcriptStatus === "missing_transcript" && (episode.transcript_text || !transcriptExpectedSoon(episode))) {
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
    return true;
  });

  filtered.sort((left, right) => {
    if (sortMode === "guest_name") {
      return normalizeText(left.guest_name).localeCompare(normalizeText(right.guest_name));
    }
    if (sortMode === "category") {
      return normalizeText(left.category).localeCompare(normalizeText(right.category));
    }
    if (sortMode === "priority") {
      return Number(right.priority_score || 0) - Number(left.priority_score || 0);
    }
    if (sortMode === "latest_interview") {
      const leftDate = parseDate(left.interview_date);
      const rightDate = parseDate(right.interview_date);
      if (!leftDate && !rightDate) return Number(right.id || 0) - Number(left.id || 0);
      if (!leftDate) return 1;
      if (!rightDate) return -1;
      return rightDate - leftDate;
    }

    const leftRelease = parseDate(left.release_date);
    const rightRelease = parseDate(right.release_date);
    if (!leftRelease && !rightRelease) return Number(right.priority_score || 0) - Number(left.priority_score || 0);
    if (!leftRelease) return 1;
    if (!rightRelease) return -1;
    return leftRelease - rightRelease;
  });

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

function renderEpisodes(episodes, totalCount) {
  episodeList.innerHTML = "";
  updateResultsMeta(
    episodeResultsMeta,
    episodes.length,
    totalCount,
    "No episodes tracked yet.",
    "Use search, category, year, or status filters to focus the planning queue."
  );

  const visibleEpisodes = episodes.slice(0, visibleEpisodeCount);
  if (!episodes.length) {
    episodeList.innerHTML = totalCount
      ? "<p class='guest-summary'>No episodes match the current planning controls.</p>"
      : "<p class='guest-summary'>No episodes tracked yet.</p>";
    episodeLoadMoreButton.classList.add("hidden");
    return;
  }

  visibleEpisodes.forEach((episode) => {
    const isReleased = normalizeText(episode.release_status) === "released";
    const hasEmail = Boolean(episode.guest_email);
    const hasShowNotes = Boolean(normalizeText(episode.show_notes_url));
    const hasFilesLink = Boolean(normalizeText(episode.release_files_url));
    const releaseEmailReady = hasEmail && isReleased && hasShowNotes && hasFilesLink;
    const releaseActionLabel = releaseEmailReady ? "Send Release Email" : "Prepare Release Email";
    const card = document.createElement("article");
    card.className = "operations-card";
    card.innerHTML = `
      <h3>${episode.episode_title || "Untitled episode"}</h3>
      <p>${episode.guest_name || "Guest not set"}</p>
      ${renderEpisodeBadges(episode)}
      <div class="operations-meta">
        <span>Topic: ${episode.topic || "Not set"}</span>
        <span>Category: ${episode.category || "Not set"}</span>
        <span>Email: ${renderLinkedValue(episode.guest_email)}</span>
        <span>Website: ${renderLinkedValue(episode.website)}</span>
        <span>Interviewed: ${formatDateTime(episode.interview_date)}</span>
        <span>Release: ${formatDateTime(episode.release_date)}</span>
        <span>Status: ${episode.release_status || "unplanned"} / ${episode.production_status || "idea"}</span>
        <span>Promo: ${episode.promotion_status || "unknown"}</span>
        <span>Readiness: ${episode.promotion_readiness?.score ?? 0}/100</span>
        <span>Priority: ${episode.priority_score ?? 0}</span>
        <span>Show Notes: ${renderLinkedValue(episode.show_notes_url, "Missing")}</span>
        <span>Files: ${renderLinkedValue(episode.release_files_url, "Missing")}</span>
        <span>Transcript: ${transcriptStatusLabel(episode)}</span>
        <span>Source: ${episode.source_file_name || "Manual entry"}</span>
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
        <button type="button" class="secondary-button" data-episode-action="edit">${activeEpisodeEditorId === episode.id ? "Hide Quick Edit" : "Quick Edit"}</button>
        <button type="button" class="ghost-button" data-episode-action="form">Open In Form</button>
        <button type="button" class="ghost-button" data-episode-action="preview-appreciation" ${hasEmail ? "" : "disabled"}>Preview Thank You</button>
        <button type="button" class="secondary-button" data-episode-action="send-appreciation" ${hasEmail ? "" : "disabled"}>Send Thank You</button>
        <button type="button" class="ghost-button" data-episode-action="preview-release-email" ${hasEmail ? "" : "disabled"}>Preview Release Email</button>
        <button type="button" class="secondary-button" data-episode-action="send-release-email" ${hasEmail ? "" : "disabled"}>${releaseActionLabel}</button>
        <button type="button" class="ghost-button danger-button" data-episode-action="delete">Delete</button>
      </div>
      <div class="card-action-feedback">${activeEpisodeActionFeedback.id === episode.id ? actionFeedbackMarkup(activeEpisodeActionFeedback) : ""}</div>
      <div class="operations-preview hidden" data-episode-appreciation-preview></div>
      <div class="operations-preview hidden" data-episode-release-preview></div>
      <div class="inline-editor hidden" data-episode-editor></div>
    `;

    const editButton = card.querySelector("[data-episode-action='edit']");
    const formButton = card.querySelector("[data-episode-action='form']");
    const previewAppreciationButton = card.querySelector("[data-episode-action='preview-appreciation']");
    const sendAppreciationButton = card.querySelector("[data-episode-action='send-appreciation']");
    const previewReleaseButton = card.querySelector("[data-episode-action='preview-release-email']");
    const sendReleaseButton = card.querySelector("[data-episode-action='send-release-email']");
    const deleteButton = card.querySelector("[data-episode-action='delete']");
    const editorNode = card.querySelector("[data-episode-editor]");
    const actionFeedbackNode = card.querySelector(".card-action-feedback");
    const appreciationPreviewNode = card.querySelector("[data-episode-appreciation-preview]");
    const releasePreviewNode = card.querySelector("[data-episode-release-preview]");
    editButton.addEventListener("click", () => {
      activeEpisodeEditorId = activeEpisodeEditorId === episode.id ? null : episode.id;
      renderPlanning();
    });
    formButton.addEventListener("click", () => {
      loadEpisodeIntoForm(episode);
      setMessage(
        episodeMessage,
        `Loaded ${episode.episode_title || episode.guest_name || "episode"} into the main form. You can finish the details here or send the thank-you email when ready.`,
        "success",
      );
    });
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
            <h4>${preview.subject}</h4>
            <p>To: ${renderLinkedValue(episode.guest_email)}</p>
            <pre>${preview.body}</pre>
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
          appreciationPreviewNode.innerHTML = `<p class="composer-feedback success">Thank-you email sent to ${episode.guest_name || episode.guest_email}.</p>`;
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
          loadEpisodeIntoForm(episode);
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
          releasePreviewNode.innerHTML = `<p class="composer-feedback success">Release email sent to ${episode.guest_name || episode.guest_email}.</p>`;
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
        await fetchJSON(`/api/episodes/${episode.id}`, {
          method: "DELETE",
          body: JSON.stringify({ confirm_label: typedLabel }),
        });
        activeEpisodeActionFeedback = { id: episode.id, text: `${label} deleted.`, tone: "success" };
        setMessage(episodeMessage, `Deleted ${label}.`, "success");
        await loadPlanning();
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

function renderRecommendations(recommendations, totalCount) {
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
    const card = document.createElement("article");
    card.className = "operations-card recommendation-card";
    card.innerHTML = `
      <h3>#${index + 1} ${episode.episode_title || episode.topic || "Untitled episode"}</h3>
      <p>${episode.guest_name || "Guest not set"}</p>
      <div class="operations-meta">
        <span>Recommended Slot: ${formatDateTime(episode.recommended_release_date)}</span>
        <span>Score: ${episode.priority_score ?? 0}</span>
        <span>Category: ${episode.category || "Not set"}</span>
        <span>Interviewed: ${formatDateTime(episode.interview_date)}</span>
        <span>Production: ${episode.production_status || "idea"}</span>
        <span>Promo: ${episode.promotion_status || "unknown"}</span>
      </div>
      ${signals.length ? `<div class="signal-list">${signals.map((signal) => `<span class="signal-chip ${signal.tone}">${signal.label}</span>`).join("")}</div>` : ""}
      <div class="operations-preview">
        <p>${insights.summary}</p>
        ${insights.strengths.length ? `<div class="insight-stack"><strong class="insight-label">Why now</strong><ul>${insights.strengths.map((item) => `<li>${item}</li>`).join("")}</ul></div>` : ""}
        ${insights.cautions.length ? `<div class="insight-stack caution"><strong class="insight-label">Watchouts</strong><ul>${insights.cautions.map((item) => `<li>${item}</li>`).join("")}</ul></div>` : ""}
      </div>
      ${episode.why_now?.length ? `<div class="operations-preview"><strong class="insight-label">Why this next</strong><ul>${episode.why_now.map((item) => `<li>${item}</li>`).join("")}</ul></div>` : ""}
      ${episode.watchouts?.length ? `<div class="operations-preview"><strong class="insight-label">Why not now</strong><ul>${episode.watchouts.map((item) => `<li>${item}</li>`).join("")}</ul></div>` : ""}
      ${renderSeasonalFit(episode.seasonal_fit)}
      ${renderAiSchedulingCopilot(episode.ai_copilot)}
      ${renderMonthlyAngleDecision(episode)}
      ${episode.sequence_warnings?.length ? `<div class="operations-preview"><strong class="insight-label">Sequence warnings</strong><ul>${episode.sequence_warnings.map((item) => `<li>${item}</li>`).join("")}</ul></div>` : ""}
      ${episode.archive_overlap?.message ? `<div class="operations-preview"><strong class="insight-label">Archive overlap</strong><p>${episode.archive_overlap.message}</p></div>` : ""}
      ${episode.topic_cluster_warning?.message ? `<div class="operations-preview"><strong class="insight-label">Recent topic cluster</strong><p>${episode.topic_cluster_warning.message}</p></div>` : ""}
      ${renderPromoReadiness(episode.promotion_readiness)}
      ${renderGuestResearchCopilot(episode.guest_research)}
      ${renderCopyAssist(episode.copy_assist)}
      <div class="context-links">
        <a class="context-link" href="${buildScopedLink("/dashboard", episode.guest_name || episode.guest_email)}">View Guest</a>
        <a class="context-link" href="${buildScopedLink("/operations", episode.guest_name || episode.guest_email)}">View Interview Ops</a>
      </div>
      <div class="operations-actions">
        <button type="button" class="primary-button" data-recommendation-action="schedule">Use Recommended Slot</button>
        <button type="button" class="secondary-button" data-recommendation-action="edit">Review In Form</button>
        <button 
          type="button" 
          class="ghost-button" 
          data-recommendation-action="pin-angle" 
          ${episode.ai_copilot?.monthly_theme ? "" : "disabled"}
          ${episode.ai_copilot?.monthly_theme ? "" : 'title="AI copilot analysis not available for this episode"'}
        >Pin Angle</button>
        <button 
          type="button" 
          class="ghost-button" 
          data-recommendation-action="reject-angle" 
          ${episode.ai_copilot?.monthly_theme ? "" : "disabled"}
          ${episode.ai_copilot?.monthly_theme ? "" : 'title="AI copilot analysis not available for this episode"'}
        >Reject Angle</button>
        <button 
          type="button" 
          class="ghost-button" 
          data-recommendation-action="clear-angle" 
          ${episode.ai_monthly_angle_state ? "" : "disabled"}
          ${episode.ai_monthly_angle_state ? "" : 'title="No angle review to clear"'}
        >Clear Angle Review</button>
      </div>
      <div class="card-action-feedback">${activeEpisodeActionFeedback.id === episode.id ? actionFeedbackMarkup(activeEpisodeActionFeedback) : ""}</div>
    `;
    const scheduleButton = card.querySelector("[data-recommendation-action='schedule']");
    const editButton = card.querySelector("[data-recommendation-action='edit']");
    const pinAngleButton = card.querySelector("[data-recommendation-action='pin-angle']");
    const rejectAngleButton = card.querySelector("[data-recommendation-action='reject-angle']");
    const clearAngleButton = card.querySelector("[data-recommendation-action='clear-angle']");
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
          priority_score: clampPriorityScore(
            episode.priority_score,
            suggestPriorityScoreForEpisode({
              release_status: "scheduled",
              production_status: episode.production_status,
              promotion_status: episode.promotion_status,
            })
          ),
        };
        await fetchJSON(`/api/episodes/${episode.id}`, {
          method: "POST",
          body: JSON.stringify(payload),
        });
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
        await loadPlanning();
      } catch (error) {
        activeEpisodeActionFeedback = { id: episode.id, text: error.message, tone: "error" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeEpisodeActionFeedback);
        setMessage(episodeMessage, error.message, "error");
        scheduleButton.disabled = false;
        scheduleButton.textContent = "Use Recommended Slot";
      }
    });
    editButton.addEventListener("click", () => {
      setPlanningTab("release_planning");
      loadEpisodeIntoForm(episode, {
        releaseDate: episode.recommended_release_date,
        releaseStatus: "scheduled",
      });
      setMessage(
        episodeMessage,
        `Loaded ${episode.episode_title || episode.guest_name || "episode"} into the release form with the recommended slot ready for review.`,
        "success",
      );
    });
    const setMonthlyAngleDecision = async (state) => {
      const theme = state ? String(episode.ai_copilot?.monthly_theme || episode.ai_monthly_angle_theme || "").trim() : "";
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
          state ? `${state === "pinned" ? "Pinned" : "Rejected"} the AI monthly angle for ${episode.guest_name || "episode"}.` : `Cleared the AI monthly angle review for ${episode.guest_name || "episode"}.`,
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

function renderPlanning() {
  const episodes = latestPlanningPayload.episodes || [];
  const recommendations = latestPlanningPayload.recommendations || [];
  const categories = latestPlanningPayload.available_categories || [];

  updatePresetButtons(recommendationPresetButtons, activeRecommendationPreset, "recommendationPreset");
  updatePresetButtons(episodePresetButtons, activeEpisodePreset, "episodePreset");
  populatePlanningFilters(categories, episodes);
  renderCategoryOptions(categories);
  renderWeeklySystemPanel(latestPlanningPayload.weekly_system);
  renderAiCopilotStatus(latestPlanningPayload.ai_copilot_status);
  renderRecommendations(filterRecommendations(recommendations), recommendations.length);
  renderEpisodes(filterEpisodes(episodes), episodes.length);
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
    const payload = await fetchJSON("/api/planning/ai-copilot");
    if (payload?.ai_scheduling_enabled) {
      latestPlanningPayload.ai_copilot_status = payload.ai_copilot_status || latestPlanningPayload.ai_copilot_status;
    }
    if (payload?.ai_scheduling_enabled && Array.isArray(payload.recommendations) && payload.recommendations.length) {
      latestPlanningPayload.recommendations = payload.recommendations;
      renderPlanning();
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

function applyEpisodeFocusFromUrl() {
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
  loadEpisodeIntoForm(episode);
  if (pendingPlanningSuccessMessage) {
    setMessage(episodeMessage, pendingPlanningSuccessMessage, "success");
  }
  pendingEpisodeIdFromUrl = null;
  pendingPlanningSuccessMessage = "";
}

async function loadPlanning() {
  if (!latestPlanningPayload.episodes?.length && !latestPlanningPayload.recommendations?.length) {
    const cachedPayload = readCachedPayload(PLANNING_PAYLOAD_CACHE_KEY);
    // Only use cache if it has meaningful data (not all zeros)
    const hasData = cachedPayload && (
      (cachedPayload.stats?.episodes_total ?? 0) > 0 ||
      (cachedPayload.episodes?.length ?? 0) > 0 ||
      (cachedPayload.recommendations?.length ?? 0) > 0
    );
    
    if (hasData) {
      latestPlanningPayload = cachedPayload;
      stats.total.textContent = cachedPayload.stats?.episodes_total ?? 0;
      stats.released.textContent = cachedPayload.stats?.episodes_released ?? 0;
      stats.scheduled.textContent = cachedPayload.stats?.episodes_scheduled ?? 0;
      stats.unreleased.textContent = cachedPayload.stats?.episodes_unreleased ?? 0;
      stats.promoReady.textContent = cachedPayload.stats?.episodes_promo_ready ?? 0;
      stats.needsAssets.textContent = cachedPayload.stats?.episodes_need_assets ?? 0;
      renderPlanning();
      setMessage(episodeMessage, "Refreshing planning data...", "pending");
    } else {
      setMessage(episodeMessage, "Loading planning data...", "pending");
    }
  }
  const payload = await fetchJSON("/api/planning");
  latestPlanningPayload = payload;
  stats.total.textContent = payload.stats.episodes_total ?? 0;
  stats.released.textContent = payload.stats.episodes_released ?? 0;
  stats.scheduled.textContent = payload.stats.episodes_scheduled ?? 0;
  stats.unreleased.textContent = payload.stats.episodes_unreleased ?? 0;
  stats.promoReady.textContent = payload.stats.episodes_promo_ready ?? 0;
  stats.needsAssets.textContent = payload.stats.episodes_need_assets ?? 0;
  renderPlanning();
  storeCachedPayload(PLANNING_PAYLOAD_CACHE_KEY, payload);
  if (episodeMessage.classList.contains("pending")) {
    setMessage(episodeMessage, "", "");
  }
  applyEpisodeFocusFromUrl();
  queueMicrotask(() => {
    hydrateAiSchedulingCopilot().catch(() => {});
  });
}

episodeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(episodeForm).entries());
  const episodeId = payload.id;
  const submitButton = episodeSubmitButton;
  payload.outreach_plan = JSON.stringify(collectOutreachPlanFromForm());
  payload.priority_score = String(
    clampPriorityScore(payload.priority_score, suggestPriorityScoreForEpisode(payload))
  );
  delete payload.id;
  submitButton.disabled = true;
  submitButton.textContent = episodeId ? "Saving..." : "Creating...";
  setMessage(episodeMessage, episodeId ? "Saving episode changes..." : "Saving episode...", "pending");
  try {
    await fetchJSON(episodeId ? `/api/episodes/${episodeId}` : "/api/episodes", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    resetEpisodeForm();
    setMessage(episodeMessage, episodeId ? "Episode updated." : "Episode saved.", "success");
    await loadPlanning();
  } catch (error) {
    setMessage(episodeMessage, error.message, "error");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = episodeId ? "Update Episode" : "Save Episode";
  }
});

episodeResetButton.addEventListener("click", () => {
  resetEpisodeForm();
  setMessage(episodeMessage, "Back to creating a new episode.", "success");
});

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
    setMessage(episodeImportMessage, error.message, "error");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Import Episode CSV";
  }
});

askSyncForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(askSyncForm).entries());
  payload.overwrite_existing = Boolean(askSyncForm.elements.overwrite_existing.checked);
  const submitButton = askSyncForm.querySelector("button[type='submit']");
  submitButton.disabled = true;
  submitButton.textContent = "Syncing...";
  setMessage(askSyncMessage, "Syncing Ask Mirror Talk transcripts...", "pending");
  try {
    const result = await fetchJSON("/api/ask-mirror-talk/sync", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const summary = [
      `Updated ${result.updated} episode${result.updated === 1 ? "" : "s"}`,
      `${result.matched} matched`,
      `${result.unmatched_local} unmatched`,
    ].join(" · ");
    setMessage(askSyncMessage, summary, "success");
    renderAskSyncBreakdown(result);
    await loadPlanning();
  } catch (error) {
    setMessage(askSyncMessage, error.message, "error");
    renderAskSyncBreakdown(null);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Sync Matching Transcripts";
  }
});

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
    setMessage(planningExportMessage, error.message, "error");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Export Selected Fields";
  }
});

exportListName.addEventListener("change", renderExportFields);
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
    visibleRecommendationCount = RECOMMENDATION_PAGE_SIZE;
    visibleEpisodeCount = EPISODE_PAGE_SIZE;
    renderPlanning();
  });
  node.addEventListener("change", () => {
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
  });
});

renderExportFields();
resetEpisodeForm();
applyUrlState();
episodeForm.elements.outreach_plan.value = JSON.stringify(normalizeOutreachPlan(null));
loadPlanning().catch((error) => {
  setMessage(episodeMessage, error.message, "error");
});
