const interviewForm = document.getElementById("interview-form");
const interviewSubmitButton = document.getElementById("interview-submit-button");
const interviewResetButton = document.getElementById("interview-reset-button");
const interviewMessage = document.getElementById("interview-message");
const reminderMessage = document.getElementById("reminder-message");
const reminderList = document.getElementById("reminder-list");
const interviewList = document.getElementById("interview-list");
const reminderSearchInput = document.getElementById("reminder-search");
const reminderResultsMeta = document.getElementById("reminder-results-meta");
const reminderLoadMoreButton = document.getElementById("reminder-load-more");
const reminderPresetButtons = Array.from(document.querySelectorAll("[data-reminder-preset]"));
const interviewSearchInput = document.getElementById("interview-search");
const interviewYearFilter = document.getElementById("interview-year-filter");
const interviewConfirmationFilter = document.getElementById("interview-confirmation-filter");
const interviewSort = document.getElementById("interview-sort");
const interviewResultsMeta = document.getElementById("interview-results-meta");
const interviewLoadMoreButton = document.getElementById("interview-load-more");
const interviewPresetButtons = Array.from(document.querySelectorAll("[data-interview-preset]"));
const refreshButton = document.getElementById("operations-refresh-button");
const sendWeeklyRemindersButton = document.getElementById("send-weekly-reminders-button");
const syncCalendarButton = document.getElementById("sync-calendar-button");

let latestOperationsPayload = { interviews: [], reminder_candidates: [], stats: {} };
let activeReminderPreset = "all";
let activeInterviewPreset = "all";
let activeInterviewEditorId = null;
let activeInterviewFeedback = { id: null, text: "", tone: "" };
let activeInterviewActionFeedback = { id: null, text: "", tone: "" };
let visibleReminderCount = 8;
let visibleInterviewCount = 10;

const REMINDER_PAGE_SIZE = 8;
const INTERVIEW_PAGE_SIZE = 10;

