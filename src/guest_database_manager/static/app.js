(() => {
  try {
    const probe = new Image();
    probe.src = `/api/client-beacon/dashboard_app_js_top?t=${Date.now()}`;
  } catch (error) {
    // Ignore telemetry failures.
  }
})();

const form = document.getElementById("guest-form");
const importForm = document.getElementById("import-form");
const importMessage = document.getElementById("import-message");
const message = document.getElementById("form-message");
const guestList = document.getElementById("guest-list");
const template = document.getElementById("guest-card-template");
const refreshButton = document.getElementById("refresh-button");
const exportButton = document.getElementById("export-button");
const bulkResearchButton = document.getElementById("bulk-research-button");
const bulkResearchMessage = document.getElementById("bulk-research-message");
const decisionFilter = document.getElementById("decision-filter");
const guestSearch = document.getElementById("guest-search");
const guestSort = document.getElementById("guest-sort");
const guestResultsMeta = document.getElementById("guest-results-meta");
const guestLoadMoreButton = document.getElementById("guest-load-more");
const guestPresetButtons = Array.from(document.querySelectorAll("[data-guest-preset]"));
const IS_FILE_PROTOCOL = window.location.protocol === "file:";

const GUEST_PAGE_SIZE = 12;
const GUEST_PAYLOAD_CACHE_KEY = "mirror-talk-dashboard-payload";

// Initialize performance utilities with safe fallbacks so dashboard data
// still loads even if performance-utils.js fails to initialize.
const perfUtils = window.PerformanceUtils || {};
const debounceUtil = perfUtils.debounce || ((fn) => fn);
const throttleUtil = perfUtils.throttle || ((fn) => fn);
const RequestDeduplicatorCtor = perfUtils.RequestDeduplicator || class {
  async dedupe(_key, requestFn) {
    return requestFn();
  }
};
const LoadingStateManagerCtor = perfUtils.LoadingStateManager || class {
  async wrap(_element, asyncFn, _options = {}) {
    return asyncFn();
  }
};
const SmartCacheCtor = perfUtils.SmartCache || class {
  constructor(_options = {}) {}
  prune() {}
};
const KeyboardShortcutManagerCtor = perfUtils.KeyboardShortcutManager || class {
  register(_shortcut, _handler, _description = "") {}
  enable() {}
  getShortcuts() {
    return [];
  }
};
const OptimisticUpdateManagerCtor = perfUtils.OptimisticUpdateManager || class {
  async apply(_id, optimisticFn, actualFn, _rollbackFn) {
    optimisticFn();
    return actualFn();
  }
};
const retryWithBackoffFn = perfUtils.retryWithBackoff || (async (fn) => fn());
const getUserFriendlyErrorFn = perfUtils.getUserFriendlyError || ((error) => {
  if (!error) return "An unknown error occurred";
  return error.message || String(error);
});

const requestDeduplicator = (() => {
  try {
    return new RequestDeduplicatorCtor();
  } catch (error) {
    console.error("Dashboard init warning: RequestDeduplicator unavailable", error);
    return { dedupe: (_key, requestFn) => requestFn() };
  }
})();

const loadingManager = (() => {
  try {
    return new LoadingStateManagerCtor();
  } catch (error) {
    console.error("Dashboard init warning: LoadingStateManager unavailable", error);
    return {
      wrap: async (_element, asyncFn, _options = {}) => asyncFn(),
    };
  }
})();

const smartCache = (() => {
  try {
    return new SmartCacheCtor({ maxSize: 100, defaultTTL: 5 * 60 * 1000 });
  } catch (error) {
    console.error("Dashboard init warning: SmartCache unavailable", error);
    return { prune: () => {} };
  }
})();

const keyboardManager = (() => {
  try {
    return new KeyboardShortcutManagerCtor();
  } catch (error) {
    console.error("Dashboard init warning: KeyboardShortcutManager unavailable", error);
    return {
      register: (_shortcut, _handler, _description = "") => {},
      enable: () => {},
      getShortcuts: () => [],
    };
  }
})();

const optimisticManager = (() => {
  try {
    return new OptimisticUpdateManagerCtor();
  } catch (error) {
    console.error("Dashboard init warning: OptimisticUpdateManager unavailable", error);
    return {
      apply: async (_id, optimisticFn, actualFn, _rollbackFn) => {
        optimisticFn();
        return actualFn();
      },
    };
  }
})();

const metrics = {
  total: document.getElementById("metric-total"),
  processed: document.getElementById("metric-processed"),
  unprocessed: document.getElementById("metric-unprocessed"),
};

const insights = {
  accepted: document.getElementById("insight-accepted"),
  rejected: document.getElementById("insight-rejected"),
  skipped: document.getElementById("insight-skipped"),
  acceptanceRate: document.getElementById("insight-acceptance-rate"),
};

const recommendationInsights = {
  strongFits: document.getElementById("ai-strong-fits"),
  reviewQueue: document.getElementById("ai-review-queue"),
  highRisk: document.getElementById("ai-high-risk"),
  averageScore: document.getElementById("ai-average-score"),
};

let emailEnabled = false;
let latestPayload = null;
let activeEmailComposer = null;
let activeGuestEditor = null;
let activeGuestPreset = "all";
let activeGuestActionFeedback = null;
let visibleGuestCount = GUEST_PAGE_SIZE;
let payloadHasFullEnrichment = false;
let fullHydrationInFlight = false;
const AI_HEAVY_PRESETS = new Set(["ai_strong_fit", "ai_review", "ai_risky"]);

function emitClientBeacon(phase) {
  try {
    const probe = new Image();
    probe.src = `/api/client-beacon/dashboard_app_${encodeURIComponent(phase)}?t=${Date.now()}`;
  } catch (error) {
    // Never block dashboard on telemetry.
  }
}

emitClientBeacon("app_js_evaluated");

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

function buildGuestScopedLink(path, guest) {
  const query = encodeURIComponent(guest.full_name || guest.email || "");
  return `${path}?q=${query}`;
}

function composerFeedbackMarkup(feedback) {
  if (!feedback?.text) {
    return "";
  }

  return `<p class="composer-feedback ${feedback.tone || ""}">${escapeHtml(feedback.text)}</p>`;
}

function editorFeedbackMarkup(feedback) {
  if (!feedback?.text) {
    return "";
  }

  return `<p class="composer-feedback ${feedback.tone || ""}">${escapeHtml(feedback.text)}</p>`;
}

function actionFeedbackMarkup(feedback) {
  if (!feedback?.text) {
    return "";
  }

  return `<p class="composer-feedback ${feedback.tone || ""}">${escapeHtml(feedback.text)}</p>`;
}

function confirmCriticalAction(message) {
  return window.confirm(message);
}

async function fetchJSON(url, options = {}) {
  const isReadRequest = !options.method || String(options.method).toUpperCase() === "GET";
  
  // Deduplicate GET requests
  if (isReadRequest && requestDeduplicator) {
    const cacheKey = `${url}_${JSON.stringify(options)}`;
    return requestDeduplicator.dedupe(cacheKey, async () => {
      return await fetchJSONInternal(url, options);
    });
  }
  
  return await fetchJSONInternal(url, options);
}

async function fetchJSONInternal(url, options = {}) {
  const isReadRequest = !options.method || String(options.method).toUpperCase() === "GET";
  
  // Use retry with backoff for better reliability
  return await retryWithBackoffFn(
    async () => {
      const response = await fetch(url, {
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        ...options,
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
        const error = new Error(data.error || "Request failed");
        error.status = response.status;
        error.userMessage = getUserFriendlyErrorFn(error);
        throw error;
      }
      return data;
    },
    {
      maxRetries: isReadRequest ? 2 : 1,
      baseDelay: 350,
      shouldRetry: (error, attempt) => {
        // Retry on network errors and 5xx server errors
        return isReadRequest && (!error.status || error.status >= 500);
      }
    }
  );
}

async function fetchUpload(url, formData) {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    body: formData,
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Upload failed");
  }
  return data;
}

