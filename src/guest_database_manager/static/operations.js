const interviewForm = document.getElementById("interview-form");
const episodeForm = document.getElementById("episode-form");
const interviewMessage = document.getElementById("interview-message");
const episodeMessage = document.getElementById("episode-message");
const reminderMessage = document.getElementById("reminder-message");
const reminderList = document.getElementById("reminder-list");
const interviewList = document.getElementById("interview-list");
const episodeList = document.getElementById("episode-list");
const refreshButton = document.getElementById("operations-refresh-button");
const sendWeeklyRemindersButton = document.getElementById("send-weekly-reminders-button");
const syncCalendarButton = document.getElementById("sync-calendar-button");
let latestReminderCandidates = [];

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
        <span>Priority: ${episode.priority_score ?? 0}</span>
      </div>
    `;
    episodeList.appendChild(card);
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
  renderReminderCandidates(payload.reminder_candidates || []);
  renderInterviews(payload.interviews);
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
    episodeForm.elements.priority_score.value = "0";
    setMessage(episodeMessage, "Episode saved.", "success");
    await loadOperations();
  } catch (error) {
    setMessage(episodeMessage, error.message, "error");
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

loadOperations().catch((error) => {
  setMessage(interviewMessage, error.message, "error");
});