const stats = {
  interviewsTotal: document.getElementById("ops-interviews-total"),
  interviewsPending: document.getElementById("ops-interviews-pending"),
  interviewsConfirmed: document.getElementById("ops-interviews-confirmed"),
  remindersDue: document.getElementById("ops-reminders-due"),
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

function setMessage(node, text, tone = "") {
  node.textContent = text;
  node.className = `message ${tone}`.trim();
}

function normalizeText(value) {
  return String(value || "").trim().toLowerCase();
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

function formatDateForDateTimeInput(value) {
  if (!value) return "";
  return String(value).replace(" ", "T").slice(0, 16);
}

function parseDate(value) {
  if (!value) return null;
  const date = new Date(String(value).replace(" ", "T"));
  return Number.isNaN(date.getTime()) ? null : date;
}

function getYearValue(value) {
  const date = parseDate(value);
  return date ? String(date.getFullYear()) : "";
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

function actionFeedbackMarkup(feedback) {
  if (!feedback?.text) {
    return "";
  }
  return `<p class="composer-feedback ${feedback.tone || ""}">${feedback.text}</p>`;
}

function populateInterviewYearOptions(interviews) {
  const years = Array.from(
    new Set(interviews.map((interview) => getYearValue(interview.scheduled_for)).filter(Boolean)),
  ).sort((a, b) => Number(b) - Number(a));

  const currentValue = interviewYearFilter.value;
  interviewYearFilter.innerHTML = '<option value="">All Years</option>';
  years.forEach((year) => {
    const option = document.createElement("option");
    option.value = year;
    option.textContent = year;
    interviewYearFilter.appendChild(option);
  });
  interviewYearFilter.value = years.includes(currentValue) ? currentValue : "";
}

function resetInterviewForm() {
  interviewForm.reset();
  interviewForm.elements.id.value = "";
  interviewForm.elements.timezone.value = "Europe/Berlin";
  interviewForm.elements.confirmation_status.value = "pending";
  interviewForm.elements.reminder_status.value = "not_scheduled";
  interviewSubmitButton.textContent = "Save Interview";
  interviewResetButton.hidden = true;
}

function loadInterviewIntoForm(interview) {
  interviewForm.elements.id.value = interview.id || "";
  interviewForm.elements.guest_name.value = interview.guest_name || "";
  interviewForm.elements.guest_email.value = interview.guest_email || "";
  interviewForm.elements.title.value = interview.title || "";
  interviewForm.elements.scheduled_for.value = formatDateForDateTimeInput(interview.scheduled_for);
  interviewForm.elements.timezone.value = interview.timezone || "Europe/Berlin";
  interviewForm.elements.calendar_event_id.value = interview.calendar_event_id || "";
  interviewForm.elements.join_url.value = interview.join_url || "";
  interviewForm.elements.confirmation_status.value = interview.confirmation_status || "pending";
  interviewForm.elements.reminder_status.value = interview.reminder_status || "not_scheduled";
  interviewForm.elements.notes.value = interview.notes || "";
  interviewSubmitButton.textContent = "Update Interview";
  interviewResetButton.hidden = false;
  interviewForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderInterviewInlineEditor(container, interview) {
  container.innerHTML = `
    <div class="inline-editor-title">Quick Edit Interview</div>
    <form class="inline-editor-form" data-inline-interview-form>
      ${createFieldMarkup("Guest Name", `<input name="guest_name" type="text" value="${interview.guest_name || ""}" required />`)}
      ${createFieldMarkup("Guest Email", `<input name="guest_email" type="email" value="${interview.guest_email || ""}" />`)}
      ${createFieldMarkup("Title", `<input name="title" type="text" value="${interview.title || ""}" />`, true)}
      ${createFieldMarkup("Scheduled For", `<input name="scheduled_for" type="datetime-local" value="${formatDateForDateTimeInput(interview.scheduled_for)}" required />`)}
      ${createFieldMarkup("Timezone", `<input name="timezone" type="text" value="${interview.timezone || "Europe/Berlin"}" />`)}
      ${createFieldMarkup("Join URL", `<input name="join_url" type="url" value="${interview.join_url || ""}" />`, true)}
      ${createFieldMarkup("Confirmation", `
        <select name="confirmation_status">
          <option value="pending" ${normalizeText(interview.confirmation_status) === "pending" ? "selected" : ""}>Pending</option>
          <option value="confirmed" ${normalizeText(interview.confirmation_status) === "confirmed" ? "selected" : ""}>Confirmed</option>
          <option value="reschedule_requested" ${normalizeText(interview.confirmation_status) === "reschedule_requested" ? "selected" : ""}>Reschedule Requested</option>
        </select>
      `)}
      ${createFieldMarkup("Reminder", `
        <select name="reminder_status">
          <option value="not_scheduled" ${normalizeText(interview.reminder_status) === "not_scheduled" ? "selected" : ""}>Not Scheduled</option>
          <option value="queued" ${normalizeText(interview.reminder_status) === "queued" ? "selected" : ""}>Queued</option>
          <option value="sent" ${normalizeText(interview.reminder_status) === "sent" ? "selected" : ""}>Sent</option>
        </select>
      `)}
      ${createFieldMarkup("Calendar Event ID", `<input name="calendar_event_id" type="text" value="${interview.calendar_event_id || ""}" />`, true)}
      ${createFieldMarkup("Notes", `<textarea name="notes" rows="3">${interview.notes || ""}</textarea>`, true)}
      <div class="inline-editor-actions full-width">
        <button type="submit" class="primary-button">Save Changes</button>
        <button type="button" class="secondary-button" data-inline-interview-confirm>Mark Confirmed</button>
        <button type="button" class="ghost-button" data-inline-interview-cancel>Close</button>
      </div>
      <p class="message" data-inline-interview-message aria-live="polite"></p>
    </form>
  `;

  const form = container.querySelector("[data-inline-interview-form]");
  const messageNode = container.querySelector("[data-inline-interview-message]");
  const confirmButton = container.querySelector("[data-inline-interview-confirm]");
  const cancelButton = container.querySelector("[data-inline-interview-cancel]");
  const saveButton = form.querySelector("button[type='submit']");

  if (activeInterviewFeedback.id === interview.id && activeInterviewFeedback.text) {
    setMessage(messageNode, activeInterviewFeedback.text, activeInterviewFeedback.tone);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(form).entries());
    saveButton.disabled = true;
    saveButton.textContent = "Saving...";
    try {
      await fetchJSON(`/api/interviews/${interview.id}`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      activeInterviewFeedback = {
        id: interview.id,
        text: `Saved ${payload.guest_name || "interview"}.`,
        tone: "success",
      };
      setMessage(interviewMessage, `Updated ${payload.guest_name || "interview"}.`, "success");
      activeInterviewEditorId = interview.id;
      await loadOperations();
    } catch (error) {
      setMessage(messageNode, error.message, "error");
      saveButton.disabled = false;
      saveButton.textContent = "Save Changes";
    }
  });

  confirmButton.addEventListener("click", async () => {
    const payload = Object.fromEntries(new FormData(form).entries());
    payload.confirmation_status = "confirmed";
    confirmButton.disabled = true;
    confirmButton.textContent = "Confirming...";
    try {
      await fetchJSON(`/api/interviews/${interview.id}`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      activeInterviewFeedback = {
        id: interview.id,
        text: `${payload.guest_name || "Interview"} marked confirmed.`,
        tone: "success",
      };
      setMessage(interviewMessage, `Marked ${payload.guest_name || "interview"} as confirmed.`, "success");
      activeInterviewEditorId = interview.id;
      await loadOperations();
    } catch (error) {
      setMessage(messageNode, error.message, "error");
      confirmButton.disabled = false;
      confirmButton.textContent = "Mark Confirmed";
    }
  });

  cancelButton.addEventListener("click", () => {
    activeInterviewEditorId = null;
    activeInterviewFeedback = { id: null, text: "", tone: "" };
    renderOperations();
  });
}

function filterAndSortInterviews(interviews) {
  const searchTerm = normalizeText(interviewSearchInput.value);
  const selectedYear = interviewYearFilter.value;
  const confirmationStatus = interviewConfirmationFilter.value;
  const sortMode = interviewSort.value || "closest";

  const filtered = interviews.filter((interview) => {
    const haystack = [
      interview.guest_name,
      interview.guest_email,
      interview.title,
      interview.confirmation_status,
    ].map(normalizeText).join(" ");

    if (searchTerm && !haystack.includes(searchTerm)) {
      return false;
    }
    if (selectedYear && getYearValue(interview.scheduled_for) !== selectedYear) {
      return false;
    }
    if (confirmationStatus && normalizeText(interview.confirmation_status) !== confirmationStatus) {
      return false;
    }
    if (activeInterviewPreset === "this_week") {
      const date = parseDate(interview.scheduled_for);
      if (!date) return false;
      const now = new Date();
      const weekStart = new Date(now);
      weekStart.setDate(now.getDate() - ((now.getDay() + 6) % 7));
      weekStart.setHours(0, 0, 0, 0);
      const weekEnd = new Date(weekStart);
      weekEnd.setDate(weekStart.getDate() + 7);
      if (!(date >= weekStart && date < weekEnd)) {
        return false;
      }
    }
    if (activeInterviewPreset === "needs_confirmation" && normalizeText(interview.confirmation_status) !== "pending") {
      return false;
    }
    if (activeInterviewPreset === "calendar_linked" && !normalizeText(interview.calendar_event_id)) {
      return false;
    }
    return true;
  });

  filtered.sort((left, right) => {
    const leftDate = parseDate(left.scheduled_for);
    const rightDate = parseDate(right.scheduled_for);

    if (sortMode === "name") {
      return normalizeText(left.guest_name).localeCompare(normalizeText(right.guest_name));
    }

    if (sortMode === "recently_updated") {
      return Number(right.id || 0) - Number(left.id || 0);
    }

    if (sortMode === "farthest") {
      if (!leftDate && !rightDate) return Number(right.id || 0) - Number(left.id || 0);
      if (!leftDate) return 1;
      if (!rightDate) return -1;
      return rightDate - leftDate;
    }

    if (!leftDate && !rightDate) return Number(right.id || 0) - Number(left.id || 0);
    if (!leftDate) return 1;
    if (!rightDate) return -1;
    return leftDate - rightDate;
  });

  return filtered;
}

function filterReminderCandidates(interviews) {
  const searchTerm = normalizeText(reminderSearchInput.value);
  return interviews.filter((interview) => {
    const haystack = [
      interview.guest_name,
      interview.guest_email,
      interview.title,
      interview.scheduled_for_display,
    ].map(normalizeText).join(" ");
    if (searchTerm && !haystack.includes(searchTerm)) {
      return false;
    }
    if (activeReminderPreset === "pending" && normalizeText(interview.confirmation_status) !== "pending") {
      return false;
    }
    if (activeReminderPreset === "missing_email" && normalizeText(interview.guest_email)) {
      return false;
    }
    return true;
  });
}

function renderInterviews(interviews, totalCount) {
  interviewList.innerHTML = "";
  updateResultsMeta(
    interviewResultsMeta,
    interviews.length,
    totalCount,
    "No interviews tracked yet.",
    "Refine the search, year, or confirmation filters to narrow the calendar."
  );

  const visibleInterviews = interviews.slice(0, visibleInterviewCount);
  if (!interviews.length) {
    interviewList.innerHTML = totalCount
      ? "<p class='guest-summary'>No interviews match the current controls.</p>"
      : "<p class='guest-summary'>No interviews tracked yet.</p>";
    interviewLoadMoreButton.classList.add("hidden");
    return;
  }

  visibleInterviews.forEach((interview) => {
    const card = document.createElement("article");
    card.className = "operations-card";
    const calendarButton = interview.calendar_event_id
      ? `<button type="button" class="secondary-button" data-calendar-action="push">Update Google Calendar Event</button>`
      : "";
    const reminderButtons = interview.guest_email
      ? `
        <button type="button" class="ghost-button" data-interview-action="preview-reminder">Preview Reminder</button>
        <button type="button" class="primary-button" data-interview-action="send-reminder">Send Reminder</button>
      `
      : `
        <button type="button" class="ghost-button" data-interview-action="preview-reminder" disabled>Preview Reminder</button>
        <button type="button" class="primary-button" data-interview-action="send-reminder" disabled>Send Reminder</button>
      `;
    card.innerHTML = `
      <h3>${interview.guest_name || "Unnamed guest"}</h3>
      <p>${interview.title || "Mirror Talk interview"}</p>
      <div class="operations-meta">
        <span>Scheduled: ${formatDateTime(interview.scheduled_for)}</span>
        <span>Email: ${interview.guest_email || "Not set"}</span>
        <span>Confirmation: ${interview.confirmation_status || "pending"}</span>
        <span>Reminder: ${interview.reminder_status || "not_scheduled"}</span>
      </div>
      <div class="context-links">
        <a class="context-link" href="${buildScopedLink("/dashboard", interview.guest_name || interview.guest_email)}">View Guest</a>
        <a class="context-link" href="${buildScopedLink("/planning", interview.guest_name || interview.guest_email)}">View Planning</a>
      </div>
      <div class="operations-actions">
        <button type="button" class="secondary-button" data-interview-action="edit">${activeInterviewEditorId === interview.id ? "Hide Quick Edit" : "Quick Edit"}</button>
        <button type="button" class="ghost-button" data-interview-action="form">Open In Form</button>
        ${reminderButtons}
        ${calendarButton}
        <button type="button" class="ghost-button danger-button" data-interview-action="delete">Delete</button>
      </div>
      <div class="card-action-feedback">${activeInterviewActionFeedback.id === interview.id ? actionFeedbackMarkup(activeInterviewActionFeedback) : ""}</div>
      <div class="inline-editor hidden" data-interview-editor></div>
      <div class="operations-preview hidden" data-interview-reminder-preview></div>
    `;

    const editButton = card.querySelector("[data-interview-action='edit']");
    const formButton = card.querySelector("[data-interview-action='form']");
    const previewReminderButton = card.querySelector("[data-interview-action='preview-reminder']");
    const sendReminderButton = card.querySelector("[data-interview-action='send-reminder']");
    const calendarPushButton = card.querySelector("[data-calendar-action='push']");
    const deleteButton = card.querySelector("[data-interview-action='delete']");
    const editorNode = card.querySelector("[data-interview-editor]");
    const reminderPreviewNode = card.querySelector("[data-interview-reminder-preview]");
    const actionFeedbackNode = card.querySelector(".card-action-feedback");

    editButton.addEventListener("click", () => {
      activeInterviewEditorId = activeInterviewEditorId === interview.id ? null : interview.id;
      renderOperations();
    });

    formButton.addEventListener("click", () => {
      loadInterviewIntoForm(interview);
      setMessage(interviewMessage, `Loaded ${interview.guest_name || "interview"} into the main form.`, "success");
    });

    if (activeInterviewEditorId === interview.id) {
      editorNode.classList.remove("hidden");
      renderInterviewInlineEditor(editorNode, interview);
    }

    if (previewReminderButton) {
      previewReminderButton.addEventListener("click", async () => {
        if (!interview.guest_email) {
          setMessage(interviewMessage, "This interview does not have a guest email yet.", "error");
          return;
        }

        previewReminderButton.disabled = true;
        previewReminderButton.textContent = "Loading...";
        activeInterviewActionFeedback = { id: interview.id, text: `Loading reminder preview for ${interview.guest_name || "guest"}...`, tone: "pending" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        try {
          const preview = await fetchJSON(`/api/interviews/${interview.id}/reminder-template`);
          reminderPreviewNode.classList.remove("hidden");
          reminderPreviewNode.innerHTML = `
            <h4>${preview.subject}</h4>
            <p>To: ${interview.guest_email}</p>
            <pre>${preview.body}</pre>
          `;
          activeInterviewActionFeedback = { id: interview.id, text: `Reminder preview ready for ${interview.guest_name || "guest"}.`, tone: "success" };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        } catch (error) {
          activeInterviewActionFeedback = { id: interview.id, text: error.message, tone: "error" };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
          setMessage(interviewMessage, error.message, "error");
        } finally {
          previewReminderButton.disabled = false;
          previewReminderButton.textContent = "Preview Reminder";
        }
      });
    }

    if (sendReminderButton) {
      sendReminderButton.addEventListener("click", async () => {
        if (!interview.guest_email) {
          setMessage(interviewMessage, "This interview does not have a guest email yet.", "error");
          return;
        }

        sendReminderButton.disabled = true;
        sendReminderButton.textContent = "Sending...";
        activeInterviewActionFeedback = { id: interview.id, text: `Sending reminder to ${interview.guest_name || interview.guest_email}...`, tone: "pending" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        try {
          await fetchJSON(`/api/interviews/${interview.id}/send-reminder`, {
            method: "POST",
            body: JSON.stringify({}),
          });
          reminderPreviewNode.classList.remove("hidden");
          reminderPreviewNode.innerHTML = `<p class="composer-feedback success">Reminder sent to ${interview.guest_name || interview.guest_email}.</p>`;
          activeInterviewActionFeedback = { id: interview.id, text: `Reminder sent to ${interview.guest_name || interview.guest_email}.`, tone: "success" };
          setMessage(interviewMessage, `Reminder sent to ${interview.guest_name || interview.guest_email}.`, "success");
          await loadOperations();
        } catch (error) {
          activeInterviewActionFeedback = { id: interview.id, text: error.message, tone: "error" };
          renderOperations();
          setMessage(interviewMessage, error.message, "error");
          sendReminderButton.disabled = false;
          sendReminderButton.textContent = "Send Reminder";
        }
      });
    }

    if (calendarPushButton) {
      calendarPushButton.addEventListener("click", async () => {
        calendarPushButton.disabled = true;
        calendarPushButton.textContent = "Updating...";
        activeInterviewActionFeedback = { id: interview.id, text: `Updating Google Calendar for ${interview.guest_name || "guest"}...`, tone: "pending" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        try {
          await fetchJSON(`/api/interviews/${interview.id}/push-to-calendar`, {
            method: "POST",
            body: JSON.stringify({}),
          });
          activeInterviewActionFeedback = { id: interview.id, text: `Google Calendar updated for ${interview.guest_name || "guest"}.`, tone: "success" };
          setMessage(interviewMessage, `Updated Google Calendar for ${interview.guest_name}.`, "success");
          await loadOperations();
        } catch (error) {
          activeInterviewActionFeedback = { id: interview.id, text: error.message, tone: "error" };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
          setMessage(interviewMessage, error.message, "error");
          calendarPushButton.disabled = false;
          calendarPushButton.textContent = "Update Google Calendar Event";
        }
      });
    }

    deleteButton.addEventListener("click", async () => {
      const label = interview.guest_name || "this interview";
      if (!window.confirm(`Delete ${label} from the database?`)) {
        return;
      }

      deleteButton.disabled = true;
      deleteButton.textContent = "Deleting...";
      activeInterviewActionFeedback = { id: interview.id, text: `Deleting ${label}...`, tone: "pending" };
      actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
      try {
        await fetchJSON(`/api/interviews/${interview.id}`, { method: "DELETE" });
        activeInterviewActionFeedback = { id: interview.id, text: `${label} deleted.`, tone: "success" };
        setMessage(interviewMessage, `Deleted ${label}.`, "success");
        await loadOperations();
      } catch (error) {
          activeInterviewActionFeedback = { id: interview.id, text: error.message, tone: "error" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        setMessage(interviewMessage, error.message, "error");
        deleteButton.disabled = false;
        deleteButton.textContent = "Delete";
      }
    });

    interviewList.appendChild(card);
  });

  interviewLoadMoreButton.classList.toggle("hidden", visibleInterviews.length >= interviews.length);
  if (!interviewLoadMoreButton.classList.contains("hidden")) {
    interviewLoadMoreButton.textContent = `Load More Interviews (${interviews.length - visibleInterviews.length} remaining)`;
  }
}

function renderReminderCandidates(interviews, totalCount) {
  reminderList.innerHTML = "";
  updateResultsMeta(
    reminderResultsMeta,
    interviews.length,
    totalCount,
    "No reminder emails are due for this week.",
    "Use search to focus on one guest or conversation."
  );

  const visibleReminders = interviews.slice(0, visibleReminderCount);
  if (!interviews.length) {
    reminderList.innerHTML = totalCount
      ? "<p class='guest-summary'>No reminders match the current search.</p>"
      : "<p class='guest-summary'>No reminder emails are due for this week.</p>";
    reminderLoadMoreButton.classList.add("hidden");
    return;
  }

  visibleReminders.forEach((interview) => {
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
      <div class="context-links">
        <a class="context-link" href="${buildScopedLink("/planning", interview.guest_name || interview.guest_email)}">Open Planning</a>
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

  reminderLoadMoreButton.classList.toggle("hidden", visibleReminders.length >= interviews.length);
  if (!reminderLoadMoreButton.classList.contains("hidden")) {
    reminderLoadMoreButton.textContent = `Load More Reminders (${interviews.length - visibleReminders.length} remaining)`;
  }
}

function renderOperations() {
  const interviews = latestOperationsPayload.interviews || [];
  const reminders = latestOperationsPayload.reminder_candidates || [];

  updatePresetButtons(reminderPresetButtons, activeReminderPreset, "reminderPreset");
  updatePresetButtons(interviewPresetButtons, activeInterviewPreset, "interviewPreset");
  populateInterviewYearOptions(interviews);
  renderReminderCandidates(filterReminderCandidates(reminders), reminders.length);
  renderInterviews(filterAndSortInterviews(interviews), interviews.length);
}

async function loadOperations() {
  const payload = await fetchJSON("/api/operations");
  latestOperationsPayload = payload;
  const interviews = payload.interviews || [];
  stats.interviewsTotal.textContent = payload.stats.interviews_total ?? interviews.length ?? 0;
  stats.interviewsPending.textContent = payload.stats.interviews_pending_confirmation ?? 0;
  stats.interviewsConfirmed.textContent = interviews.filter((item) => item.confirmation_status === "confirmed").length;
  stats.remindersDue.textContent = payload.reminder_candidates?.length ?? 0;
  renderOperations();
}

interviewForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(interviewForm).entries());
  const interviewId = payload.id;
  delete payload.id;

  try {
    await fetchJSON(interviewId ? `/api/interviews/${interviewId}` : "/api/interviews", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    resetInterviewForm();
    setMessage(interviewMessage, interviewId ? "Interview updated." : "Interview saved.", "success");
    await loadOperations();
  } catch (error) {
    setMessage(interviewMessage, error.message, "error");
  }
});

interviewResetButton.addEventListener("click", () => {
  resetInterviewForm();
  setMessage(interviewMessage, "Back to creating a new interview.", "success");
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
  const visibleReminders = filterReminderCandidates(latestOperationsPayload.reminder_candidates || []);
  if (!visibleReminders.length) {
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

[reminderSearchInput, interviewSearchInput, interviewYearFilter, interviewConfirmationFilter, interviewSort].forEach((node) => {
  node.addEventListener("input", () => {
    visibleReminderCount = REMINDER_PAGE_SIZE;
    visibleInterviewCount = INTERVIEW_PAGE_SIZE;
    renderOperations();
  });
  node.addEventListener("change", () => {
    visibleReminderCount = REMINDER_PAGE_SIZE;
    visibleInterviewCount = INTERVIEW_PAGE_SIZE;
    renderOperations();
  });
});

reminderLoadMoreButton.addEventListener("click", () => {
  visibleReminderCount += REMINDER_PAGE_SIZE;
  renderOperations();
});

interviewLoadMoreButton.addEventListener("click", () => {
  visibleInterviewCount += INTERVIEW_PAGE_SIZE;
  renderOperations();
});

reminderPresetButtons.forEach((button) => {
  button.addEventListener("click", () => {
    activeReminderPreset = button.dataset.reminderPreset || "all";
    visibleReminderCount = REMINDER_PAGE_SIZE;
    renderOperations();
  });
});

interviewPresetButtons.forEach((button) => {
  button.addEventListener("click", () => {
    activeInterviewPreset = button.dataset.interviewPreset || "all";
    visibleInterviewCount = INTERVIEW_PAGE_SIZE;
    if (activeInterviewPreset === "needs_confirmation") {
      interviewConfirmationFilter.value = "pending";
    } else if (activeInterviewPreset === "all") {
      interviewConfirmationFilter.value = "";
    }
    renderOperations();
  });
});

function applyUrlState() {
  const params = new URLSearchParams(window.location.search);
  const query = params.get("q");
  const preset = params.get("preset");

  if (query) {
    interviewSearchInput.value = query;
    reminderSearchInput.value = query;
  }
  if (preset && interviewPresetButtons.some((button) => button.dataset.interviewPreset === preset)) {
    activeInterviewPreset = preset;
  }
}

resetInterviewForm();
applyUrlState();
loadOperations().catch((error) => {
  setMessage(interviewMessage, error.message, "error");
});