async function fetchTemplate(url, payload) {
  return fetchJSON(url, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

function setMessage(text, tone = "") {
  if (!message) {
    return;
  }
  message.textContent = text;
  message.className = `message ${tone}`.trim();
}

function setImportMessage(text, tone = "") {
  if (!importMessage) {
    return;
  }
  importMessage.textContent = text;
  importMessage.className = `message ${tone}`.trim();
}

function setBulkResearchMessage(text, tone = "") {
  if (!bulkResearchMessage) {
    return;
  }
  bulkResearchMessage.textContent = text;
  bulkResearchMessage.className = `message ${tone}`.trim();
}

function guestStatusLabel(guest) {
  if (guest.dashboard_status_label) {
    return guest.dashboard_status_label;
  }
  if (guest.email_status) {
    return guest.email_status;
  }
  return guest.is_processed ? "processed" : "unprocessed";
}

function normalizeText(value) {
  return String(value || "").trim().toLowerCase();
}

function guestMatchesFilter(guest, filterValue) {
  if (filterValue === "all") {
    return true;
  }

  if (filterValue === "processed") {
    return Boolean(guest.dashboard_processed ?? guest.is_processed);
  }

  if (filterValue === "unprocessed") {
    return !Boolean(guest.dashboard_processed ?? guest.is_processed);
  }

  return guestStatusLabel(guest) === filterValue;
}

function guestMatchesSearch(guest, query) {
  if (!query) {
    return true;
  }

  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) {
    return true;
  }

  const haystack = [
    guest.full_name,
    guest.email,
    guest.website,
    guest.profession,
    guest.original_file_name,
    guest.background,
    guest.passionate_topics,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  return haystack.includes(normalizedQuery);
}

function guestMatchesPreset(guest, preset) {
  const support = guest.decision_support || {};
  if (preset === "all") return true;
  if (preset === "needs_review") return !Boolean(guest.dashboard_processed ?? guest.is_processed);
  if (preset === "ai_strong_fit") return support.suggested_decision === "approve";
  if (preset === "ai_review") return support.suggested_decision === "review";
  if (preset === "ai_risky") return support.suggested_decision === "decline";
  if (preset === "research_failed") return guest.guest_research?.cache_status === "failed";
  if (preset === "accepted") return guestStatusLabel(guest) === "accepted";
  if (preset === "rejected") return guestStatusLabel(guest) === "rejected";
  if (preset === "no_email") return !normalizeText(guest.email);
  return true;
}

function hasFullEnrichment(payload) {
  const guests = payload?.guests || [];
  if (!guests.length) return false;
  return guests.some((guest) => Boolean(guest.promotion_profile) || Boolean(guest.guest_recommendation_support?.score));
}

function guestSortRank(guest) {
  const status = guestStatusLabel(guest);
  if (status === "accepted") return 0;
  if (status === "rejected") return 1;
  if (status === "skipped") return 2;
  if (status === "processed") return 3;
  return 4;
}

function sortGuests(guests, sortMode) {
  const sorted = [...guests];
  sorted.sort((left, right) => {
    if (sortMode === "recommendation") {
      const scoreDifference = Number(right.decision_support?.score || 0) - Number(left.decision_support?.score || 0);
      if (scoreDifference !== 0) {
        return scoreDifference;
      }
      return Number(right.id || 0) - Number(left.id || 0);
    }
    if (sortMode === "name") {
      return String(left.full_name || "").localeCompare(String(right.full_name || ""));
    }
    if (sortMode === "decision") {
      const rankDifference = guestSortRank(left) - guestSortRank(right);
      if (rankDifference !== 0) {
        return rankDifference;
      }
      return String(left.full_name || "").localeCompare(String(right.full_name || ""));
    }
    if (sortMode === "oldest") {
      return Number(left.id || 0) - Number(right.id || 0);
    }
    return Number(right.id || 0) - Number(left.id || 0);
  });
  return sorted;
}

function updateResultsMeta(shown, total, visible) {
  if (!total) {
    guestResultsMeta.textContent = "No guests in the pipeline yet.";
    return;
  }
  if (shown === total && visible === shown) {
    guestResultsMeta.textContent = `Showing all ${total} guest${total === 1 ? "" : "s"}.`;
    return;
  }
  const moreText = visible < shown ? ` Displaying ${visible} right now.` : "";
  guestResultsMeta.textContent = `Showing ${shown} of ${total} guests after the current view controls.${moreText}`;
}

function updateGuestPresetButtons() {
  guestPresetButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.guestPreset === activeGuestPreset);
  });
}

function recommendationTone(support) {
  const decision = support?.suggested_decision;
  if (decision === "approve") return "good";
  if (decision === "decline") return "warning";
  return "neutral";
}

function normalizeClipboardValue(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value).trim();
}

function parseOriginalData(guest) {
  if (!guest.original_data) {
    return {};
  }

  try {
    const parsed = JSON.parse(guest.original_data);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (error) {
    return {};
  }
}

function buildIntakeClipboardText(guest) {
  const original = parseOriginalData(guest);
  const sections = [
    ["Full Name", guest.full_name],
    ["Email", guest.email],
    ["Website", guest.website],
    ["Profession", guest.profession || original.profession],
    ["Social Media Handles", guest.social_handles || original.social_handles || original.social_media_handles],
    ["Background", guest.background || original.background],
    ["Motivation", guest.motivation || original.motivation],
    ["Life Experiences", guest.life_experiences || original.life_experiences],
    ["Core Values", guest.core_values || original.core_values],
    ["Favorite Quote", guest.favorite_quote || original.favorite_quote],
    ["Faith / Practice", guest.faith || original.faith],
    ["Beliefs Align", guest.alignment || original.alignment],
    ["Passionate Topics", guest.passionate_topics || original.passionate_topics],
    ["Message / Takeaway", guest.message || original.message],
    ["Previous Podcast / Speaking Experience", guest.experience || original.experience],
    ["Additional Info", guest.additional_info || original.additional_info],
    ["Following Mirror Talk", guest.has_social_media || original.has_social_media],
    ["Source", guest.original_file_name],
    ["Status", guestStatusLabel(guest)],
    ["Skip Reason", guest.skip_reason],
  ];

  return sections
    .map(([label, value]) => [label, normalizeClipboardValue(value)])
    .filter(([, value]) => value)
    .map(([label, value]) => `${label}:\n${value}`)
    .join("\n\n");
}

function parseSocialHandleEntries(rawValue) {
  const text = String(rawValue || "").trim();
  if (!text) {
    return [];
  }

  return text
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const labeledMatch = line.match(/^([^:]+):\s*(.+)$/);
      if (labeledMatch) {
        return {
          label: labeledMatch[1].trim(),
          value: labeledMatch[2].trim(),
        };
      }

      const inferredLabel = /^https?:\/\//i.test(line) || /\s/.test(line) ? "Other" : "Unspecified";

      return {
        label: inferredLabel,
        value: line,
      };
    });
}

function socialValueToUrl(label, value) {
  const trimmedValue = String(value || "").trim();
  if (!trimmedValue) {
    return "";
  }

  if (/^https?:\/\//i.test(trimmedValue)) {
    return trimmedValue;
  }

  const cleanedHandle = trimmedValue.replace(/^@/, "");
  const normalizedLabel = String(label || "").trim().toLowerCase();

  if (normalizedLabel === "instagram") return `https://www.instagram.com/${cleanedHandle}`;
  if (normalizedLabel === "youtube") return cleanedHandle.startsWith("@") ? `https://www.youtube.com/${trimmedValue}` : `https://www.youtube.com/@${cleanedHandle}`;
  if (normalizedLabel === "x/twitter") return `https://x.com/${cleanedHandle}`;
  if (normalizedLabel === "facebook") return `https://www.facebook.com/${cleanedHandle}`;
  if (normalizedLabel === "tiktok") return `https://www.tiktok.com/@${cleanedHandle}`;
  if (normalizedLabel === "linkedin") {
    if (/^linkedin\.com\//i.test(trimmedValue)) {
      return `https://${trimmedValue}`;
    }
    return "";
  }

  return "";
}

