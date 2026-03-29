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

function formatDateTime(value) {
  if (!value) return "Not set";
  const normalized = String(value).replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
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

function renderEpisodes(episodes) {
  episodeList.innerHTML = "";
  if (!episodes.length) {
    episodeList.innerHTML = "<p class='guest-summary'>No episodes tracked yet.</p>";
    return;
  }
  episodes.forEach((episode) => {
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
      <div class="operations-actions">
        <button type="button" class="secondary-button" data-episode-action="edit">Edit / Schedule</button>
        <button type="button" class="ghost-button danger-button" data-episode-action="delete">Delete</button>
      </div>
    `;

    const editButton = card.querySelector("[data-episode-action='edit']");
    const deleteButton = card.querySelector("[data-episode-action='delete']");
    editButton.addEventListener("click", () => {
      loadEpisodeIntoForm(episode);
      setMessage(episodeMessage, `Editing ${episode.episode_title || episode.guest_name || "episode"}.`, "success");
    });
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
}

function renderRecommendations(recommendations) {
  recommendationList.innerHTML = "";
  if (!recommendations.length) {
    recommendationList.innerHTML = "<p class='guest-summary'>Import the yearly release CSVs and the Not Yet Released queue to generate recommendations.</p>";
    return;
  }
  recommendations.forEach((episode, index) => {
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
      <div class="operations-preview">
        <p>${episode.recommendation_reason || "Good fit for the next release slot."}</p>
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
}

async function loadPlanning() {
  const payload = await fetchJSON("/api/planning");
  stats.total.textContent = payload.stats.episodes_total ?? 0;
  stats.released.textContent = payload.stats.episodes_released ?? 0;
  stats.scheduled.textContent = payload.stats.episodes_scheduled ?? 0;
  stats.unreleased.textContent = payload.stats.episodes_unreleased ?? 0;
  stats.promoReady.textContent = payload.stats.episodes_promo_ready ?? 0;
  stats.needsAssets.textContent = payload.stats.episodes_need_assets ?? 0;
  renderCategoryOptions(payload.available_categories || []);
  renderRecommendations(payload.recommendations || []);
  renderEpisodes(payload.episodes || []);
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

renderExportFields();
resetEpisodeForm();
loadPlanning().catch((error) => {
  setMessage(episodeMessage, error.message, "error");
});
