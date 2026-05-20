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
const syncCalendarButton = document.getElementById("sync-calendar-button");
const operationsWeeklyOutreach = document.getElementById("operations-weekly-outreach");
const operationsAlerts = document.getElementById("operations-alerts");
const operationsTabButtons = Array.from(document.querySelectorAll("[data-operations-tab]"));
const operationsTabPanels = Array.from(document.querySelectorAll("[data-operations-panel]"));

let latestOperationsPayload = { interviews: [], reminder_candidates: [], stats: {} };
let activeReminderPreset = "all";
let activeInterviewPreset = "upcoming";
let activeInterviewEditorId = null;
let activeInterviewFeedback = { id: null, text: "", tone: "" };
let activeInterviewActionFeedback = { id: null, text: "", tone: "" };
let visibleReminderCount = 8;
let visibleInterviewCount = 10;
let activeOperationsTab = "upcoming_interviews";
let calendarReadOnlyMode = false;
const OPERATIONS_PAYLOAD_CACHE_KEY = "mirror-talk-operations-payload";

const REMINDER_PAGE_SIZE = 8;
const INTERVIEW_PAGE_SIZE = 10;

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
  interviewsTotal: document.getElementById("ops-interviews-total"),
  interviewsPending: document.getElementById("ops-interviews-pending"),
  interviewsConfirmed: document.getElementById("ops-interviews-confirmed"),
  remindersDue: document.getElementById("ops-reminders-due"),
};

function buildScopedLink(path, value) {
  return `${path}?q=${encodeURIComponent(value || "")}`;
}

function setOperationsTab(tabName) {
  activeOperationsTab = tabName;
  operationsTabButtons.forEach((button) => {
    const isActive = button.dataset.operationsTab === tabName;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  operationsTabPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.operationsPanel === tabName);
  });
}