function renderSocialHandlesMarkup(rawValue) {
  const entries = parseSocialHandleEntries(rawValue);
  if (!entries.length) {
    return "";
  }

  return `
    <div class="social-detail-list">
      ${entries
        .map((entry) => {
          const url = socialValueToUrl(entry.label, entry.value);
          const valueMarkup = url
            ? `<a class="inline-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(entry.value)}</a>`
            : escapeHtml(entry.value);
          const toneClass = entry.label === "Unspecified" ? " ambiguous" : "";
          return `<span class="social-chip${toneClass}"><strong>${escapeHtml(entry.label)}:</strong> ${valueMarkup}</span>`;
        })
        .join("")}
    </div>
  `;
}

function renderSubmissionMetaMarkup(meta) {
  if (!meta?.mode) {
    return "";
  }

  const details = [`Submission Mode: ${meta.label || meta.mode}`];
  if (meta.agency_name) details.push(`Agency: ${meta.agency_name}`);
  if (meta.agency_email) details.push(`Agency Email: ${meta.agency_email}`);
  if (meta.personal_application_status) details.push(`Personal Application: ${meta.personal_application_status}`);

  return `
    <div class="submission-detail-list">
      ${details.map((detail) => `<span>${linkifyText(detail)}</span>`).join("")}
    </div>
  `;
}

function renderBookingOverrideMarkup(override) {
  if (!override || typeof override !== "object") {
    return "";
  }

  const details = [];
  if (override.timezone) details.push(`Booking Override Timezone: ${override.timezone}`);
  if (Array.isArray(override.weekdays) && override.weekdays.length) details.push(`Booking Override Days: ${override.weekdays.join(", ")}`);
  if (Array.isArray(override.slot_times) && override.slot_times.length) details.push(`Booking Override Times: ${override.slot_times.join(", ")}`);
  if (override.min_notice_hours) details.push(`Booking Override Min Notice: ${override.min_notice_hours} hours`);
  if (override.days_ahead) details.push(`Booking Override Window: ${override.days_ahead} days`);

  if (!details.length) {
    return "";
  }

  return `
    <div class="submission-detail-list">
      ${details.map((detail) => `<span>${linkifyText(detail)}</span>`).join("")}
    </div>
  `;
}

function renderPromotionProfile(guest) {
  const profile = guest.promotion_profile;
  if (!profile) {
    return "";
  }
  const strengths = (profile.strengths || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const gaps = (profile.gaps || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  return `
    <div class="guest-ai-card guest-promotion-card">
      <div class="guest-ai-head">
        <div>
          <div class="guest-ai-title-row">
            <strong>Promotion Profile</strong>
            <span class="guest-ai-badge ${profile.score >= 80 ? "good" : profile.score >= 55 ? "" : "warning"}">${escapeHtml(profile.label)}</span>
          </div>
          <p class="guest-ai-copy">Score: ${profile.score}/100</p>
        </div>
      </div>
      <div class="guest-ai-grid">
        ${strengths ? `<div class="guest-ai-block"><strong>Ready signals</strong><ul>${strengths}</ul></div>` : ""}
        ${gaps ? `<div class="guest-ai-block caution"><strong>Outreach gaps</strong><ul>${gaps}</ul></div>` : ""}
      </div>
    </div>
  `;
}

function formatPlanningDate(value) {
  if (!value) {
    return "";
  }
  const parsed = new Date(value.includes("T") ? value : value.replace(" ", "T"));
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function renderGuestPlanningSummary(guest) {
  const summary = guest.planning_summary;
  if (!summary) {
    return "";
  }

  const featuredTitle = summary.featured_title || "Linked episode";
  const nextDate = summary.next_scheduled_release_date
    ? `<li><strong>Next scheduled release</strong>: ${escapeHtml(formatPlanningDate(summary.next_scheduled_release_date))}</li>`
    : "";
  const featuredDate = summary.featured_release_date
    ? `<li><strong>Stored release date</strong>: ${escapeHtml(formatPlanningDate(summary.featured_release_date))}</li>`
    : "";
  const featuredEpisodeLink = summary.featured_episode_id
    ? `/planning?tab=release_planning&episode_id=${encodeURIComponent(summary.featured_episode_id)}`
    : buildGuestScopedLink("/planning", guest);

  return `
    <section class="guest-ai-card guest-planning-card">
      <div class="guest-ai-head">
        <div>
          <div class="guest-ai-title-row">
            <strong>Planning Context</strong>
            <span class="guest-ai-badge">${escapeHtml(summary.summary_label || "Linked planning context")}</span>
          </div>
          <p class="guest-ai-copy">${escapeHtml(featuredTitle)}</p>
        </div>
      </div>
      <ul class="guest-planning-meta">
        <li><strong>Release status</strong>: ${escapeHtml(summary.featured_release_status || "unplanned")}</li>
        <li><strong>Production status</strong>: ${escapeHtml(summary.featured_production_status || "idea")}</li>
        ${featuredDate}
        ${nextDate}
      </ul>
      <div class="guest-planning-links">
        <a class="context-link" href="${featuredEpisodeLink}">Open Linked Episode</a>
        <a class="context-link" href="${buildGuestScopedLink("/planning", guest)}">Open In Planning</a>
      </div>
    </section>
  `;
}

function buildGuestResearchSearchUrl(guest) {
  const parts = [];
  const name = String(guest.full_name || "").trim();
  if (name) {
    parts.push(`"${name}"`);
  }

  const website = String(guest.website || "").trim();
  if (website) {
    parts.push(website.replace(/^https?:\/\//i, "").replace(/^www\./i, "").split(/[/?#]/)[0]);
  } else {
    const socialEntries = parseSocialHandleEntries(guest.social_media_handles || guest.social_handles);
    const firstNamedEntry = socialEntries.find((entry) => String(entry.value || "").trim());
    if (firstNamedEntry) {
      parts.push(`"${String(firstNamedEntry.value || "").trim().replace(/^@/, "")}"`);
    }
  }

  if (!parts.length) {
    return "";
  }

  return `https://www.google.com/search?q=${encodeURIComponent(parts.join(" "))}`;
}

function renderResearchRecoveryLinks(guest) {
  const links = [];
  const website = normalizeText(guest.website);
  if (website) {
    links.push({
      label: "Open website",
      url: /^https?:\/\//i.test(website) ? website : `https://${website}`,
    });
  }

  parseSocialHandleEntries(guest.social_media_handles || guest.social_handles)
    .slice(0, 3)
    .forEach((entry) => {
      const url = socialValueToUrl(entry.label, entry.value);
      if (url) {
        links.push({
          label: `Open ${entry.label}`,
          url,
        });
      }
    });

  const googleSearchUrl = buildGuestResearchSearchUrl(guest);
  if (googleSearchUrl) {
    links.push({
      label: "Google search",
      url: googleSearchUrl,
    });
  }

  const uniqueLinks = [];
  const seen = new Set();
  links.forEach((link) => {
    const key = `${link.label}|${link.url}`;
    if (!link.url || seen.has(key)) {
      return;
    }
    seen.add(key);
    uniqueLinks.push(link);
  });

  if (!uniqueLinks.length) {
    return "";
  }

  return `
    <div class="guest-ai-block">
      <strong>Recovery links</strong>
      <p class="guest-ai-copy">Use these to verify the right public profile before retrying research.</p>
      <p class="guest-ai-copy">
        ${uniqueLinks.map((link) => `<a class="inline-link" href="${escapeHtml(link.url)}" target="_blank" rel="noopener">${escapeHtml(link.label)}</a>`).join(" · ")}
      </p>
    </div>
  `;
}

function isLowSignalResearchSource(source) {
  const values = [source?.title, source?.description, source?.heading]
    .map((value) => normalizeText(value))
    .filter(Boolean);
  if (!values.length) {
    return false;
  }
  const genericLabels = new Set(["facebook", "instagram"]);
  return values.every((value) => genericLabels.has(value));
}

