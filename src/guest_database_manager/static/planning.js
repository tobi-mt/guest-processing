const episodeForm = document.getElementById("episode-form");
const episodeImportForm = document.getElementById("episode-import-form");
const planningExportForm = document.getElementById("planning-export-form");
const episodeSubmitButton = document.getElementById("episode-submit-button");
const episodeResetButton = document.getElementById("episode-reset-button");
const exportListName = document.getElementById("export-list-name");
const exportFields = document.getElementById("export-fields");
const episodeCategoryOptions = document.getElementById("episode-category-options");
const episodeMessage = document.getElementById("episode-message");
const episodeImportMessage = document.getElementById("episode-import-message");
const planningExportMessage = document.getElementById("planning-export-message");
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
const episodeSort = document.getElementById("episode-sort");
const episodeResultsMeta = document.getElementById("episode-results-meta");
const episodeLoadMoreButton = document.getElementById("episode-load-more");
const episodePresetButtons = Array.from(document.querySelectorAll("[data-episode-preset]"));

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
let visibleRecommendationCount = 6;
let visibleEpisodeCount = 10;

const RECOMMENDATION_PAGE_SIZE = 6;
const EPISODE_PAGE_SIZE = 10;

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

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

async function postForm(url, formData) {
  const response = await fetch(url, {
    method: "POST",
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

function normalizeText(value) {
  return String(value || "").trim().toLowerCase();
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

function createFieldMarkup(label, inputMarkup, fullWidth = false) {
  return `
    <label class="${fullWidth ? "full-width" : ""}">
      <span>${label}</span>
      ${inputMarkup}
    </label>
  `;
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
  if (text.includes("seasonal focus")) {
    signals.push({ label: "Seasonal Fit", tone: "good" });
  }
  if (text.includes("ready to publish") || text.includes("promotion assets look ready")) {
    signals.push({ label: "Release Ready", tone: "good" });
  }
  return signals;
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
  episodeForm.elements.release_status.value = "unplanned";
  episodeForm.elements.production_status.value = "idea";
  episodeForm.elements.promotion_status.value = "unknown";
  episodeForm.elements.priority_score.value = "0";
  episodeSubmitButton.textContent = "Save Episode";
  episodeResetButton.hidden = true;
}

function loadEpisodeIntoForm(episode, { releaseDate = "", releaseStatus = "" } = {}) {
  episodeForm.elements.id.value = episode.id || "";
  episodeForm.elements.guest_name.value = episode.guest_name || "";
  episodeForm.elements.guest_email.value = episode.guest_email || "";
  episodeForm.elements.website.value = episode.website || "";
  episodeForm.elements.episode_title.value = episode.episode_title || "";
  episodeForm.elements.topic.value = episode.topic || "";
  episodeForm.elements.category.value = episode.category || "";
  episodeForm.elements.interview_date.value = formatDateForDateInput(episode.interview_date);
  episodeForm.elements.recording_date.value = formatDateForDateInput(episode.recording_date);
  episodeForm.elements.release_date.value = formatDateForDateTimeInput(releaseDate || episode.release_date);
  episodeForm.elements.release_status.value = releaseStatus || episode.release_status || "unplanned";
  episodeForm.elements.production_status.value = episode.production_status || "idea";
  episodeForm.elements.promotion_status.value = episode.promotion_status || "unknown";
  episodeForm.elements.priority_score.value = episode.priority_score ?? 0;
  episodeForm.elements.legacy_episode_number.value = episode.legacy_episode_number || "";
  episodeForm.elements.riverside_status.value = episode.riverside_status || "";
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
      ${createFieldMarkup("Priority", `<input name="priority_score" type="number" min="0" max="10" step="0.5" value="${episode.priority_score ?? 0}" />`)}
      ${createFieldMarkup("Topic", `<input name="topic" type="text" value="${episode.topic || ""}" />`, true)}
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
    if (activeEpisodePreset === "ready_to_schedule") {
      if (!(normalizeText(episode.production_status) === "ready" && normalizeText(episode.release_status) !== "scheduled")) {
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
    const card = document.createElement("article");
    card.className = "operations-card";
    card.innerHTML = `
      <h3>${episode.episode_title || "Untitled episode"}</h3>
      <p>${episode.guest_name || "Guest not set"}</p>
      <div class="operations-meta">
        <span>Topic: ${episode.topic || "Not set"}</span>
        <span>Category: ${episode.category || "Not set"}</span>
        <span>Release: ${formatDateTime(episode.release_date)}</span>
        <span>Status: ${episode.release_status || "unplanned"} / ${episode.production_status || "idea"}</span>
        <span>Promo: ${episode.promotion_status || "unknown"}</span>
        <span>Priority: ${episode.priority_score ?? 0}</span>
        <span>Source: ${episode.source_file_name || "Manual entry"}</span>
      </div>
      <div class="context-links">
        <a class="context-link" href="${buildScopedLink("/dashboard", episode.guest_name || episode.guest_email)}">View Guest</a>
        <a class="context-link" href="${buildScopedLink("/operations", episode.guest_name || episode.guest_email)}">View Interview Ops</a>
      </div>
      <div class="operations-actions">
        <button type="button" class="secondary-button" data-episode-action="edit">${activeEpisodeEditorId === episode.id ? "Hide Quick Edit" : "Quick Edit"}</button>
        <button type="button" class="ghost-button" data-episode-action="form">Open In Form</button>
        <button type="button" class="ghost-button danger-button" data-episode-action="delete">Delete</button>
      </div>
      <div class="inline-editor hidden" data-episode-editor></div>
    `;

    const editButton = card.querySelector("[data-episode-action='edit']");
    const formButton = card.querySelector("[data-episode-action='form']");
    const deleteButton = card.querySelector("[data-episode-action='delete']");
    const editorNode = card.querySelector("[data-episode-editor]");
    editButton.addEventListener("click", () => {
      activeEpisodeEditorId = activeEpisodeEditorId === episode.id ? null : episode.id;
      renderPlanning();
    });
    formButton.addEventListener("click", () => {
      loadEpisodeIntoForm(episode);
      setMessage(episodeMessage, `Loaded ${episode.episode_title || episode.guest_name || "episode"} into the main form.`, "success");
    });
    if (activeEpisodeEditorId === episode.id) {
      editorNode.classList.remove("hidden");
      renderEpisodeInlineEditor(editorNode, episode);
    }
    deleteButton.addEventListener("click", async () => {
      const label = episode.episode_title || episode.guest_name || "this episode";
      if (!window.confirm(`Delete ${label} from the database?`)) {
        return;
      }

      deleteButton.disabled = true;
      deleteButton.textContent = "Deleting...";
      try {
        await fetchJSON(`/api/episodes/${episode.id}`, { method: "DELETE" });
        setMessage(episodeMessage, `Deleted ${label}.`, "success");
        await loadPlanning();
      } catch (error) {
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
      <div class="context-links">
        <a class="context-link" href="${buildScopedLink("/dashboard", episode.guest_name || episode.guest_email)}">View Guest</a>
        <a class="context-link" href="${buildScopedLink("/operations", episode.guest_name || episode.guest_email)}">View Interview Ops</a>
      </div>
      <div class="operations-actions">
        <button type="button" class="primary-button" data-recommendation-action="schedule">Use Recommended Slot</button>
        <button type="button" class="secondary-button" data-recommendation-action="edit">Review In Form</button>
      </div>
    `;
    const scheduleButton = card.querySelector("[data-recommendation-action='schedule']");
    const editButton = card.querySelector("[data-recommendation-action='edit']");
    scheduleButton.addEventListener("click", async () => {
      try {
        const payload = {
          ...episode,
          release_date: formatDateForDateTimeInput(episode.recommended_release_date),
          release_status: "scheduled",
        };
        await fetchJSON(`/api/episodes/${episode.id}`, {
          method: "POST",
          body: JSON.stringify(payload),
        });
        setMessage(
          episodeMessage,
          `Scheduled ${episode.episode_title || episode.guest_name || "episode"} for ${formatDateTime(episode.recommended_release_date)}.`,
          "success",
        );
        await loadPlanning();
      } catch (error) {
        setMessage(episodeMessage, error.message, "error");
      }
    });
    editButton.addEventListener("click", () => {
      loadEpisodeIntoForm(episode, {
        releaseDate: episode.recommended_release_date,
        releaseStatus: "scheduled",
      });
      setMessage(
        episodeMessage,
        `Loaded ${episode.episode_title || episode.guest_name || "episode"} with the recommended release slot.`,
        "success",
      );
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
  renderRecommendations(filterRecommendations(recommendations), recommendations.length);
  renderEpisodes(filterEpisodes(episodes), episodes.length);
}

async function loadPlanning() {
  const payload = await fetchJSON("/api/planning");
  latestPlanningPayload = payload;
  stats.total.textContent = payload.stats.episodes_total ?? 0;
  stats.released.textContent = payload.stats.episodes_released ?? 0;
  stats.scheduled.textContent = payload.stats.episodes_scheduled ?? 0;
  stats.unreleased.textContent = payload.stats.episodes_unreleased ?? 0;
  stats.promoReady.textContent = payload.stats.episodes_promo_ready ?? 0;
  stats.needsAssets.textContent = payload.stats.episodes_need_assets ?? 0;
  renderPlanning();
}

episodeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(episodeForm).entries());
  const episodeId = payload.id;
  delete payload.id;
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
  }
});

episodeResetButton.addEventListener("click", () => {
  resetEpisodeForm();
  setMessage(episodeMessage, "Back to creating a new episode.", "success");
});

episodeImportForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(episodeImportForm);
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
  }
});

planningExportForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const selectedFields = Array.from(
    planningExportForm.querySelectorAll("input[name='fields']:checked"),
    (input) => input.value,
  );
  try {
    await downloadExport({
      list_name: exportListName.value,
      format: planningExportForm.elements.format.value,
      fields: selectedFields,
    });
    setMessage(planningExportMessage, "Export is downloading.", "success");
  } catch (error) {
    setMessage(planningExportMessage, error.message, "error");
  }
});

exportListName.addEventListener("change", renderExportFields);
refreshButton.addEventListener("click", async () => {
  try {
    await loadPlanning();
  } catch (error) {
    setMessage(episodeMessage, error.message, "error");
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

  if (query) {
    episodeSearchInput.value = query;
    recommendationSearchInput.value = query;
  }
  if (preset && episodePresetButtons.some((button) => button.dataset.episodePreset === preset)) {
    activeEpisodePreset = preset;
  }
}

renderExportFields();
resetEpisodeForm();
applyUrlState();
loadPlanning().catch((error) => {
  setMessage(episodeMessage, error.message, "error");
});