async function fetchJSON(url, options = {}) {
  const isReadRequest = !options.method || String(options.method).toUpperCase() === "GET";
  let lastError = null;
  const requestTimeoutMs = isReadRequest ? 20000 : 30000;

  for (let attempt = 0; attempt < (isReadRequest ? 2 : 1); attempt += 1) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), requestTimeoutMs);
    try {
      const response = await fetch(url, {
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
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
        throw new Error(data.error || `Request failed (${response.status})`);
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

function formatConfirmationStatus(value) {
  const labels = {
    pending: "Pending reply",
    confirmed: "Confirmed",
    tentative: "Tentative",
    declined: "Declined",
    reschedule_requested: "Reschedule requested",
  };
  return labels[normalizeText(value)] || value || "Pending reply";
}

function formatInterviewStatus(value) {
  const labels = {
    scheduled: "Scheduled",
    cancelled: "Cancelled",
  };
  return labels[normalizeText(value)] || value || "Scheduled";
}

function formatReminderStatus(value) {
  const labels = {
    not_scheduled: "Not sent yet",
    queued: "Queued",
    sent: "Sent",
  };
  return labels[normalizeText(value)] || value || "Not sent yet";
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

function renderSkeletonCards(container, count = 3) {
  if (!container) return;
  container.innerHTML = Array.from({ length: count }).map(() => `
    <article class="operations-card skeleton-card" aria-hidden="true">
      <div class="skeleton-line medium"></div>
      <div class="skeleton-line short"></div>
      <div class="skeleton-line long"></div>
      <div class="skeleton-line long"></div>
    </article>
  `).join("");
}

function renderWeeklyOutreachPanel() {
  if (!operationsWeeklyOutreach) {
    return;
  }
  const weeklyOutreach = latestOperationsPayload.weekly_outreach || {};
  const spotlight = weeklyOutreach.spotlight_episode;
  const summary = weeklyOutreach.spotlight_summary;
  const socialFocus = (weeklyOutreach.social_focus || [])
    .map((item) => `<li><strong>${item.day}</strong>: ${item.theme}</li>`)
    .join("");

  operationsWeeklyOutreach.innerHTML = `
    <div class="insight-stack">
      <strong class="insight-label">How to use this panel</strong>
      <ul>
        <li>Use this as a weekly reference while you manage interviews and confirmations.</li>
        <li>Do not try to complete outreach here. The actual episode checklist lives in Release Planning.</li>
        <li>If the spotlight episode is already launching this week, let it guide what Tuesday to Friday promotion should happen around it.</li>
      </ul>
    </div>
    ${spotlight ? `
      <div class="insight-stack">
        <strong class="insight-label">Current release spotlight</strong>
        <p><strong>${spotlight.episode_title || spotlight.topic || "Upcoming episode"}</strong> · ${spotlight.guest_name || "Guest not set"}</p>
        <p>Release: ${formatDateTime(spotlight.release_date)}</p>
        ${summary ? `<p><strong>${summary.progress_label}</strong><br />${summary.next_step || ""}</p>` : ""}
      </div>
    ` : `
      <div class="insight-stack">
        <strong class="insight-label">Current release spotlight</strong>
        <p>No scheduled or newly released episode is active right now, so this week is best used for preparation, guest confirmations, and queue cleanup.</p>
      </div>
    `}
    <div class="insight-stack">
      <strong class="insight-label">Daily social focus</strong>
      <ul>${socialFocus}</ul>
    </div>
  `;
}

function renderOperationsAlerts() {
  if (!operationsAlerts) {
    return;
  }
  const alerts = latestOperationsPayload.booking_alerts || {};
  const doubleBookings = alerts.double_bookings || [];
  const cleanup = alerts.calendar_cleanup || [];

  if (!doubleBookings.length && !cleanup.length) {
    operationsAlerts.innerHTML = `
      <div class="insight-stack">
        <strong class="insight-label">No urgent calendar risks</strong>
        <p>No duplicate future guest bookings or stale cancelled calendar slots are showing right now.</p>
      </div>
    `;
    return;
  }

  operationsAlerts.innerHTML = `
    ${calendarReadOnlyMode ? `
      <div class="insight-stack caution">
        <strong class="insight-label">Google Calendar is read-only</strong>
        <p>Your current Google token can sync interviews, but it cannot remove calendar events. The destructive cleanup buttons are disabled until the token is re-authorized with write permission.</p>
      </div>
    ` : ""}
    ${doubleBookings.length ? `
      <div class="insight-stack caution">
        <strong class="insight-label">Possible duplicate guest bookings</strong>
        <p>Use the <strong>Booking Risks</strong> preset below to jump straight to the affected interview cards.</p>
        <div class="stack-list">
          ${doubleBookings.map((alert) => `
            <div class="mini-card">
              <strong>${alert.guest_name}</strong>
              <p>${alert.count} future bookings are holding space for the same guest.</p>
              <ul>
                ${alert.interviews.map((item) => `<li>${item.title || "Mirror Talk interview"} · ${formatDateTime(item.scheduled_for)}</li>`).join("")}
              </ul>
            </div>
          `).join("")}
        </div>
      </div>
    ` : ""}
    ${cleanup.length ? `
      <div class="insight-stack caution">
        <strong class="insight-label">Calendar cleanup needed</strong>
        <p>Use the <strong>Booking Risks</strong> preset below to focus on interviews that may still be blocking dates.</p>
        <div class="stack-list">
          ${cleanup.map((item) => `
            <div class="mini-card">
              <strong>${item.guest_name || "Guest"}</strong>
              <p>${item.title || "Mirror Talk interview"} · ${formatDateTime(item.scheduled_for)}</p>
              <p>${item.reason}</p>
              <button type="button" class="ghost-button small-button" data-alert-action="remove-calendar" data-interview-id="${item.id}">Remove From Google Calendar</button>
            </div>
          `).join("")}
        </div>
      </div>
    ` : ""}
  `;

  operationsAlerts.querySelectorAll("[data-alert-action='remove-calendar']").forEach((button) => {
    if (calendarReadOnlyMode) {
      button.disabled = true;
      button.title = "Google Calendar removal is unavailable with the current token permissions.";
      return;
    }
    button.addEventListener("click", async () => {
      const interviewId = button.dataset.interviewId;
      button.disabled = true;
      button.textContent = "Removing...";
      try {
        await fetchJSON(`/api/interviews/${interviewId}/remove-from-calendar`, {
          method: "POST",
          body: JSON.stringify({}),
        });
        setMessage(interviewMessage, "Removed the cancelled booking from Google Calendar.", "success");
        await loadOperations();
      } catch (error) {
        setMessage(interviewMessage, error.message, "error");
        button.disabled = false;
        button.textContent = "Remove From Google Calendar";
      }
    });
  });
}

function buildBookingRiskReasonMap(alerts = {}) {
  const reasonsById = new Map();
  const addReason = (interviewId, reason) => {
    const numericId = Number(interviewId);
    if (!numericId || !reason) {
      return;
    }
    const existing = reasonsById.get(numericId) || [];
    reasonsById.set(numericId, [...existing, reason]);
  };

  (alerts.double_bookings || []).forEach((group) => {
    const guestLabel = group.guest_name || "this guest";
    const count = Number(group.count || 0);
    (group.interviews || []).forEach((item) => {
      addReason(
        item.id,
        count > 1
          ? `Possible duplicate booking: ${guestLabel} currently has ${count} future interview slots reserved.`
          : `Possible duplicate booking for ${guestLabel}.`
      );
    });
  });

  (alerts.calendar_cleanup || []).forEach((item) => {
    addReason(item.id, item.reason || "This interview may still be blocking a calendar slot.");
  });

  return reasonsById;
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
  interviewForm.elements.status.value = "scheduled";
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
  interviewForm.elements.status.value = interview.status || "scheduled";
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
      ${createFieldMarkup("Status", `
        <select name="status">
          <option value="scheduled" ${normalizeText(interview.status) === "scheduled" ? "selected" : ""}>Scheduled</option>
          <option value="cancelled" ${normalizeText(interview.status) === "cancelled" ? "selected" : ""}>Cancelled</option>
        </select>
      `)}
      ${createFieldMarkup("Confirmation", `
        <select name="confirmation_status">
          <option value="pending" ${normalizeText(interview.confirmation_status) === "pending" ? "selected" : ""}>Pending</option>
          <option value="confirmed" ${normalizeText(interview.confirmation_status) === "confirmed" ? "selected" : ""}>Confirmed</option>
          <option value="tentative" ${normalizeText(interview.confirmation_status) === "tentative" ? "selected" : ""}>Tentative</option>
          <option value="declined" ${normalizeText(interview.confirmation_status) === "declined" ? "selected" : ""}>Declined</option>
          <option value="reschedule_requested" ${normalizeText(interview.confirmation_status) === "reschedule_requested" ? "selected" : ""}>Reschedule Requested</option>
        </select>
      `)}
      ${createFieldMarkup("Reminder", `
        <select name="reminder_status">
          <option value="not_scheduled" ${normalizeText(interview.reminder_status) === "not_scheduled" ? "selected" : ""}>Not Sent Yet</option>
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
  const now = new Date();
  const alerts = latestOperationsPayload.booking_alerts || {};
  const riskIds = new Set(
    (alerts.double_bookings || []).flatMap((group) => (group.interviews || []).map((item) => Number(item.id))),
  );
  const cleanupIds = new Set((alerts.calendar_cleanup || []).map((item) => Number(item.id)));

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
    const date = parseDate(interview.scheduled_for);
    const isPast = date ? date < now : false;
    if (activeInterviewPreset === "upcoming" && isPast) {
      return false;
    }
    if (activeInterviewPreset === "upcoming" && normalizeText(interview.status) === "cancelled") {
      return false;
    }
    if (activeInterviewPreset === "past" && !isPast) {
      return false;
    }
    if (activeInterviewPreset === "past" && interview.planning_episode_id) {
      return false;
    }
    if (activeInterviewPreset === "needs_confirmation" && normalizeText(interview.confirmation_status) !== "pending") {
      return false;
    }
    if (activeInterviewPreset === "booking_risks" && !(riskIds.has(Number(interview.id)) || cleanupIds.has(Number(interview.id)))) {
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

async function updateInterviewStatus(interview, payload, pendingLabel, successLabel, actionFeedbackNode) {
  activeInterviewActionFeedback = {
    id: interview.id,
    text: pendingLabel,
    tone: "pending",
  };
  actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);

  await fetchJSON(`/api/interviews/${interview.id}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

  activeInterviewActionFeedback = {
    id: interview.id,
    text: successLabel,
    tone: "success",
  };
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

  const bookingRiskReasons = buildBookingRiskReasonMap(latestOperationsPayload.booking_alerts || {});
  visibleInterviews.forEach((interview) => {
    const card = document.createElement("article");
    card.className = "operations-card";
    const riskReasons = bookingRiskReasons.get(Number(interview.id)) || [];
    const planningButtonLabel = interview.planning_episode_id ? "Update Planning Episode" : "Move To Planning";
    const calendarButton = interview.calendar_event_id
      ? `<button type="button" class="secondary-button" data-calendar-action="push">Update Google Calendar Event</button>`
      : "";
    const reminderButtons = interview.guest_email
      ? `
        <button type="button" class="ghost-button" data-interview-action="preview-booking-confirmation">Preview Booking Confirmation</button>
        <button type="button" class="primary-button" data-interview-action="send-booking-confirmation">Send Booking Confirmation</button>
        <button type="button" class="ghost-button" data-interview-action="preview-reschedule-link">Preview Reschedule Link</button>
        <button type="button" class="secondary-button" data-interview-action="send-reschedule-link">Send Reschedule Link</button>
        <button type="button" class="ghost-button" data-interview-action="preview-reminder">Preview Reminder</button>
        <button type="button" class="primary-button" data-interview-action="send-reminder">Send Reminder</button>
        <button type="button" class="ghost-button" data-interview-action="preview-cancellation">Preview Cancellation</button>
        <button type="button" class="secondary-button" data-interview-action="send-cancellation">Cancel & Email</button>
      `
      : `
        <button type="button" class="ghost-button" data-interview-action="preview-booking-confirmation" disabled>Preview Booking Confirmation</button>
        <button type="button" class="primary-button" data-interview-action="send-booking-confirmation" disabled>Send Booking Confirmation</button>
        <button type="button" class="ghost-button" data-interview-action="preview-reschedule-link" disabled>Preview Reschedule Link</button>
        <button type="button" class="secondary-button" data-interview-action="send-reschedule-link" disabled>Send Reschedule Link</button>
        <button type="button" class="ghost-button" data-interview-action="preview-reminder" disabled>Preview Reminder</button>
        <button type="button" class="primary-button" data-interview-action="send-reminder" disabled>Send Reminder</button>
        <button type="button" class="ghost-button" data-interview-action="preview-cancellation" disabled>Preview Cancellation</button>
        <button type="button" class="secondary-button" data-interview-action="send-cancellation" disabled>Cancel & Email</button>
      `;
    const confirmationTone = normalizeText(interview.confirmation_status) === "confirmed"
      ? "success"
      : normalizeText(interview.confirmation_status) === "pending"
        ? "pending"
        : "warning";
    const reminderTone = normalizeText(interview.reminder_status) === "sent" ? "success" : "pending";
    const statusTone = normalizeText(interview.status) === "cancelled" ? "warning" : "success";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h3>${interview.guest_name || "Unnamed guest"}</h3>
          <p>${interview.title || "Mirror Talk interview"}</p>
        </div>
        <div class="card-status-chips">
          <span class="status-chip ${statusTone}">${formatInterviewStatus(interview.status)}</span>
          <span class="status-chip ${confirmationTone}">${formatConfirmationStatus(interview.confirmation_status)}</span>
          <span class="status-chip ${reminderTone}">${formatReminderStatus(interview.reminder_status)}</span>
        </div>
      </div>
      <div class="operations-meta">
        <span>Scheduled: ${formatDateTime(interview.scheduled_for)}</span>
        <span>Email: ${renderLinkedValue(interview.guest_email)}</span>
        <span>Join: ${renderLinkedValue(interview.join_url)}</span>
      </div>
      ${activeInterviewPreset === "booking_risks" && riskReasons.length ? `
        <div class="operations-preview caution">
          <strong class="insight-label">Why this is in Booking Risks</strong>
          <ul>${riskReasons.map((reason) => `<li>${reason}</li>`).join("")}</ul>
        </div>
      ` : ""}
      <div class="context-links">
        <a class="context-link" href="${buildScopedLink("/dashboard", interview.guest_name || interview.guest_email)}">View Guest</a>
        <a class="context-link" href="${buildScopedLink("/planning", interview.guest_name || interview.guest_email)}">View Planning</a>
      </div>
      <div class="operations-actions">
        <div class="action-group">
          <span class="action-group-label">Core Actions</span>
          <button type="button" class="secondary-button" data-interview-action="edit">${activeInterviewEditorId === interview.id ? "Hide Quick Edit" : "Quick Edit"}</button>
          <button type="button" class="ghost-button" data-interview-action="form">Open In Form</button>
          <button type="button" class="ghost-button" data-interview-action="move-to-planning">${planningButtonLabel}</button>
          <button type="button" class="ghost-button" data-interview-action="mark-confirmed">Mark Confirmed</button>
          <button type="button" class="ghost-button" data-interview-action="mark-pending">Mark Pending</button>
        </div>
        <div class="action-group">
          <span class="action-group-label">Communication</span>
          <button type="button" class="ai-button" data-interview-action="ai-reminder" title="Generate AI-powered reminder email">\u2728 AI Reminder</button>
          <button type="button" class="ai-button" data-interview-action="ai-questions" title="Generate interview questions">\u2753 AI Questions</button>
          ${reminderButtons}
          <button type="button" class="ghost-button" data-interview-action="mark-reminder-unsent">Reminder Not Sent</button>
        </div>
        <div class="action-group">
          <span class="action-group-label">Calendar & Record</span>
          <button type="button" class="ghost-button" data-interview-action="mark-cancelled">Mark Cancelled</button>
          ${calendarButton}
          ${interview.calendar_event_id ? `<button type="button" class="ghost-button danger-button" data-calendar-action="remove" ${calendarReadOnlyMode ? "disabled title=\"Google Calendar removal is unavailable with the current token permissions.\"" : ""}>Remove From Google Calendar</button>` : ""}
          <button type="button" class="ghost-button danger-button" data-interview-action="delete">Delete</button>
        </div>
      </div>
      <div class="card-action-feedback">${activeInterviewActionFeedback.id === interview.id ? actionFeedbackMarkup(activeInterviewActionFeedback) : ""}</div>
      <div class="inline-editor hidden" data-interview-editor></div>
      <div class="operations-preview hidden" data-interview-reminder-preview></div>
    `;

    const editButton = card.querySelector("[data-interview-action='edit']");
    const formButton = card.querySelector("[data-interview-action='form']");
    const aiReminderButton = card.querySelector("[data-interview-action='ai-reminder']");
    const aiQuestionsButton = card.querySelector("[data-interview-action='ai-questions']");
    const moveToPlanningButton = card.querySelector("[data-interview-action='move-to-planning']");
    const markConfirmedButton = card.querySelector("[data-interview-action='mark-confirmed']");
    const markPendingButton = card.querySelector("[data-interview-action='mark-pending']");
    const previewBookingConfirmationButton = card.querySelector("[data-interview-action='preview-booking-confirmation']");
    const sendBookingConfirmationButton = card.querySelector("[data-interview-action='send-booking-confirmation']");
    const previewRescheduleLinkButton = card.querySelector("[data-interview-action='preview-reschedule-link']");
    const sendRescheduleLinkButton = card.querySelector("[data-interview-action='send-reschedule-link']");
    const previewReminderButton = card.querySelector("[data-interview-action='preview-reminder']");
    const sendReminderButton = card.querySelector("[data-interview-action='send-reminder']");
    const previewCancellationButton = card.querySelector("[data-interview-action='preview-cancellation']");
    const sendCancellationButton = card.querySelector("[data-interview-action='send-cancellation']");
    const markReminderUnsentButton = card.querySelector("[data-interview-action='mark-reminder-unsent']");
    const markCancelledButton = card.querySelector("[data-interview-action='mark-cancelled']");
    const calendarPushButton = card.querySelector("[data-calendar-action='push']");
    const calendarRemoveButton = card.querySelector("[data-calendar-action='remove']");
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
      setMessage(
        interviewMessage,
        `Loaded ${interview.guest_name || "interview"} into the main form. Keep the details accurate here, then move it to planning after the recording.`,
        "success",
      );
    });

    // AI Reminder Button
    if (aiReminderButton) {
      aiReminderButton.addEventListener("click", async () => {
        if (!interview.guest_email) {
          setMessage(interviewMessage, "This interview does not have a guest email yet.", "error");
          return;
        }
        await generateAIReminderEmail(interview);
      });
    }

    // AI Questions Button
    if (aiQuestionsButton) {
      aiQuestionsButton.addEventListener("click", async () => {
        await generateInterviewQuestionsForInterview(interview);
      });
    }

    moveToPlanningButton.addEventListener("click", async () => {
      const guestLabel = interview.guest_name || "guest";
      moveToPlanningButton.disabled = true;
      moveToPlanningButton.textContent = interview.planning_episode_id ? "Updating..." : "Moving...";
      activeInterviewActionFeedback = {
        id: interview.id,
        text: `${interview.planning_episode_id ? "Refreshing" : "Creating"} the planning episode for ${guestLabel}...`,
        tone: "pending",
      };
      actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
      try {
        const episode = await fetchJSON(`/api/interviews/${interview.id}/move-to-planning`, {
          method: "POST",
          body: JSON.stringify({}),
        });
        const successText = interview.planning_episode_id
          ? `Updated the planning episode for ${guestLabel}.`
          : `${guestLabel} is now in episode planning as "${episode.episode_title || guestLabel}".`;
        activeInterviewActionFeedback = { id: interview.id, text: successText, tone: "success" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        setMessage(interviewMessage, successText, "success");
        const planningTarget = `/planning?episode_id=${encodeURIComponent(episode.id)}&source=operations&q=${encodeURIComponent(
          episode.guest_name || episode.guest_email || episode.episode_title || "",
        )}`;
        window.location.assign(planningTarget);
      } catch (error) {
        activeInterviewActionFeedback = { id: interview.id, text: error.message, tone: "error" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        setMessage(interviewMessage, error.message, "error");
        moveToPlanningButton.disabled = false;
        moveToPlanningButton.textContent = planningButtonLabel;
      }
    });

    if (activeInterviewEditorId === interview.id) {
      editorNode.classList.remove("hidden");
      renderInterviewInlineEditor(editorNode, interview);
    }

    markConfirmedButton.addEventListener("click", async () => {
      markConfirmedButton.disabled = true;
      markConfirmedButton.textContent = "Confirming...";
      try {
        await updateInterviewStatus(
          interview,
          { confirmation_status: "confirmed" },
          `Marking ${interview.guest_name || "guest"} confirmed...`,
          `${interview.guest_name || "Guest"} marked confirmed.`,
          actionFeedbackNode,
        );
        setMessage(interviewMessage, `${interview.guest_name || "Guest"} marked confirmed.`, "success");
        await loadOperations();
      } catch (error) {
        activeInterviewActionFeedback = { id: interview.id, text: error.message, tone: "error" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        setMessage(interviewMessage, error.message, "error");
        markConfirmedButton.disabled = false;
        markConfirmedButton.textContent = "Mark Confirmed";
      }
    });

    markPendingButton.addEventListener("click", async () => {
      markPendingButton.disabled = true;
      markPendingButton.textContent = "Updating...";
      try {
        await updateInterviewStatus(
          interview,
          { confirmation_status: "pending" },
          `Marking ${interview.guest_name || "guest"} as pending reply...`,
          `${interview.guest_name || "Guest"} moved back to pending reply.`,
          actionFeedbackNode,
        );
        setMessage(interviewMessage, `${interview.guest_name || "Guest"} moved back to pending reply.`, "success");
        await loadOperations();
      } catch (error) {
        activeInterviewActionFeedback = { id: interview.id, text: error.message, tone: "error" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        setMessage(interviewMessage, error.message, "error");
        markPendingButton.disabled = false;
        markPendingButton.textContent = "Mark Pending";
      }
    });

    markCancelledButton.addEventListener("click", async () => {
      if (!confirmCriticalAction(`Mark ${interview.guest_name || "this guest"} as cancelled?`)) {
        return;
      }
      markCancelledButton.disabled = true;
      markCancelledButton.textContent = "Cancelling...";
      try {
        await updateInterviewStatus(
          interview,
          { status: "cancelled", confirmation_status: normalizeText(interview.confirmation_status) === "confirmed" ? interview.confirmation_status : "declined" },
          `Marking ${interview.guest_name || "guest"} as cancelled...`,
          `${interview.guest_name || "Guest"} marked cancelled.`,
          actionFeedbackNode,
        );
        setMessage(interviewMessage, `${interview.guest_name || "Guest"} marked cancelled.`, "success");
        await loadOperations();
      } catch (error) {
        activeInterviewActionFeedback = { id: interview.id, text: error.message, tone: "error" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        setMessage(interviewMessage, error.message, "error");
        markCancelledButton.disabled = false;
        markCancelledButton.textContent = "Mark Cancelled";
      }
    });

    if (previewReminderButton) {
      previewRescheduleLinkButton.addEventListener("click", async () => {
        if (!interview.guest_email) {
          setMessage(interviewMessage, "This interview does not have a guest email yet.", "error");
          return;
        }

        previewRescheduleLinkButton.disabled = true;
        previewRescheduleLinkButton.textContent = "Loading...";
        activeInterviewActionFeedback = { id: interview.id, text: `Loading reschedule email preview for ${interview.guest_name || "guest"}...`, tone: "pending" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        try {
          const preview = await fetchJSON(`/api/interviews/${interview.id}/reschedule-template`);
          reminderPreviewNode.classList.remove("hidden");
          reminderPreviewNode.innerHTML = `
            <h4>${preview.subject}</h4>
            <p>To: ${renderLinkedValue(interview.guest_email)}</p>
            <pre>${preview.body}</pre>
            <p><strong>Reschedule link:</strong> <a class="inline-link" href="${preview.reschedule_url}" target="_blank" rel="noopener">${preview.reschedule_url}</a></p>
          `;
          activeInterviewActionFeedback = { id: interview.id, text: `Reschedule email preview ready for ${interview.guest_name || "guest"}.`, tone: "success" };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        } catch (error) {
          activeInterviewActionFeedback = { id: interview.id, text: error.message, tone: "error" };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
          setMessage(interviewMessage, error.message, "error");
        } finally {
          previewRescheduleLinkButton.disabled = false;
          previewRescheduleLinkButton.textContent = "Preview Reschedule Link";
        }
      });

      sendRescheduleLinkButton.addEventListener("click", async () => {
        if (!interview.guest_email) {
          setMessage(interviewMessage, "This interview does not have a guest email yet.", "error");
          return;
        }
        if (!confirmCriticalAction(`Send the reschedule link to ${interview.guest_name || interview.guest_email || "this guest"} now?`)) {
          return;
        }

        sendRescheduleLinkButton.disabled = true;
        sendRescheduleLinkButton.textContent = "Sending...";
        activeInterviewActionFeedback = { id: interview.id, text: `Sending reschedule link to ${interview.guest_name || interview.guest_email}...`, tone: "pending" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        try {
          await fetchJSON(`/api/interviews/${interview.id}/send-reschedule-link`, {
            method: "POST",
            body: JSON.stringify({}),
          });
          reminderPreviewNode.classList.remove("hidden");
          reminderPreviewNode.innerHTML = `<p class="composer-feedback success">Reschedule link sent to ${interview.guest_name || interview.guest_email}. They can now choose a new interview slot.</p>`;
          activeInterviewActionFeedback = { id: interview.id, text: `Reschedule link sent to ${interview.guest_name || interview.guest_email}.`, tone: "success" };
          setMessage(interviewMessage, `Reschedule link sent to ${interview.guest_name || interview.guest_email}.`, "success");
          await loadOperations();
        } catch (error) {
          activeInterviewActionFeedback = { id: interview.id, text: error.message, tone: "error" };
          renderOperations();
          setMessage(interviewMessage, error.message, "error");
          sendRescheduleLinkButton.disabled = false;
          sendRescheduleLinkButton.textContent = "Send Reschedule Link";
        }
      });

      previewBookingConfirmationButton.addEventListener("click", async () => {
        if (!interview.guest_email) {
          setMessage(interviewMessage, "This interview does not have a guest email yet.", "error");
          return;
        }

        previewBookingConfirmationButton.disabled = true;
        previewBookingConfirmationButton.textContent = "Loading...";
        activeInterviewActionFeedback = { id: interview.id, text: `Loading booking confirmation preview for ${interview.guest_name || "guest"}...`, tone: "pending" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        try {
          const preview = await fetchJSON(`/api/interviews/${interview.id}/booking-confirmation-template`);
          reminderPreviewNode.classList.remove("hidden");
          reminderPreviewNode.innerHTML = `
            <h4>${preview.subject}</h4>
            <p>To: ${renderLinkedValue(interview.guest_email)}</p>
            <pre>${preview.body}</pre>
          `;
          activeInterviewActionFeedback = { id: interview.id, text: `Booking confirmation preview ready for ${interview.guest_name || "guest"}.`, tone: "success" };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        } catch (error) {
          activeInterviewActionFeedback = { id: interview.id, text: error.message, tone: "error" };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
          setMessage(interviewMessage, error.message, "error");
        } finally {
          previewBookingConfirmationButton.disabled = false;
          previewBookingConfirmationButton.textContent = "Preview Booking Confirmation";
        }
      });

      sendBookingConfirmationButton.addEventListener("click", async () => {
        if (!interview.guest_email) {
          setMessage(interviewMessage, "This interview does not have a guest email yet.", "error");
          return;
        }
        if (!confirmCriticalAction(`Send the booking confirmation email and calendar invite to ${interview.guest_name || interview.guest_email || "this guest"} now?`)) {
          return;
        }

        sendBookingConfirmationButton.disabled = true;
        sendBookingConfirmationButton.textContent = "Sending...";
        activeInterviewActionFeedback = { id: interview.id, text: `Sending booking confirmation to ${interview.guest_name || interview.guest_email}...`, tone: "pending" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        try {
          await fetchJSON(`/api/interviews/${interview.id}/send-booking-confirmation`, {
            method: "POST",
            body: JSON.stringify({}),
          });
          reminderPreviewNode.classList.remove("hidden");
          reminderPreviewNode.innerHTML = `<p class="composer-feedback success">Booking confirmation sent to ${interview.guest_name || interview.guest_email}, including the calendar invite.</p>`;
          activeInterviewActionFeedback = { id: interview.id, text: `Booking confirmation sent to ${interview.guest_name || interview.guest_email}.`, tone: "success" };
          setMessage(interviewMessage, `Booking confirmation sent to ${interview.guest_name || interview.guest_email}.`, "success");
          await loadOperations();
        } catch (error) {
          activeInterviewActionFeedback = { id: interview.id, text: error.message, tone: "error" };
          renderOperations();
          setMessage(interviewMessage, error.message, "error");
          sendBookingConfirmationButton.disabled = false;
          sendBookingConfirmationButton.textContent = "Send Booking Confirmation";
        }
      });

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
            <p>To: ${renderLinkedValue(interview.guest_email)}</p>
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
        if (!confirmCriticalAction(`Send the reminder email to ${interview.guest_name || interview.guest_email || "this guest"} now?`)) {
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

    if (previewCancellationButton) {
      previewCancellationButton.addEventListener("click", async () => {
        if (!interview.guest_email) {
          setMessage(interviewMessage, "This interview does not have a guest email yet.", "error");
          return;
        }

        previewCancellationButton.disabled = true;
        previewCancellationButton.textContent = "Loading...";
        activeInterviewActionFeedback = { id: interview.id, text: `Loading cancellation preview for ${interview.guest_name || "guest"}...`, tone: "pending" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        try {
          const preview = await fetchJSON(`/api/interviews/${interview.id}/cancellation-template`);
          reminderPreviewNode.classList.remove("hidden");
          reminderPreviewNode.innerHTML = `
            <h4>${preview.subject}</h4>
            <p>To: ${renderLinkedValue(interview.guest_email)}</p>
            <pre>${preview.body}</pre>
          `;
          activeInterviewActionFeedback = { id: interview.id, text: `Cancellation preview ready for ${interview.guest_name || "guest"}.`, tone: "success" };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        } catch (error) {
          activeInterviewActionFeedback = { id: interview.id, text: error.message, tone: "error" };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
          setMessage(interviewMessage, error.message, "error");
        } finally {
          previewCancellationButton.disabled = false;
          previewCancellationButton.textContent = "Preview Cancellation";
        }
      });
    }

    if (sendCancellationButton) {
      sendCancellationButton.addEventListener("click", async () => {
        if (!interview.guest_email) {
          setMessage(interviewMessage, "This interview does not have a guest email yet.", "error");
          return;
        }
        if (!confirmCriticalAction(`Send the cancellation email to ${interview.guest_name || interview.guest_email || "this guest"} and mark this interview cancelled?`)) {
          return;
        }

        sendCancellationButton.disabled = true;
        sendCancellationButton.textContent = "Sending...";
        activeInterviewActionFeedback = { id: interview.id, text: `Sending cancellation to ${interview.guest_name || interview.guest_email}...`, tone: "pending" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        try {
          await fetchJSON(`/api/interviews/${interview.id}/send-cancellation`, {
            method: "POST",
            body: JSON.stringify({}),
          });
          reminderPreviewNode.classList.remove("hidden");
          reminderPreviewNode.innerHTML = `<p class="composer-feedback success">Cancellation email sent to ${interview.guest_name || interview.guest_email}. Interview marked cancelled.</p>`;
          activeInterviewActionFeedback = { id: interview.id, text: `Cancellation email sent to ${interview.guest_name || interview.guest_email}.`, tone: "success" };
          setMessage(interviewMessage, `Cancellation email sent to ${interview.guest_name || interview.guest_email}. Interview marked cancelled.`, "success");
          await loadOperations();
        } catch (error) {
          activeInterviewActionFeedback = { id: interview.id, text: error.message, tone: "error" };
          renderOperations();
          setMessage(interviewMessage, error.message, "error");
          sendCancellationButton.disabled = false;
          sendCancellationButton.textContent = "Cancel & Email";
        }
      });
    }

    markReminderUnsentButton.addEventListener("click", async () => {
      markReminderUnsentButton.disabled = true;
      markReminderUnsentButton.textContent = "Updating...";
      try {
        await updateInterviewStatus(
          interview,
          { reminder_status: "not_scheduled" },
          `Resetting reminder status for ${interview.guest_name || "guest"}...`,
          `${interview.guest_name || "Guest"} marked as not sent yet.`,
          actionFeedbackNode,
        );
        setMessage(interviewMessage, `${interview.guest_name || "Guest"} marked as not sent yet.`, "success");
        await loadOperations();
      } catch (error) {
        activeInterviewActionFeedback = { id: interview.id, text: error.message, tone: "error" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        setMessage(interviewMessage, error.message, "error");
        markReminderUnsentButton.disabled = false;
        markReminderUnsentButton.textContent = "Reminder Not Sent";
      }
    });

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

    if (calendarRemoveButton) {
      calendarRemoveButton.addEventListener("click", async () => {
        if (!confirmCriticalAction(`Remove ${interview.guest_name || "this guest"} from Google Calendar?`)) {
          return;
        }
        calendarRemoveButton.disabled = true;
        calendarRemoveButton.textContent = "Removing...";
        activeInterviewActionFeedback = { id: interview.id, text: `Removing ${interview.guest_name || "guest"} from Google Calendar...`, tone: "pending" };
        actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
        try {
          await fetchJSON(`/api/interviews/${interview.id}/remove-from-calendar`, {
            method: "POST",
            body: JSON.stringify({}),
          });
          activeInterviewActionFeedback = { id: interview.id, text: `${interview.guest_name || "Guest"} removed from Google Calendar.`, tone: "success" };
          setMessage(interviewMessage, `${interview.guest_name || "Guest"} removed from Google Calendar.`, "success");
          await loadOperations();
        } catch (error) {
          if (error.message.includes("read-only mode")) {
            calendarReadOnlyMode = true;
            await loadOperations();
            setMessage(interviewMessage, error.message, "error");
            return;
          }
          activeInterviewActionFeedback = { id: interview.id, text: error.message, tone: "error" };
          actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
          setMessage(interviewMessage, error.message, "error");
          calendarRemoveButton.disabled = false;
          calendarRemoveButton.textContent = "Remove From Google Calendar";
        }
      });
    }

    deleteButton.addEventListener("click", async () => {
      const label = interview.guest_name || "this interview";
      const typedLabel = promptExactMatch(label, "delete this interview");
      if (typedLabel === null) {
        return;
      }
      if (typedLabel === false) {
        setMessage(interviewMessage, `Deletion cancelled. Type ${label} exactly to remove this interview.`, "error");
        return;
      }

      deleteButton.disabled = true;
      deleteButton.textContent = "Deleting...";
      activeInterviewActionFeedback = { id: interview.id, text: `Deleting ${label}...`, tone: "pending" };
      actionFeedbackNode.innerHTML = actionFeedbackMarkup(activeInterviewActionFeedback);
      try {
        await fetchJSON(`/api/interviews/${interview.id}`, {
          method: "DELETE",
          body: JSON.stringify({ confirm_label: typedLabel }),
        });
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
      <p>${interview.title || "Soulful Conversation"}</p>
      <div class="operations-meta">
        <span>Scheduled: ${interview.scheduled_for_display || formatDateTime(interview.scheduled_for)}</span>
        <span>Email: ${renderLinkedValue(interview.guest_email)}</span>
        <span>Confirmation: ${formatConfirmationStatus(interview.confirmation_status)}</span>
      </div>
      <div class="context-links">
        <a class="context-link" href="${buildScopedLink("/dashboard", interview.guest_name || interview.guest_email)}">View Guest</a>
      </div>
      <div class="operations-actions">
        <button type="button" class="ghost-button" data-reminder-action="mark-confirmed">Mark Confirmed</button>
        <button type="button" class="secondary-button" data-reminder-action="preview">Preview Email</button>
        <button type="button" class="primary-button" data-reminder-action="send">Send Reminder</button>
      </div>
      <div class="operations-preview hidden"></div>
    `;

    const previewPanel = card.querySelector(".operations-preview");
    const markConfirmedButton = card.querySelector("[data-reminder-action='mark-confirmed']");
    const previewButton = card.querySelector("[data-reminder-action='preview']");
    const sendButton = card.querySelector("[data-reminder-action='send']");

    markConfirmedButton.addEventListener("click", async () => {
      markConfirmedButton.disabled = true;
      markConfirmedButton.textContent = "Confirming...";
      try {
        await fetchJSON(`/api/interviews/${interview.id}`, {
          method: "POST",
          body: JSON.stringify({ confirmation_status: "confirmed" }),
        });
        setMessage(reminderMessage, `${interview.guest_name || "Guest"} marked confirmed.`, "success");
        await loadOperations();
      } catch (error) {
        setMessage(reminderMessage, error.message, "error");
        markConfirmedButton.disabled = false;
        markConfirmedButton.textContent = "Mark Confirmed";
      }
    });

    previewButton.addEventListener("click", async () => {
      try {
        const preview = await fetchJSON(`/api/interviews/${interview.id}/reminder-template`);
        card.classList.add("selected");
        previewPanel.classList.remove("hidden");
        previewPanel.innerHTML = `
          <h4>${preview.subject}</h4>
          <p>To: ${renderLinkedValue(interview.guest_email, "No email address")}</p>
          <pre>${preview.body}</pre>
        `;
      } catch (error) {
        setMessage(reminderMessage, error.message, "error");
      }
    });

    sendButton.addEventListener("click", async () => {
      if (!confirmCriticalAction(`Send the reminder email to ${interview.guest_name || interview.guest_email || "this guest"} now?`)) {
        return;
      }
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
  renderWeeklyOutreachPanel();
  renderOperationsAlerts();
  renderReminderCandidates(filterReminderCandidates(reminders), reminders.length);
  renderInterviews(filterAndSortInterviews(interviews), interviews.length);
}

async function loadOperations() {
  if (!latestOperationsPayload.interviews?.length && !latestOperationsPayload.reminder_candidates?.length) {
    renderSkeletonCards(interviewList, 4);
    renderSkeletonCards(reminderList, 2);
    const cachedPayload = readCachedPayload(OPERATIONS_PAYLOAD_CACHE_KEY);
    // Only use cache if it has meaningful data (not all zeros)
    const hasData = cachedPayload && (
      (cachedPayload.stats?.interviews_total ?? 0) > 0 ||
      (cachedPayload.interviews?.length ?? 0) > 0 ||
      (cachedPayload.reminder_candidates?.length ?? 0) > 0
    );
    
    if (hasData) {
      latestOperationsPayload = cachedPayload;
      const interviews = cachedPayload.interviews || [];
      stats.interviewsTotal.textContent = cachedPayload.stats?.interviews_total ?? interviews.length ?? 0;
      stats.interviewsPending.textContent = cachedPayload.stats?.interviews_pending_confirmation ?? 0;
      stats.interviewsConfirmed.textContent = interviews.filter((item) => item.confirmation_status === "confirmed").length;
      stats.remindersDue.textContent = cachedPayload.reminder_candidates?.length ?? 0;
      renderOperations();
      setMessage(interviewMessage, "Refreshing interview operations...", "pending");
    } else {
      setMessage(interviewMessage, "Loading interview operations...", "pending");
    }
  }
  const payload = await fetchJSON("/api/operations");
  latestOperationsPayload = payload;
  const interviews = payload.interviews || [];
  stats.interviewsTotal.textContent = payload.stats.interviews_total ?? interviews.length ?? 0;
  stats.interviewsPending.textContent = payload.stats.interviews_pending_confirmation ?? 0;
  stats.interviewsConfirmed.textContent = interviews.filter((item) => item.confirmation_status === "confirmed").length;
  stats.remindersDue.textContent = payload.reminder_candidates?.length ?? 0;
  renderOperations();
  storeCachedPayload(OPERATIONS_PAYLOAD_CACHE_KEY, payload);
  if (interviewMessage.classList.contains("pending")) {
    setMessage(interviewMessage, "", "");
  }
}

interviewForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(interviewForm).entries());
  const interviewId = payload.id;
  const submitButton = interviewForm.querySelector("button[type='submit']");
  delete payload.id;
  submitButton.disabled = true;
  submitButton.textContent = interviewId ? "Saving..." : "Creating...";
  setMessage(interviewMessage, interviewId ? "Saving interview changes..." : "Saving interview...", "pending");

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
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = interviewId ? "Update Interview" : "Save Interview";
  }
});

interviewResetButton.addEventListener("click", () => {
  resetInterviewForm();
  setMessage(interviewMessage, "Back to creating a new interview.", "success");
});

refreshButton.addEventListener("click", async () => {
  refreshButton.disabled = true;
  refreshButton.textContent = "Refreshing...";
  setMessage(interviewMessage, "Refreshing interview operations...", "pending");
  try {
    await loadOperations();
  } catch (error) {
    setMessage(interviewMessage, error.message, "error");
  } finally {
    refreshButton.disabled = false;
    refreshButton.textContent = "Refresh";
  }
});

syncCalendarButton.addEventListener("click", async () => {
  syncCalendarButton.disabled = true;
  syncCalendarButton.textContent = "Syncing...";
  setMessage(interviewMessage, "Syncing Google Calendar...", "pending");
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
  } finally {
    syncCalendarButton.disabled = false;
    syncCalendarButton.textContent = "Sync Google Calendar";
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
    activeInterviewPreset = button.dataset.interviewPreset || "upcoming";
    visibleInterviewCount = INTERVIEW_PAGE_SIZE;
    if (activeInterviewPreset === "needs_confirmation") {
      interviewConfirmationFilter.value = "pending";
    } else if (activeInterviewPreset === "upcoming") {
      interviewConfirmationFilter.value = "";
    }
    renderOperations();
  });
});

function applyUrlState() {
  const params = new URLSearchParams(window.location.search);
  const query = params.get("q");
  const preset = params.get("preset");
  const tab = params.get("tab");

  if (query) {
    interviewSearchInput.value = query;
    reminderSearchInput.value = query;
  }
  if (preset && interviewPresetButtons.some((button) => button.dataset.interviewPreset === preset)) {
    activeInterviewPreset = preset;
  }
  if (tab && operationsTabButtons.some((button) => button.dataset.operationsTab === tab)) {
    activeOperationsTab = tab;
  }
  setOperationsTab(activeOperationsTab);
}

operationsTabButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setOperationsTab(button.dataset.operationsTab || "upcoming_interviews");
  });
});