function renderGuestCopilotSummary(guest) {
  const research = guest.guest_research;
  if (!research) {
    return "";
  }
  if (research.cache_status === "failed") {
    const failureReason = normalizeText(research.last_error) || "The available public profile source could not be read cleanly.";
    const freshness = research.freshness || {};
    return `
      <div class="guest-ai-card">
        <div class="guest-ai-head">
          <div>
            <p class="composer-eyebrow">Guest Copilot Research</p>
            <div class="guest-ai-title-row">
              <strong>Research failed</strong>
              <span class="guest-ai-badge warning">Needs source fix</span>
            </div>
            <p class="guest-ai-copy">${escapeHtml(failureReason)}</p>
            ${freshness.label ? `<p class="guest-ai-copy">Last attempt: ${escapeHtml(freshness.label)}</p>` : ""}
          </div>
        </div>
        <div class="guest-ai-grid">
        <div class="guest-ai-block caution">
          <strong>What to do next</strong>
          <ul>
              <li>Check whether the website or social profile field is missing, malformed, or blocked.</li>
              <li>Update the guest details, then use <strong>Retry With Search</strong> to rescue the profile intentionally.</li>
            </ul>
          </div>
          ${renderResearchRecoveryLinks(guest)}
        </div>
      </div>
    `;
  }
  if (!research.summary && !(research.likely_topics || []).length) {
    return "";
  }

  const topics = (research.likely_topics || []).slice(0, 4).map((item) => `<span class="signal-chip good">${escapeHtml(item)}</span>`).join("");
  const signals = (research.timely_signals || []).slice(0, 3).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const sources = (research.sources || [])
    .filter((source) => !isLowSignalResearchSource(source))
    .slice(0, 3)
    .map((source) => {
      const label = source.title || source.host || source.url || "Public source";
      const url = source.url || "";
      const evidence = (source.evidence || []).slice(0, 1).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
      return `
        <div class="guest-ai-block">
          <strong>${url ? `<a class="inline-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>` : escapeHtml(label)}</strong>
          ${evidence ? `<ul>${evidence}</ul>` : ""}
        </div>
      `;
    })
    .join("");
  const mode = normalizeText(research.research_mode) || "manual";
  const freshness = research.freshness || {};

  return `
    <div class="guest-ai-card">
      <div class="guest-ai-head">
        <div>
          <p class="composer-eyebrow">Guest Copilot Research</p>
          <div class="guest-ai-title-row">
            <strong>Public profile evidence</strong>
            <span class="guest-ai-badge">${escapeHtml(mode === "auto" ? "Auto" : "Manual")}</span>
          </div>
          <p class="guest-ai-copy">${escapeHtml(research.summary || "Public profile context is available for planning and drafting.")}</p>
          ${freshness.label ? `<p class="guest-ai-copy">Freshness: ${escapeHtml(freshness.label)}</p>` : ""}
        </div>
      </div>
      ${topics ? `<div class="signal-list guest-ai-signals">${topics}</div>` : ""}
      <div class="guest-ai-grid">
        ${signals ? `<div class="guest-ai-block"><strong>Useful planning angles</strong><ul>${signals}</ul></div>` : ""}
        ${sources ? `<div class="guest-ai-block"><strong>Public sources checked</strong><div class="guest-ai-grid">${sources}</div></div>` : ""}
      </div>
    </div>
  `;
}

async function copyGuestIntake(guest) {
  const clipboardText = buildIntakeClipboardText(guest);
  if (!clipboardText) {
    throw new Error("No intake details available to copy.");
  }

  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(clipboardText);
    return;
  }

  const helper = document.createElement("textarea");
  helper.value = clipboardText;
  helper.setAttribute("readonly", "");
  helper.style.position = "absolute";
  helper.style.left = "-9999px";
  document.body.appendChild(helper);
  helper.select();

  try {
    document.execCommand("copy");
  } finally {
    document.body.removeChild(helper);
  }
}

function renderInlineEditor(editorNode, guest) {
  if (!activeGuestEditor || activeGuestEditor.guestId !== guest.id) {
    editorNode.classList.add("hidden");
    editorNode.innerHTML = "";
    return;
  }

  editorNode.classList.remove("hidden");
  editorNode.innerHTML = `
    <div class="inline-editor-title">Edit Guest</div>
    <form class="inline-editor-form">
      <label>
        Full Name
        <input name="full_name" type="text" value="${escapeHtml(activeGuestEditor.full_name)}" required />
      </label>
      <label>
        Email
        <input name="email" type="email" value="${escapeHtml(activeGuestEditor.email)}" />
      </label>
      <label>
        Website
        <input name="website" type="text" inputmode="url" autocapitalize="off" spellcheck="false" value="${escapeHtml(activeGuestEditor.website)}" />
      </label>
      <label>
        Profession
        <input name="profession" type="text" value="${escapeHtml(activeGuestEditor.profession)}" />
      </label>
      <label class="full-width">
        Social Handles
        <input name="social_handles" type="text" value="${escapeHtml(activeGuestEditor.social_handles)}" />
      </label>
      <label class="full-width">
        Background
        <textarea name="background" rows="3">${escapeHtml(activeGuestEditor.background)}</textarea>
      </label>
      <label class="full-width">
        Passionate Topics
        <textarea name="passionate_topics" rows="3">${escapeHtml(activeGuestEditor.passionate_topics)}</textarea>
      </label>
      <label>
        Booking Override Timezone
        <input name="booking_override_timezone" type="text" value="${escapeHtml(activeGuestEditor.booking_override_timezone)}" placeholder="e.g. America/Phoenix" />
      </label>
      <label>
        Booking Override Days
        <input name="booking_override_weekdays" type="text" value="${escapeHtml(activeGuestEditor.booking_override_weekdays)}" placeholder="e.g. WE" />
      </label>
      <label class="full-width">
        Booking Override Times
        <input name="booking_override_slot_times" type="text" value="${escapeHtml(activeGuestEditor.booking_override_slot_times)}" placeholder="e.g. 10:00,11:00,12:00,13:00,14:00" />
      </label>
      <label>
        Booking Override Window (days)
        <input name="booking_override_days_ahead" type="number" min="7" max="180" value="${escapeHtml(activeGuestEditor.booking_override_days_ahead)}" />
      </label>
      <label>
        Booking Override Min Notice (hours)
        <input name="booking_override_min_notice_hours" type="number" min="2" max="168" value="${escapeHtml(activeGuestEditor.booking_override_min_notice_hours)}" />
      </label>
      ${editorFeedbackMarkup(activeGuestEditor.feedback)}
      <div class="inline-editor-actions full-width">
        <button type="submit" class="primary-button small-button" ${activeGuestEditor.saving ? "disabled" : ""}>
          ${activeGuestEditor.saving ? "Saving..." : "Save Changes"}
        </button>
        <button type="button" data-editor-action="cancel" class="ghost-button small-button" ${activeGuestEditor.saving ? "disabled" : ""}>Cancel</button>
      </div>
    </form>
  `;

  const formNode = editorNode.querySelector("form");
  formNode.querySelectorAll("input, textarea").forEach((field) => {
    field.addEventListener("input", (event) => {
      activeGuestEditor[event.target.name] = event.target.value;
    });
  });

  editorNode.querySelector("[data-editor-action='cancel']").addEventListener("click", () => {
    activeGuestEditor = null;
    renderGuests(latestPayload);
  });

  formNode.addEventListener("submit", async (event) => {
    event.preventDefault();
    activeGuestEditor.saving = true;
    activeGuestEditor.feedback = { text: `Saving ${guest.full_name || "guest"}...`, tone: "pending" };
    renderGuests(latestPayload);
    try {
      await fetchJSON(`/api/guests/${guest.id}`, {
        method: "POST",
        body: JSON.stringify({
          full_name: activeGuestEditor.full_name,
          email: activeGuestEditor.email,
          website: activeGuestEditor.website,
          profession: activeGuestEditor.profession,
          social_handles: activeGuestEditor.social_handles,
          background: activeGuestEditor.background,
          passionate_topics: activeGuestEditor.passionate_topics,
          booking_override: {
            timezone: activeGuestEditor.booking_override_timezone,
            weekdays: activeGuestEditor.booking_override_weekdays,
            slot_times: activeGuestEditor.booking_override_slot_times,
            days_ahead: activeGuestEditor.booking_override_days_ahead,
            min_notice_hours: activeGuestEditor.booking_override_min_notice_hours,
          },
        }),
      });
      activeGuestEditor = null;
      setMessage(`Updated ${guest.full_name || "guest"}.`, "success");
      await loadGuests();
    } catch (error) {
      activeGuestEditor.saving = false;
      activeGuestEditor.feedback = { text: error.message, tone: "error" };
      renderGuests(latestPayload);
      setMessage(error.message, "error");
    }
  });
}

function renderGuests(payload) {
  latestPayload = payload;
  emailEnabled = Boolean(payload.email_enabled);
  if (metrics.total) {
    metrics.total.textContent = payload.stats.total ?? 0;
  }
  if (metrics.processed) {
    metrics.processed.textContent = payload.stats.processed ?? 0;
  }
  if (metrics.unprocessed) {
    metrics.unprocessed.textContent = payload.stats.unprocessed ?? 0;
  }

  const accepted = payload.email_stats.accepted_emails ?? 0;
  const rejected = payload.email_stats.rejected_emails ?? 0;
  const skipped = payload.email_stats.skipped_guests ?? 0;
  const decided = accepted + rejected + skipped;

  if (insights.accepted) {
    insights.accepted.textContent = accepted;
  }
  if (insights.rejected) {
    insights.rejected.textContent = rejected;
  }
  if (insights.skipped) {
    insights.skipped.textContent = skipped;
  }
  if (insights.acceptanceRate) {
    insights.acceptanceRate.textContent = decided ? `${Math.round((accepted / decided) * 100)}%` : "0%";
  }
  if (recommendationInsights.strongFits) {
    recommendationInsights.strongFits.textContent = payload.recommendation_stats?.strong_fits ?? 0;
  }
  if (recommendationInsights.reviewQueue) {
    recommendationInsights.reviewQueue.textContent = payload.recommendation_stats?.review_queue ?? 0;
  }
  if (recommendationInsights.highRisk) {
    recommendationInsights.highRisk.textContent = payload.recommendation_stats?.high_risk ?? 0;
  }
  if (recommendationInsights.averageScore) {
    recommendationInsights.averageScore.textContent = payload.recommendation_stats?.average_score ?? 0;
  }

  const filteredGuests = sortGuests(
    payload.guests.filter((guest) => {
      return (
        guestMatchesPreset(guest, activeGuestPreset) &&
        guestMatchesFilter(guest, decisionFilter.value) &&
        guestMatchesSearch(guest, guestSearch.value)
      );
    }),
    guestSort.value,
  );
  const visibleGuests = filteredGuests.slice(0, visibleGuestCount);

  guestList.innerHTML = "";
  updateGuestPresetButtons();
  updateResultsMeta(filteredGuests.length, payload.guests.length, visibleGuests.length);

  if (!filteredGuests.length) {
    if (payload.guests.length) {
      guestList.innerHTML = "<p class='guest-summary'>No guests match the current dashboard view. Try a different preset, search, or decision filter.</p>";
    } else {
      guestList.innerHTML = "<p class='guest-summary'>No guests yet. Add the first one with the form.</p>";
    }
    guestLoadMoreButton.classList.add("hidden");
    return;
  }

  visibleGuests.forEach((guest) => {
    const node = template.content.cloneNode(true);
    const statusPill = node.querySelector(".status-pill");
    const composer = node.querySelector(".email-composer");
    const editor = node.querySelector(".inline-editor");
    const actionFeedbackNode = node.querySelector(".card-action-feedback");
    const aiSummaryNode = node.querySelector(".guest-ai-summary");
    const copilotSummaryNode = node.querySelector(".guest-copilot-summary");
    const planningSummaryNode = node.querySelector(".guest-planning-summary");
    const promotionSummaryNode = node.querySelector(".guest-promotion-summary");

    node.querySelector(".guest-name").textContent = guest.full_name || "Unnamed Guest";
    node.querySelector(".guest-meta").textContent = guest.email || "No email provided";
    node.querySelector(".guest-summary").textContent =
      guest.background || guest.additional_info || "No background added yet.";
    aiSummaryNode.innerHTML = renderGuestAiSummary(guest);
    copilotSummaryNode.innerHTML = renderGuestCopilotSummary(guest);
    planningSummaryNode.innerHTML = renderGuestPlanningSummary(guest);
    promotionSummaryNode.innerHTML = renderPromotionProfile(guest);

    statusPill.textContent = guestStatusLabel(guest);
    statusPill.classList.add(normalizeText(guest.dashboard_status || guestStatusLabel(guest)).replaceAll(" ", "_"));

    const researchButton = node.querySelector("[data-action='research']");
    const resendBookingLinkButton = node.querySelector("[data-action='resend_booking_link']");
    const resendPersonalApplicationButton = node.querySelector("[data-action='resend_personal_application']");
    const researchFailed = guest.guest_research?.cache_status === "failed";
    if (researchButton && researchFailed) {
      researchButton.textContent = "Retry With Search";
      researchButton.title = "Use Google search results as a rescue path for this failed research record.";
    }
    if (researchButton && !guest.website && !guest.social_media_handles) {
      researchButton.disabled = true;
      researchButton.title = "Add a website or labeled social profile first so copilot research has a public source to read.";
    }
    if (resendBookingLinkButton) {
      const isAccepted = normalizeText(guest.email_status) === "accepted";
      if (!isAccepted) {
        resendBookingLinkButton.classList.add("hidden");
      } else if (!guest.email) {
        resendBookingLinkButton.disabled = true;
        resendBookingLinkButton.title = "Add the guest's email first so Mirror Talk can resend their booking link.";
      }
    }
    if (resendPersonalApplicationButton) {
      const isAgencyReferral = guest.submission_meta?.mode === "agency_referral";
      if (!isAgencyReferral) {
        resendPersonalApplicationButton.classList.add("hidden");
      } else if (!guest.email) {
        resendPersonalApplicationButton.disabled = true;
        resendPersonalApplicationButton.title = "Add the guest's personal email first so Mirror Talk can resend their application link.";
      }
    }

    if (!emailEnabled) {
      node
        .querySelectorAll("[data-action='accepted_email'], [data-action='rejected_email'], [data-action='resend_booking_link'], [data-action='resend_personal_application']")
        .forEach((button) => {
        button.disabled = true;
        button.title = "Set the dashboard SMTP or Resend environment variables on Railway to enable email sending.";
        });
    }

    renderInlineEditor(editor, guest);
    actionFeedbackNode.innerHTML =
      activeGuestActionFeedback?.guestId === guest.id ? actionFeedbackMarkup(activeGuestActionFeedback) : "";

    if (
      activeEmailComposer &&
      activeEmailComposer.guestId === guest.id &&
      (activeEmailComposer.status === "accepted" || activeEmailComposer.status === "rejected")
    ) {
      composer.classList.remove("hidden");
      composer.innerHTML = `
        <div class="composer-header">
          <div>
            <p class="composer-eyebrow">${activeEmailComposer.status === "accepted" ? "Approval Email" : "Decline Email"}</p>
            <h4>${guest.full_name || "Guest"}</h4>
          </div>
          <p class="composer-meta">${guest.email || "No email address"}</p>
        </div>
        <label class="composer-field">
          <span>Subject</span>
          <input type="text" data-composer-field="subject" value="${escapeHtml(activeEmailComposer.subject)}" />
        </label>
        <label class="composer-field">
          <span>Email Body</span>
          <textarea rows="12" data-composer-field="body">${escapeHtml(activeEmailComposer.body)}</textarea>
        </label>
        ${composerFeedbackMarkup(activeEmailComposer.feedback)}
        <div class="composer-actions">
          <button type="button" data-composer-action="send" class="primary-button small-button" ${activeEmailComposer.sending ? "disabled" : ""}>
            ${activeEmailComposer.sending ? "Sending..." : "Send Email"}
          </button>
          <button type="button" data-composer-action="cancel" class="ghost-button small-button" ${activeEmailComposer.sending ? "disabled" : ""}>Cancel</button>
        </div>
      `;

      composer.querySelectorAll("[data-composer-field]").forEach((field) => {
        field.addEventListener("input", (event) => {
          activeEmailComposer[event.target.dataset.composerField] = event.target.value;
        });
      });

      composer.querySelector("[data-composer-action='cancel']").addEventListener("click", () => {
        activeEmailComposer = null;
        renderGuests(latestPayload);
      });

      composer.querySelector("[data-composer-action='send']").addEventListener("click", async () => {
        const guestLabel = guest.full_name || "guest";
        if (!confirmCriticalAction(`Send this ${activeEmailComposer.status === "accepted" ? "approval" : "decline"} email to ${guestLabel}?`)) {
          return;
        }
        activeEmailComposer.sending = true;
        activeEmailComposer.feedback = {
          text: activeEmailComposer.status === "accepted"
            ? `Sending approval email to ${guest.full_name || "guest"}...`
            : `Sending decline email to ${guest.full_name || "guest"}...`,
          tone: "pending",
        };
        renderGuests(latestPayload);

        try {
          await fetchJSON(`/api/guests/${guest.id}/email-decision`, {
            method: "POST",
            body: JSON.stringify({
              status: activeEmailComposer.status,
              subject: activeEmailComposer.subject,
              body: activeEmailComposer.body,
            }),
          });
          setMessage(
            activeEmailComposer.status === "accepted"
              ? `Sent approval email to ${guest.full_name}.`
              : `Sent decline email to ${guest.full_name}.`,
            "success",
          );
          activeEmailComposer.feedback = {
            text: activeEmailComposer.status === "accepted"
              ? `Approval email sent to ${guest.full_name || "guest"}.`
              : `Decline email sent to ${guest.full_name || "guest"}.`,
            tone: "success",
          };
          activeEmailComposer.sending = false;
          renderGuests(latestPayload);
          await new Promise((resolve) => window.setTimeout(resolve, 900));
          activeEmailComposer = null;
          await loadGuests();
        } catch (error) {
          activeEmailComposer.sending = false;
          activeEmailComposer.feedback = {
            text: error.message,
            tone: "error",
          };
          renderGuests(latestPayload);
          setMessage(error.message, "error");
        }
      });
    }

    const details = [];
    if (guest.profession) details.push(`Profession: ${guest.profession}`);
    if (guest.website) details.push(`Website: ${guest.website}`);
    const socialHandles = guest.social_media_handles;
    if (socialHandles) {
      details.push(`Social media available`);
    }
    if (guest.passionate_topics) details.push(`Topics: ${guest.passionate_topics}`);
    if (guest.original_file_name) details.push(`Source: ${guest.original_file_name}`);
    node.querySelector(".guest-details").innerHTML = details.map((detail) => `<span>${linkifyText(detail)}</span>`).join("");
    if (socialHandles) {
      node.querySelector(".guest-details").insertAdjacentHTML("beforeend", renderSocialHandlesMarkup(socialHandles));
    }
    node.querySelector(".guest-details").insertAdjacentHTML("beforeend", renderSubmissionMetaMarkup(guest.submission_meta));
    node.querySelector(".guest-details").insertAdjacentHTML("beforeend", renderBookingOverrideMarkup(guest.booking_override));
    node.querySelector(".guest-details").insertAdjacentHTML(
      "beforeend",
      `
        <div class="context-links">
          <a class="context-link" href="${buildGuestScopedLink("/operations", guest)}">Open In Operations</a>
          <a class="context-link" href="${buildGuestScopedLink("/planning", guest)}">Open In Planning</a>
        </div>
      `,
    );

    node.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", async () => {
        const action = button.dataset.action;

        try {
          if (action === "edit") {
            activeEmailComposer = null;
            activeGuestEditor = {
              guestId: guest.id,
              full_name: guest.full_name || "",
              email: guest.email || "",
              website: guest.website || "",
              profession: guest.profession || "",
              social_handles: guest.social_media_handles || "",
              background: guest.background || "",
              passionate_topics: guest.passionate_topics || "",
              booking_override_timezone: guest.booking_override?.timezone || "",
              booking_override_weekdays: Array.isArray(guest.booking_override?.weekdays) ? guest.booking_override.weekdays.join(",") : "",
              booking_override_slot_times: Array.isArray(guest.booking_override?.slot_times) ? guest.booking_override.slot_times.join(",") : "",
              booking_override_days_ahead: guest.booking_override?.days_ahead || "",
              booking_override_min_notice_hours: guest.booking_override?.min_notice_hours || "",
              saving: false,
              feedback: null,
            };
            renderGuests(latestPayload);
          } else if (action === "copy") {
            activeGuestActionFeedback = { guestId: guest.id, text: `Copying ${guest.full_name || "guest"}...`, tone: "pending" };
            renderGuests(latestPayload);
            await copyGuestIntake(guest);
            activeGuestActionFeedback = { guestId: guest.id, text: `Copied ${guest.full_name}'s intake details.`, tone: "success" };
            renderGuests(latestPayload);
            setMessage(`Copied ${guest.full_name}'s intake details.`, "success");
          } else if (action === "research") {
            const failedResearch = guest.guest_research?.cache_status === "failed";
            activeGuestActionFeedback = {
              guestId: guest.id,
              text: failedResearch
                ? `Retrying research for ${guest.full_name || "guest"} with search results...`
                : `Researching public profile signals for ${guest.full_name || "guest"}...`,
              tone: "pending",
            };
            renderGuests(latestPayload);
            await fetchJSON(`/api/guests/${guest.id}/${failedResearch ? "research-with-search" : "research"}`, {
              method: "POST",
              body: JSON.stringify({}),
            });
            activeGuestActionFeedback = {
              guestId: guest.id,
              text: failedResearch
                ? `Search-assisted research saved for ${guest.full_name || "guest"}.`
                : `Public profile research saved for ${guest.full_name || "guest"}.`,
              tone: "success",
            };
            renderGuests(latestPayload);
            setMessage(
              failedResearch
                ? `Saved search-assisted profile research for ${guest.full_name}. Planning can now use it as copilot context.`
                : `Saved public profile research for ${guest.full_name}. Planning can now use it as copilot context.`,
              "success",
            );
          } else if (action === "resend_personal_application") {
            if (!confirmCriticalAction(`Resend the personal Mirror Talk application link to ${guest.full_name || guest.email || "this guest"}?`)) {
              return;
            }
            activeGuestActionFeedback = {
              guestId: guest.id,
              text: `Resending the personal application link to ${guest.full_name || guest.email || "guest"}...`,
              tone: "pending",
            };
            renderGuests(latestPayload);
            await fetchJSON(`/api/guests/${guest.id}/resend-personal-application`, {
              method: "POST",
              body: JSON.stringify({}),
            });
            activeGuestActionFeedback = {
              guestId: guest.id,
              text: `Personal application link resent to ${guest.full_name || guest.email || "guest"}.`,
              tone: "success",
            };
            renderGuests(latestPayload);
            setMessage(`Resent the personal application link to ${guest.full_name || guest.email}.`, "success");
          } else if (action === "resend_booking_link") {
            if (!confirmCriticalAction(`Resend the Mirror Talk booking link to ${guest.full_name || guest.email || "this guest"}?`)) {
              return;
            }
            activeGuestActionFeedback = {
              guestId: guest.id,
              text: `Resending the booking link to ${guest.full_name || guest.email || "guest"}...`,
              tone: "pending",
            };
            renderGuests(latestPayload);
            await fetchJSON(`/api/guests/${guest.id}/resend-booking-link`, {
              method: "POST",
              body: JSON.stringify({}),
            });
            activeGuestActionFeedback = {
              guestId: guest.id,
              text: `Booking link resent to ${guest.full_name || guest.email || "guest"}.`,
              tone: "success",
            };
            renderGuests(latestPayload);
            setMessage(`Resent the booking link to ${guest.full_name || guest.email}.`, "success");
          } else if (action === "accepted_email" || action === "rejected_email") {
            activeGuestEditor = null;
            const decision = action === "accepted_email" ? "accepted" : "rejected";
            const templateData = await fetchTemplate(`/api/guests/${guest.id}/email-template`, { status: decision });
            activeEmailComposer = {
              guestId: guest.id,
              status: decision,
              subject: templateData.subject || "",
              body: templateData.body || "",
              sending: false,
              feedback: null,
            };
            renderGuests(latestPayload);
          } else if (action === "ai_email_draft") {
            // AI Email Draft Generation
            const emailType = guest.email_status === "accepted" ? "acceptance" : "acceptance";
            await generateAIEmailDraft(guest.id, emailType);
          } else if (action === "ai_questions") {
            // AI Interview Questions Generation
            await generateInterviewQuestions(guest.id, guest.full_name || "Guest");
          } else if (action === "ai_analysis") {
            // AI Guest Analysis
            await analyzeGuestWithAI(guest.id, guest.full_name || "Guest");
          } else if (action === "delete") {
            const guestLabel = guest.full_name || "guest";
            const needsTypedConfirmation = Boolean(guest.is_processed || guest.email_status);
            if (needsTypedConfirmation) {
              const typedName = window.prompt(`Type "${guestLabel}" to delete this processed guest.`);
              if (typedName === null) {
                return;
              }
              if (typedName.trim() !== guestLabel) {
                setMessage(`Deletion cancelled. Type the full name exactly to remove ${guestLabel}.`, "error");
                return;
              }
              activeGuestActionFeedback = { guestId: guest.id, text: `Deleting ${guestLabel}...`, tone: "pending" };
              renderGuests(latestPayload);
              await fetchJSON(`/api/guests/${guest.id}`, {
                method: "DELETE",
                body: JSON.stringify({ confirm_name: typedName.trim() }),
              });
            } else {
              if (!window.confirm(`Delete ${guestLabel} from the dashboard?`)) {
                return;
              }
              activeGuestActionFeedback = { guestId: guest.id, text: `Deleting ${guestLabel}...`, tone: "pending" };
              renderGuests(latestPayload);
              await fetchJSON(`/api/guests/${guest.id}`, {
                method: "DELETE",
                body: JSON.stringify({}),
              });
            }
            activeGuestActionFeedback = null;
            setMessage(`Deleted ${guestLabel}.`, "success");
          } else if (action === "skipped") {
            const skipReason = window.prompt("Optional skip reason:") || "";
            activeGuestActionFeedback = { guestId: guest.id, text: `Skipping ${guest.full_name || "guest"}...`, tone: "pending" };
            renderGuests(latestPayload);
            await fetchJSON(`/api/guests/${guest.id}/status`, {
              method: "POST",
              body: JSON.stringify({ status: action, skip_reason: skipReason }),
            });
            activeGuestActionFeedback = { guestId: guest.id, text: `${guest.full_name || "Guest"} marked skipped.`, tone: "success" };
            setMessage(`Updated ${guest.full_name} to skipped.`, "success");
          } else {
            activeGuestActionFeedback = { guestId: guest.id, text: `Updating ${guest.full_name || "guest"}...`, tone: "pending" };
            renderGuests(latestPayload);
            await fetchJSON(`/api/guests/${guest.id}/status`, {
              method: "POST",
              body: JSON.stringify({ status: action }),
            });
            activeGuestActionFeedback = { guestId: guest.id, text: `${guest.full_name || "Guest"} updated to ${action}.`, tone: "success" };
            setMessage(`Updated ${guest.full_name} to ${action}.`, "success");
          }

          await loadGuests();
        } catch (error) {
          activeGuestActionFeedback = { guestId: guest.id, text: error.message, tone: "error" };
          renderGuests(latestPayload);
          setMessage(error.message, "error");
        }
      });
    });

    guestList.appendChild(node);
  });

  guestLoadMoreButton.classList.toggle("hidden", visibleGuests.length >= filteredGuests.length);
  if (!guestLoadMoreButton.classList.contains("hidden")) {
    guestLoadMoreButton.textContent = `Load More Guests (${filteredGuests.length - visibleGuests.length} remaining)`;
  }
}

