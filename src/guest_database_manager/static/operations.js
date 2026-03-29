const interviewForm = document.getElementById("interview-form");
const episodeForm = document.getElementById("episode-form");
const episodeImportForm = document.getElementById("episode-import-form");
const operationsExportForm = document.getElementById("operations-export-form");
const exportListName = document.getElementById("export-list-name");
const exportFields = document.getElementById("export-fields");
const episodeCategoryOptions = document.getElementById("episode-category-options");
const interviewMessage = document.getElementById("interview-message");
const episodeMessage = document.getElementById("episode-message");
const episodeImportMessage = document.getElementById("episode-import-message");
const operationsExportMessage = document.getElementById("operations-export-message");
const reminderMessage = document.getElementById("reminder-message");
const reminderList = document.getElementById("reminder-list");
const interviewList = document.getElementById("interview-list");
const episodeList = document.getElementById("episode-list");
const recommendationList = document.getElementById("recommendation-list");
const refreshButton = document.getElementById("operations-refresh-button");
const sendWeeklyRemindersButton = document.getElementById("send-weekly-reminders-button");
const syncCalendarButton = document.getElementById("sync-calendar-button");
let latestReminderCandidates = [];
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
  interviewsTotal: document.getElementById("ops-interviews-total"),
  interviewsPending: document.getElementById("ops-interviews-pending"),
  episodesTotal: document.getElementById("ops-episodes-total"),
  episodesScheduled: document.getElementById("ops-episodes-scheduled"),
  remindersDue: document.getElementById("ops-reminders-due"),
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
  if (!value) {
    return "Not set";
  }

  const normalized = String(value).replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("en-GB", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderInterviews(interviews) {
  interviewList.innerHTML = "";

  if (!interviews.length) {
    interviewList.innerHTML = "<p class='guest-summary'>No interviews tracked yet.</p>";
    return;
  }

  interviews.forEach((interview) => {
    const card = document.createElement("article");
    card.className = "operations-card";
    const calendarButton = interview.calendar_event_id
      ? `<button type="button" class="secondary-button" data-calendar-action="push">Update Google Calendar Event</button>`
      : "";
    card.innerHTML = `
      <h3>${interview.guest_name || "Unnamed guest"}</h3>
      <p>${interview.title || "Mirror Talk interview"}</p>
      <div class="operations-meta">
        <span>Scheduled: ${formatDateTime(interview.scheduled_for)}</span>
        <span>Email: ${interview.guest_email || "Not set"}</span>
        <span>Confirmation: ${interview.confirmation_status || "pending"}</span>
        <span>Reminder: ${interview.reminder_status || "not_scheduled"}</span>
      </div>
      <div class="operations-actions">
        ${calendarButton}
      </div>
    `;

    const calendarPushButton = card.querySelector("[data-calendar-action='push']");
    if (calendarPushButton) {
      calendarPushButton.addEventListener("click", async () => {
        calendarPushButton.disabled = true;
        calendarPushButton.textContent = "Updating...";
        try {
          await fetchJSON(`/api/interviews/${interview.id}/push-to-calendar`, {
            method: "POST",
            body: JSON.stringify({}),
          });
          setMessage(interviewMessage, `Updated Google Calendar for ${interview.guest_name}.`, "success");
          await loadOperations();
        } catch (error) {
          setMessage(interviewMessage, error.message, "error");
          calendarPushButton.disabled = false;
          calendarPushButton.textContent = "Update Google Calendar Event";
        }
      });
    }

    interviewList.appendChild(card);
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
    `;
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
    `;
    recommendationList.appendChild(card);
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
  const selectedList = exportListName.value;
  const fields = EXPORT_FIELD_CONFIG[selectedList] || [];
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

function renderReminderCandidates(interviews) {
  latestReminderCandidates = interviews;
  reminderList.innerHTML = "";

  if (!interviews.length) {
    reminderList.innerHTML = "<p class='guest-summary'>No reminder emails are due for this week.</p>";
    return;
  }

  interviews.forEach((interview) => {
    const card = document.createElement("article");
    card.className = "operations-card";
    card.innerHTML = `
      <h3>${interview.guest_name || "Unnamed guest"}</h3>
      <p>${interview.title || "Mirror Talk conversation"}</p>
      <div class="operations-meta">
        <span>Scheduled: ${interview.scheduled_for_display || formatDateTime(interview.scheduled_for)}</span>
        <span>Email: ${interview.guest_email || "Not set"}</span>
        <span>Confirmation: ${interview.confirmation_status || "pending"}</span>
      </div>
      <div class="operations-actions">
        <button type="button" class="secondary-button" data-reminder-action="preview">Preview Email</button>
        <button type="button" class="primary-button" data-reminder-action="send">Send Reminder</button>
      </div>
      <div class="operations-preview hidden"></div>
    `;

    const previewPanel = card.querySelector(".operations-preview");
    const previewButton = card.querySelector("[data-reminder-action='preview']");
    const sendButton = card.querySelector("[data-reminder-action='send']");

    previewButton.addEventListener("click", async () => {
      try {
        const preview = await fetchJSON(`/api/interviews/${interview.id}/reminder-template`);
        card.classList.add("selected");
        previewPanel.classList.remove("hidden");
        previewPanel.innerHTML = `
          <h4>${preview.subject}</h4>
          <p>To: ${interview.guest_email || "No email address"}</p>
          <pre>${preview.body}</pre>
        `;
      } catch (error) {
        setMessage(reminderMessage, error.message, "error");
      }
    });

    sendButton.addEventListener("click", async () => {
      try {
        await fetchJSON(`/api/interviews/${interview.id}/send-reminder`, {
          method: "POST",
          body: JSON.stringify({}),
        });
        setMessage(reminderMessage, `Reminder sent to ${interview.guest_name}.`, "success");
        await loadOperations();
      } catch (error) {
        setMessage(reminderMessage, error.message, "error");
      }
    });

    reminderList.appendChild(card);
  });
}

async function loadOperations() {
  const payload = await fetchJSON("/api/operations");
  stats.interviewsTotal.textContent = payload.stats.interviews_total ?? 0;
  stats.interviewsPending.textContent = payload.stats.interviews_pending_confirmation ?? 0;
  stats.episodesTotal.textContent = payload.stats.episodes_total ?? 0;
  stats.episodesScheduled.textContent = payload.stats.episodes_scheduled ?? 0;
  stats.remindersDue.textContent = payload.reminder_candidates?.length ?? 0;
  renderCategoryOptions(payload.available_categories || []);
  renderReminderCandidates(payload.reminder_candidates || []);
  renderInterviews(payload.interviews);
  renderRecommendations(payload.recommendations || []);
  renderEpisodes(payload.episodes);
}

interviewForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(interviewForm).entries());

  try {
    await fetchJSON("/api/interviews", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    interviewForm.reset();
    interviewForm.elements.timezone.value = "Europe/Berlin";
    interviewForm.elements.confirmation_status.value = "pending";
    interviewForm.elements.reminder_status.value = "not_scheduled";
    setMessage(interviewMessage, "Interview saved.", "success");
    await loadOperations();
  } catch (error) {
    setMessage(interviewMessage, error.message, "error");
  }
});

episodeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(episodeForm).entries());

  try {
    await fetchJSON("/api/episodes", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    episodeForm.reset();
    episodeForm.elements.release_status.value = "unplanned";
    episodeForm.elements.production_status.value = "idea";
    episodeForm.elements.promotion_status.value = "unknown";
    episodeForm.elements.priority_score.value = "0";
    setMessage(episodeMessage, "Episode saved.", "success");
    await loadOperations();
  } catch (error) {
    setMessage(episodeMessage, error.message, "error");
  }
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
    await loadOperations();
  } catch (error) {
    setMessage(episodeImportMessage, error.message, "error");
  }
});

operationsExportForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const selectedFields = Array.from(
    operationsExportForm.querySelectorAll("input[name='fields']:checked"),
    (input) => input.value,
  );

  try {
    await downloadExport({
      list_name: exportListName.value,
      format: operationsExportForm.elements.format.value,
      fields: selectedFields,
    });
    setMessage(operationsExportMessage, "Export is downloading.", "success");
  } catch (error) {
    setMessage(operationsExportMessage, error.message, "error");
  }
});

refreshButton.addEventListener("click", async () => {
  try {
    await loadOperations();
  } catch (error) {
    setMessage(interviewMessage, error.message, "error");
  }
});

syncCalendarButton.addEventListener("click", async () => {
  try {
    const result = await fetchJSON("/api/google-calendar/sync", {
      method: "POST",
      body: JSON.stringify({}),
    });
    setMessage(
      interviewMessage,
      result.count
        ? `Google Calendar sync complete. ${result.count} interview event(s) synced.`
        : "Google Calendar sync completed, but no matching interview events were found.",
      "success",
    );
    await loadOperations();
  } catch (error) {
    setMessage(interviewMessage, error.message, "error");
  }
});

sendWeeklyRemindersButton.addEventListener("click", async () => {
  if (!latestReminderCandidates.length) {
    setMessage(reminderMessage, "There are no reviewed reminder candidates to send right now.", "error");
    return;
  }

  try {
    const result = await fetchJSON("/api/reminders/send-weekly", {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (result.errors?.length) {
      setMessage(
        reminderMessage,
        `Sent ${result.count} reminder(s), but ${result.errors.length} interview(s) still need attention.`,
        "error",
      );
    } else {
      setMessage(reminderMessage, `Sent ${result.count} weekly reminder(s).`, "success");
    }
    await loadOperations();
  } catch (error) {
    setMessage(reminderMessage, error.message, "error");
  }
});

exportListName.addEventListener("change", () => {
  renderExportFields();
});

renderExportFields();
loadOperations().catch((error) => {
  setMessage(interviewMessage, error.message, "error");
});