resetInterviewForm();
applyUrlState();
loadOperations().catch((error) => {
  setMessage(interviewMessage, error.message, "error");
});

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

async function generateAIReminderEmail(interview) {
  if (!aiEnabled) {
    alert("AI features are not available. Please configure OPENAI_API_KEY.");
    return;
  }

  if (!interview.guest_email) {
    alert("This interview does not have a guest email.");
    return;
  }

  const customNote = prompt(`Add a custom note for the reminder email (optional):`);
  const noteParam = customNote ? `&note=${encodeURIComponent(customNote)}` : "";
  
  try {
    showAIModal(`✨ AI Reminder Email: ${interview.guest_name}`, `<p class="loading">Generating reminder email...</p>`);
    
    // We'll use the acceptance email endpoint as a template, or create a new endpoint
    // For now, generate a custom reminder based on interview details
    const interviewDate = new Date(interview.scheduled_for).toLocaleString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
    
    const reminderText = `Interview Reminder: ${interview.guest_name}

Scheduled for: ${interviewDate}
Title: ${interview.title || 'Mirror Talk Interview'}
${interview.join_url ? `Join URL: ${interview.join_url}` : ''}

${customNote ? `Note: ${customNote}` : ''}

This is a reminder email for your upcoming Mirror Talk podcast interview. AI-powered email generation coming soon with full customization.`;

    const content = `
      <div class="ai-email-draft">
        <div class="email-field">
          <label><strong>To:</strong></label>
          <p>${escapeHtml(interview.guest_name || interview.guest_email)}</p>
        </div>
        <div class="email-field">
          <label><strong>Subject:</strong></label>
          <input type="text" class="email-subject-input" value="Reminder: Your Mirror Talk Interview on ${new Date(interview.scheduled_for).toLocaleDateString()}" />
        </div>
        <div class="email-field">
          <label><strong>Body:</strong></label>
          <textarea class="email-body-input" rows="15">${escapeHtml(reminderText)}</textarea>
        </div>
        <p class="ai-note">💡 <em>Review and edit before sending. You can copy this draft or use the standard reminder buttons.</em></p>
      </div>
    `;
    
    showAIModal(`✨ AI Reminder: ${interview.guest_name}`, content);
  } catch (error) {
    showAIModal("Error", `<p class="error">Failed to generate reminder: ${escapeHtml(error.message)}</p>`);
  }
}