async function loadGuests() {
  emitClientBeacon("loadGuests_enter");
  try {
    if (!latestPayload) {
      const cachedPayload = readCachedPayload(GUEST_PAYLOAD_CACHE_KEY);
      // Only use cache if it has meaningful data (not all zeros)
      const hasData = cachedPayload && (
        (cachedPayload.stats?.total ?? 0) > 0 ||
        (cachedPayload.guests?.length ?? 0) > 0
      );
      
      if (hasData) {
        renderGuests(cachedPayload);
        setMessage("Refreshing guests...", "pending");
      } else {
        setMessage("Loading guests...", "pending");
      }
    }
    const needsFullForPreset = AI_HEAVY_PRESETS.has(activeGuestPreset);
    const payload = await fetchJSON(needsFullForPreset ? "/api/guests" : "/api/guests?skip_enrichment=true");
    emitClientBeacon("loadGuests_api_ok");
    payloadHasFullEnrichment = hasFullEnrichment(payload);
    renderGuests(payload);
    storeCachedPayload(GUEST_PAYLOAD_CACHE_KEY, payload);
    if (!payloadHasFullEnrichment && !fullHydrationInFlight) {
      fullHydrationInFlight = true;
      window.setTimeout(async () => {
        try {
          const enrichedPayload = await fetchJSON("/api/guests");
          payloadHasFullEnrichment = hasFullEnrichment(enrichedPayload);
          if (payloadHasFullEnrichment && AI_HEAVY_PRESETS.has(activeGuestPreset)) {
            renderGuests(enrichedPayload);
          }
          latestPayload = enrichedPayload;
          storeCachedPayload(GUEST_PAYLOAD_CACHE_KEY, enrichedPayload);
        } catch (error) {
          // Keep lite mode if enriched hydration fails.
        } finally {
          fullHydrationInFlight = false;
        }
      }, 20);
    }
    if (message && message.classList.contains("pending")) {
      setMessage("", "");
    }
  } catch (error) {
    emitClientBeacon("loadGuests_error");
    setMessage(error.message, "error");
  }
}

if (form) {
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());
  const submitButton = form.querySelector("button[type='submit']");
  
  setMessage("Saving guest...", "pending");

  try {
    await loadingManager.wrap(
      submitButton,
      async () => {
        await fetchJSON("/api/guests", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        form.reset();
        setMessage("Guest saved directly to the database.", "success");
        await loadGuests();
      },
      { loadingText: "Saving...", successText: "✓ Saved" }
    );
  } catch (error) {
    setMessage(error.userMessage || error.message, "error");
  }
});
}

if (importForm) {
importForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(importForm);
  const uploadedFile = formData.get("file");

  if (!(uploadedFile instanceof File) || !uploadedFile.name) {
    setImportMessage("Please choose a CSV or Excel file.", "error");
    return;
  }

  const submitButton = importForm.querySelector("button[type='submit']");
  submitButton.disabled = true;
  submitButton.textContent = "Importing...";
  setImportMessage("Importing guest file...", "pending");
  try {
    const result = await fetchUpload("/api/import", formData);
    importForm.reset();
    setImportMessage(
      `Import finished. New: ${result.imported}, Updated: ${result.updated}, Skipped: ${result.skipped}, Errors: ${result.errors}.`,
      result.errors ? "error" : "success",
    );
    await loadGuests();
  } catch (error) {
    setImportMessage(error.message, "error");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Import File";
  }
});
}

if (refreshButton) {
refreshButton.addEventListener("click", async () => {
  await loadingManager.wrap(
    refreshButton,
    () => loadGuests(),
    { loadingText: "Refreshing...", successText: "✓ Refreshed" }
  );
});
}

if (exportButton) {
exportButton.addEventListener("click", () => {
  window.location.href = "/api/export";
});
}