async function generateInterviewQuestionsForInterview(interview) {
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
    showAIModal(`❓ Interview Questions for ${interview.guest_name}`, `<p class="loading">Generating ${num} personalized questions...</p>`);
    
    // Try to find the guest in the database and use their guest_id
    // For now, create generic questions based on interview info
    const questionsText = `Interview Questions for ${interview.guest_name}

Based on the upcoming interview:
Title: ${interview.title || 'Mirror Talk Interview'}
Scheduled: ${new Date(interview.scheduled_for).toLocaleDateString()}

Note: To get personalized AI questions, this guest needs to be in the guest database. You can view their profile from the "View Guest" link on the interview card.

Generic interview starter questions:
1. What brought you to your current work or passion?
2. Can you share a pivotal moment that shaped your journey?
3. What challenges have you faced, and what did you learn?
4. How do you approach creativity or problem-solving in your field?
5. What advice would you give to someone starting in this area?
6. What projects are you most excited about right now?
7. How do you balance different aspects of your work and life?
8. Who or what has influenced you most in your journey?
9. What questions do you wish people would ask you?
10. Where do you see yourself or your work heading in the future?`;

    const questionsList = questionsText.split('\n').filter(line => line.match(/^\d+\./))
      .map((q, i) => `<li><strong>${i + 1}.</strong> ${escapeHtml(q.replace(/^\d+\.\s*/, ''))}</li>`)
      .join("");
    
    const content = `
      <div class="ai-questions">
        <p class="ai-note">Generated questions for <strong>${escapeHtml(interview.guest_name)}</strong></p>
        <ol class="questions-list">${questionsList}</ol>
        <p class="ai-note">💡 <em>For personalized AI questions based on the guest's application, use the "View Guest" link to access their profile on the dashboard and click "AI Questions" there.</em></p>
      </div>
    `;
    
    showAIModal(`❓ Interview Questions: ${interview.guest_name}`, content);
  } catch (error) {
    showAIModal("Error", `<p class="error">Failed to generate questions: ${escapeHtml(error.message)}</p>`);
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

// Check AI status on load
checkAIStatus();