if (bulkResearchButton) {
  bulkResearchButton.addEventListener("click", async () => {
    if (!confirmCriticalAction("Research missing guest profiles now? This will use saved website and social data to prefill planning copilot context.")) {
      return;
    }
    bulkResearchButton.disabled = true;
    bulkResearchButton.textContent = "Researching...";
    setBulkResearchMessage("Researching missing guest profiles in batches...", "pending");

    let totalResearched = 0;
    let remainingEligible = 0;
    let skippedCached = 0;
    let skippedMissingProfile = 0;
    const errors = [];

    try {
      while (true) {
        const result = await fetchJSON("/api/guests/research-bulk", {
          method: "POST",
          body: JSON.stringify({ limit: 25 }),
        });
        totalResearched += Number(result.researched || 0);
        remainingEligible = Number(result.remaining_eligible || 0);
        skippedCached = Number(result.skipped_cached || 0);
        skippedMissingProfile = Number(result.skipped_missing_profile || 0);
        errors.push(...(result.errors || []));
        if (!remainingEligible || !result.processed_batch_size) {
          break;
        }
        setBulkResearchMessage(
          `Researched ${totalResearched} guest profile${totalResearched === 1 ? "" : "s"} so far. ${remainingEligible} still eligible.`,
          "pending",
        );
      }

      const errorSuffix = errors.length ? ` First issue: ${errors[0]}` : "";
      setBulkResearchMessage(
        `Research finished. New research: ${totalResearched}. Already cached: ${skippedCached}. Missing website/social data: ${skippedMissingProfile}. Remaining eligible: ${remainingEligible}.${errorSuffix}`,
        errors.length ? "error" : "success",
      );
      await loadGuests();
    } catch (error) {
      setBulkResearchMessage(error.message, "error");
    } finally {
      bulkResearchButton.disabled = false;
      bulkResearchButton.textContent = "Research Missing Profiles";
    }
  });
}

if (decisionFilter) {
decisionFilter.addEventListener("change", () => {
  visibleGuestCount = GUEST_PAGE_SIZE;
  if (latestPayload) {
    renderGuests(latestPayload);
  }
});
}

// Debounce search input for better performance
const debouncedSearch = debounceUtil(() => {
  visibleGuestCount = GUEST_PAGE_SIZE;
  if (latestPayload) {
    renderGuests(latestPayload);
  }
}, 300);

if (guestSearch) {
  guestSearch.addEventListener("input", debouncedSearch);
}

if (guestSort) {
guestSort.addEventListener("change", () => {
  if (latestPayload) {
    renderGuests(latestPayload);
  }
});
}

if (guestLoadMoreButton) {
guestLoadMoreButton.addEventListener("click", () => {
  visibleGuestCount += GUEST_PAGE_SIZE;
  if (latestPayload) {
    renderGuests(latestPayload);
  }
});
}

guestPresetButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    activeGuestPreset = button.dataset.guestPreset || "all";
    visibleGuestCount = GUEST_PAGE_SIZE;
    if (activeGuestPreset === "accepted" || activeGuestPreset === "rejected") {
      decisionFilter.value = activeGuestPreset;
    } else if (activeGuestPreset === "needs_review") {
      decisionFilter.value = "unprocessed";
    } else {
      decisionFilter.value = "all";
    }
    if (AI_HEAVY_PRESETS.has(activeGuestPreset) && !payloadHasFullEnrichment) {
      setMessage("Loading full AI context for this view...", "pending");
      await loadGuests();
      return;
    }
    if (latestPayload) {
      renderGuests(latestPayload);
    }
  });
});

function applyUrlState() {
  const params = new URLSearchParams(window.location.search);
  const query = params.get("q");
  const preset = params.get("preset");

  if (query) {
    guestSearch.value = query;
  }
  if (preset && guestPresetButtons.some((button) => button.dataset.guestPreset === preset)) {
    activeGuestPreset = preset;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function linkifyText(value) {
  const text = String(value || "");
  const urlPattern = /(https?:\/\/[^\s<]+)/gi;
  let lastIndex = 0;
  let output = "";

  text.replace(urlPattern, (match, _url, offset) => {
    const leadingText = text.slice(lastIndex, offset);
    let url = match;
    let trailingPunctuation = "";

    while (/[),.;!?]$/.test(url)) {
      trailingPunctuation = url.slice(-1) + trailingPunctuation;
      url = url.slice(0, -1);
    }

    output += escapeHtml(leadingText);
    output += `<a class="inline-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(url)}</a>`;
    output += escapeHtml(trailingPunctuation);
    lastIndex = offset + match.length;
    return match;
  });

  output += escapeHtml(text.slice(lastIndex));
  return output;
}

function renderGuestAiSummary(guest) {
  const support = guest.decision_support;
  if (!support) {
    return "";
  }

  const signals = (support.signals || [])
    .map((signal) => `<span class="signal-chip ${signal.tone || "neutral"}">${escapeHtml(signal.label)}</span>`)
    .join("");
  const strengths = (support.strengths || []).slice(0, 2).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const cautions = (support.cautions || []).slice(0, 2).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const acceptedMatches = (support.accepted_guest_matches || [])
    .slice(0, 3)
    .map((name) => `<span class="context-link">${escapeHtml(name)}</span>`)
    .join("");
  const emailConflicts = (support.identity_flags?.email_conflicts || [])
    .slice(0, 3)
    .map((name) => `<li>Same email is also used by ${escapeHtml(name)}.</li>`)
    .join("");
  const hostConflicts = (support.identity_flags?.host_conflicts || [])
    .slice(0, 3)
    .map((name) => `<li>Website domain is also shared with ${escapeHtml(name)}.</li>`)
    .join("");

  return `
    <div class="guest-ai-card">
      <div class="guest-ai-head">
        <div>
          <p class="composer-eyebrow">AI Review Assist</p>
          <div class="guest-ai-title-row">
            <strong class="guest-ai-score">${Math.round(Number(support.score || 0))}/100</strong>
            <span class="guest-ai-badge ${recommendationTone(support)}">${escapeHtml(support.recommendation_label || "Needs Human Review")}</span>
          </div>
          <p class="guest-ai-copy">${escapeHtml(support.summary || "")}</p>
        </div>
        <p class="guest-ai-confidence">Confidence: ${escapeHtml(support.confidence || "medium")}</p>
      </div>
      ${signals ? `<div class="signal-list guest-ai-signals">${signals}</div>` : ""}
      ${acceptedMatches ? `<div class="guest-ai-match-row"><strong>Similar accepted guests</strong><div class="context-links">${acceptedMatches}</div></div>` : ""}
      <div class="guest-ai-grid">
        ${strengths ? `<div class="guest-ai-block"><strong>Why it could work</strong><ul>${strengths}</ul></div>` : ""}
        ${cautions ? `<div class="guest-ai-block caution"><strong>Watchouts</strong><ul>${cautions}</ul></div>` : ""}
        ${emailConflicts || hostConflicts ? `<div class="guest-ai-block caution"><strong>Identity checks</strong><ul>${emailConflicts}${hostConflicts}</ul></div>` : ""}
      </div>
    </div>
  `;
}

// ==================== AI Features ====================

let aiEnabled = false;
const aiModal = document.getElementById("ai-modal");
const aiModalTitle = document.getElementById("ai-modal-title");
const aiModalBody = document.getElementById("ai-modal-body");
const aiModalClose = document.getElementById("ai-modal-close");
const aiModalCopy = document.getElementById("ai-modal-copy");
const aiModalDone = document.getElementById("ai-modal-done");
const aiStatusIndicator = document.getElementById("ai-status-indicator");
let currentAIContent = "";

async function checkAIStatus() {
  if (!aiStatusIndicator) {
    return;
  }
  try {
    const data = await fetchJSON("/api/ai/status");
    aiEnabled = data.configured || false;
    
    if (aiEnabled) {
      aiStatusIndicator.innerHTML = `<span class="status-badge success">✅ AI Enabled (${escapeHtml(data.model || 'GPT-4')})</span>`;
      // Show all AI buttons
      document.querySelectorAll(".ai-button").forEach(btn => {
        btn.style.display = "inline-block";
      });
    } else {
      aiStatusIndicator.innerHTML = `<span class="status-badge warning">⚠️ AI Not Configured</span>`;
      // Hide all AI buttons
      document.querySelectorAll(".ai-button").forEach(btn => {
        btn.style.display = "none";
      });
    }
  } catch (error) {
    aiStatusIndicator.innerHTML = `<span class="status-badge error">❌ AI Check Failed</span>`;
    document.querySelectorAll(".ai-button").forEach(btn => {
      btn.style.display = "none";
    });
  }
}

function showAIModal(title, content) {
  aiModalTitle.textContent = title;
  aiModalBody.innerHTML = content;
  currentAIContent = content;
  aiModal.classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function hideAIModal() {
  aiModal.classList.add("hidden");
  document.body.style.overflow = "";
  currentAIContent = "";
}

function copyAIContent() {
  const tempDiv = document.createElement("div");
  tempDiv.innerHTML = currentAIContent;
  const text = tempDiv.textContent || tempDiv.innerText || "";
  
  navigator.clipboard.writeText(text).then(() => {
    aiModalCopy.textContent = "✅ Copied!";
    setTimeout(() => {
      aiModalCopy.textContent = "📋 Copy";
    }, 2000);
  }).catch(err => {
    alert("Failed to copy: " + err.message);
  });
}

async function generateAIEmailDraft(guestId, emailType) {
  if (!aiEnabled) {
    alert("AI features are not available. Please configure OPENAI_API_KEY.");
    return;
  }

  const customNote = prompt(`Add a custom note to include in the ${emailType} email (optional):`);
  const noteParam = customNote ? `&note=${encodeURIComponent(customNote)}` : "";
  
  try {
    const loadingMsg = emailType === "acceptance" ? "Generating acceptance email..." : "Generating rejection email...";
    showAIModal(`✨ ${emailType === "acceptance" ? "Acceptance" : "Rejection"} Email`, `<p class="loading">${loadingMsg}</p>`);
    
    const data = await fetchJSON(`/api/guests/${guestId}/ai-email-draft?type=${emailType}${noteParam}`);
    
    const content = `
      <div class="ai-email-draft">
        <div class="email-field">
          <label><strong>To:</strong></label>
          <p>${escapeHtml(data.guest_name)}</p>
        </div>
        <div class="email-field">
          <label><strong>Subject:</strong></label>
          <input type="text" class="email-subject-input" value="${escapeHtml(data.subject)}" />
        </div>
        <div class="email-field">
          <label><strong>Body:</strong></label>
          <textarea class="email-body-input" rows="15">${escapeHtml(data.body)}</textarea>
        </div>
        <p class="ai-note">💡 <em>Review and edit before sending. You can copy this draft and paste it into your email composer.</em></p>
      </div>
    `;
    
    showAIModal(`✨ AI ${emailType === "acceptance" ? "Acceptance" : "Rejection"} Email`, content);
  } catch (error) {
    showAIModal("Error", `<p class="error">Failed to generate email: ${escapeHtml(error.message)}</p>`);
  }
}

async function generateInterviewQuestions(guestId, guestName) {
  if (!aiEnabled) {
    alert("AI features are not available. Please configure OPENAI_API_KEY.");
    return;
  }

  const numQuestions = prompt("How many interview questions would you like? (5-20)", "10");
  if (!numQuestions) return;
  
  const num = parseInt(numQuestions, 10);
  if (isNaN(num) || num < 5 || num > 20) {
    alert("Please enter a number between 5 and 20");
    return;
  }
  
  try {
    showAIModal(`❓ Interview Questions for ${guestName}`, `<p class="loading">Generating ${num} personalized questions...</p>`);
    
    const data = await fetchJSON(`/api/guests/${guestId}/ai-interview-questions?num=${num}`);
    
    const questionsList = data.questions
      .map((q, i) => `<li><strong>${i + 1}.</strong> ${escapeHtml(q)}</li>`)
      .join("");
    
    const content = `
      <div class="ai-questions">
        <p class="ai-note">Generated ${data.num_questions} thoughtful questions for <strong>${escapeHtml(data.guest_name)}</strong></p>
        <ol class="questions-list">${questionsList}</ol>
        <p class="ai-note">💡 <em>These questions are tailored to the guest's background and interests. Feel free to adapt them for your interview style.</em></p>
      </div>
    `;
    
    showAIModal(`❓ Interview Questions: ${guestName}`, content);
  } catch (error) {
    showAIModal("Error", `<p class="error">Failed to generate questions: ${escapeHtml(error.message)}</p>`);
  }
}

async function analyzeGuestWithAI(guestId, guestName) {
  if (!aiEnabled) {
    alert("AI features are not available. Please configure OPENAI_API_KEY.");
    return;
  }
  
  try {
    showAIModal(`🔍 AI Analysis: ${guestName}`, `<p class="loading">Analyzing guest profile...</p>`);
    
    const data = await fetchJSON(`/api/guests/${guestId}/ai-analysis`);
    const analysis = data.analysis;
    
    const themes = Array.isArray(analysis.themes) 
      ? analysis.themes.map(t => `<li>${escapeHtml(t)}</li>`).join("")
      : `<p>${escapeHtml(analysis.themes || "N/A")}</p>`;
    
    const angles = Array.isArray(analysis.conversation_angles)
      ? analysis.conversation_angles.map(a => `<li>${escapeHtml(a)}</li>`).join("")
      : `<p>${escapeHtml(analysis.conversation_angles || "N/A")}</p>`;
    
    const content = `
      <div class="ai-analysis">
        <div class="analysis-metric">
          <strong>Fit Score</strong>
          <span class="score-large">${analysis.fit_score || 5}/10</span>
        </div>
        <div class="analysis-section">
          <strong>Key Themes:</strong>
          ${Array.isArray(analysis.themes) ? `<ul>${themes}</ul>` : themes}
        </div>
        <div class="analysis-section">
          <strong>Conversation Angles:</strong>
          ${Array.isArray(analysis.conversation_angles) ? `<ul>${angles}</ul>` : angles}
        </div>
        ${analysis.best_timing ? `
          <div class="analysis-section">
            <strong>Best Timing:</strong>
            <p>${escapeHtml(analysis.best_timing)}</p>
          </div>
        ` : ""}
        ${analysis.concerns ? `
          <div class="analysis-section caution">
            <strong>Potential Concerns:</strong>
            <p>${escapeHtml(analysis.concerns)}</p>
          </div>
        ` : ""}
        <p class="ai-note">💡 <em>This analysis is based on the guest's application. Use it to guide your decision and interview prep.</em></p>
      </div>
    `;
    
    showAIModal(`🔍 Deep Analysis: ${guestName}`, content);
  } catch (error) {
    showAIModal("Error", `<p class="error">Failed to analyze guest: ${escapeHtml(error.message)}</p>`);
  }
}

// Modal event listeners
if (aiModalClose) {
  aiModalClose.addEventListener("click", hideAIModal);
}

if (aiModalDone) {
  aiModalDone.addEventListener("click", hideAIModal);
}

if (aiModalCopy) {
  aiModalCopy.addEventListener("click", copyAIContent);
}

if (aiModal) {
  aiModal.querySelector(".modal-backdrop")?.addEventListener("click", hideAIModal);
}

try {
  // Check AI status on load
  checkAIStatus();

  // Set up keyboard shortcuts for power users
  if (keyboardManager) {
    // Refresh data
    keyboardManager.register('meta+r', (e) => {
      e.preventDefault();
      refreshButton.click();
    }, 'Refresh guest list');
    
    // Search focus
    keyboardManager.register('meta+f', (e) => {
      e.preventDefault();
      guestSearch.focus();
      guestSearch.select();
    }, 'Focus search box');
    
    keyboardManager.register('/', (e) => {
      const target = e.target;
      if (target.tagName !== 'INPUT' && target.tagName !== 'TEXTAREA') {
        e.preventDefault();
        guestSearch.focus();
      }
    }, 'Quick search (/)');
    
    // View presets
    keyboardManager.register('1', () => {
      const btn = guestPresetButtons.find(b => b.dataset.guestPreset === 'all');
      if (btn) btn.click();
    }, 'Show all guests (1)');
    
    keyboardManager.register('2', () => {
      const btn = guestPresetButtons.find(b => b.dataset.guestPreset === 'needs_review');
      if (btn) btn.click();
    }, 'Show needs review (2)');
    
    keyboardManager.register('3', () => {
      const btn = guestPresetButtons.find(b => b.dataset.guestPreset === 'ai_strong_fit');
      if (btn) btn.click();
    }, 'Show AI strong fits (3)');
    
    keyboardManager.register('4', () => {
      const btn = guestPresetButtons.find(b => b.dataset.guestPreset === 'accepted');
      if (btn) btn.click();
    }, 'Show accepted guests (4)');
    
    // Close modal
    keyboardManager.register('escape', () => {
      if (aiModal && !aiModal.classList.contains('hidden')) {
        hideAIModal();
      }
    }, 'Close modal (Esc)');
    
    // Show keyboard shortcuts help
    keyboardManager.register('shift+/', () => {
      const shortcuts = keyboardManager.getShortcuts();
      const shortcutList = shortcuts
        .map(s => `<li><kbd>${escapeHtml(s.shortcut)}</kbd> — ${escapeHtml(s.description)}</li>`)
        .join('');
      showAIModal(
        '⌨️ Keyboard Shortcuts',
        `<div class="shortcuts-help"><ul>${shortcutList}</ul></div>`
      );
    }, 'Show keyboard shortcuts (Shift+?)');
    
    keyboardManager.enable();
  }
} catch (error) {
  console.error('Dashboard initialization warning:', error);
}

// Automatically prune expired cache entries periodically
if (smartCache) {
  setInterval(() => {
    smartCache.prune();
  }, 5 * 60 * 1000); // Every 5 minutes
}

// Provide visual feedback when app is ready
console.log('✓ Mirror Talk Dashboard ready with performance optimizations');
console.log('  • Debounced search for faster filtering');
console.log('  • Request deduplication prevents duplicate API calls');
console.log('  • Smart caching reduces server load');
console.log('  • Keyboard shortcuts enabled (press Shift+/ for help)');

try {
  if (IS_FILE_PROTOCOL) {
    setMessage("This page is opened as a local file, so dashboard actions are disabled. Please use the live app URL (for example: https://.../dashboard).", "error");
    document.querySelectorAll("button, input, select, textarea").forEach((element) => {
      element.disabled = true;
    });
  } else {
    emitClientBeacon("startup_try_enter");
    applyUrlState();
    loadGuests();
  }
} catch (error) {
  if (!IS_FILE_PROTOCOL) {
    emitClientBeacon("startup_try_error");
  }
  console.error('Dashboard startup failed before loading guests:', error);
}
