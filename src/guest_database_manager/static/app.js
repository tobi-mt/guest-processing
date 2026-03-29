const form = document.getElementById("guest-form");
const importForm = document.getElementById("import-form");
const importMessage = document.getElementById("import-message");
const message = document.getElementById("form-message");
const guestList = document.getElementById("guest-list");
const template = document.getElementById("guest-card-template");
const refreshButton = document.getElementById("refresh-button");
const exportButton = document.getElementById("export-button");
const decisionFilter = document.getElementById("decision-filter");
const guestSearch = document.getElementById("guest-search");
const guestSort = document.getElementById("guest-sort");
const guestResultsMeta = document.getElementById("guest-results-meta");

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

let emailEnabled = false;
let latestPayload = null;
let activeEmailComposer = null;

function composerFeedbackMarkup(feedback) {
  if (!feedback?.text) {
    return "";
  }

  return `<p class="composer-feedback ${feedback.tone || ""}">${escapeHtml(feedback.text)}</p>`;
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

async function fetchUpload(url, formData) {
  const response = await fetch(url, {
    method: "POST",
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
  message.textContent = text;
  message.className = `message ${tone}`.trim();
}

function setImportMessage(text, tone = "") {
  importMessage.textContent = text;
  importMessage.className = `message ${tone}`.trim();
}

function guestStatusLabel(guest) {
  if (guest.email_status) {
    return guest.email_status;
  }
  return guest.is_processed ? "processed" : "unprocessed";
}

function guestMatchesFilter(guest, filterValue) {
  if (filterValue === "all") {
    return true;
  }

  if (filterValue === "processed") {
    return Boolean(guest.is_processed);
  }

  if (filterValue === "unprocessed") {
    return !guest.is_processed;
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

  const haystack = [guest.full_name, guest.email, guest.website, guest.profession, guest.original_file_name]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  return haystack.includes(normalizedQuery);
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

function updateResultsMeta(shown, total) {
  if (!total) {
    guestResultsMeta.textContent = "No guests in the pipeline yet.";
    return;
  }
  if (shown === total) {
    guestResultsMeta.textContent = `Showing all ${total} guest${total === 1 ? "" : "s"}.`;
    return;
  }
  guestResultsMeta.textContent = `Showing ${shown} of ${total} guests after search and decision filtering.`;
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

function renderGuests(payload) {
  latestPayload = payload;
  emailEnabled = Boolean(payload.email_enabled);
  metrics.total.textContent = payload.stats.total ?? 0;
  metrics.processed.textContent = payload.stats.processed ?? 0;
  metrics.unprocessed.textContent = payload.stats.unprocessed ?? 0;

  const accepted = payload.email_stats.accepted_emails ?? 0;
  const rejected = payload.email_stats.rejected_emails ?? 0;
  const skipped = payload.email_stats.skipped_guests ?? 0;
  const decided = accepted + rejected + skipped;

  insights.accepted.textContent = accepted;
  insights.rejected.textContent = rejected;
  insights.skipped.textContent = skipped;
  insights.acceptanceRate.textContent = decided ? `${Math.round((accepted / decided) * 100)}%` : "0%";

  const activeFilter = decisionFilter.value;
  const searchQuery = guestSearch.value;
  const guests = sortGuests(payload.guests.filter(
    (guest) => guestMatchesFilter(guest, activeFilter) && guestMatchesSearch(guest, searchQuery),
  ), guestSort.value);

  guestList.innerHTML = "";
  updateResultsMeta(guests.length, payload.guests.length);
  if (!guests.length) {
    if (payload.guests.length) {
      guestList.innerHTML = "<p class='guest-summary'>No guests match the current search and decision filter.</p>";
    } else {
    guestList.innerHTML = "<p class='guest-summary'>No guests yet. Add the first one with the form.</p>";
    }
    return;
  }

  guests.forEach((guest) => {
    const node = template.content.cloneNode(true);
    const card = node.querySelector(".guest-card");
    const statusPill = node.querySelector(".status-pill");
    const composer = node.querySelector(".email-composer");

    node.querySelector(".guest-name").textContent = guest.full_name || "Unnamed Guest";
    node.querySelector(".guest-meta").textContent = guest.email || "No email provided";
    node.querySelector(".guest-summary").textContent =
      guest.background || guest.additional_info || "No background added yet.";

    statusPill.textContent = guestStatusLabel(guest);
    statusPill.classList.add(guestStatusLabel(guest));

    if (!emailEnabled) {
      node.querySelectorAll("[data-action='accepted_email'], [data-action='rejected_email']").forEach((button) => {
        button.disabled = true;
        button.title = "Set the dashboard SMTP environment variables on Railway to enable email sending.";
      });
    }

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
    if (guest.social_media_handles) details.push(`Social: ${guest.social_media_handles}`);
    if (guest.original_file_name) details.push(`Source: ${guest.original_file_name}`);
    node.querySelector(".guest-details").innerHTML = details.map((detail) => `<span>${detail}</span>`).join("");

    node.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", async () => {
        const action = button.dataset.action;

        try {
          if (action === "copy") {
            await copyGuestIntake(guest);
            setMessage(`Copied ${guest.full_name}'s intake details.`, "success");
          } else if (action === "accepted_email" || action === "rejected_email") {
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
          } else if (action === "delete") {
            await fetchJSON(`/api/guests/${guest.id}`, { method: "DELETE" });
            setMessage(`Deleted ${guest.full_name}.`, "success");
          } else if (action === "skipped") {
            const skipReason = window.prompt("Optional skip reason:") || "";
            await fetchJSON(`/api/guests/${guest.id}/status`, {
              method: "POST",
              body: JSON.stringify({ status: action, skip_reason: skipReason }),
            });
            setMessage(`Updated ${guest.full_name} to skipped.`, "success");
          } else {
            await fetchJSON(`/api/guests/${guest.id}/status`, {
              method: "POST",
              body: JSON.stringify({ status: action }),
            });
            setMessage(`Updated ${guest.full_name} to ${action}.`, "success");
          }

          await loadGuests();
        } catch (error) {
          setMessage(error.message, "error");
        }
      });
    });

    guestList.appendChild(card);
  });
}

async function loadGuests() {
  try {
    const payload = await fetchJSON("/api/guests");
    renderGuests(payload);
  } catch (error) {
    setMessage(error.message, "error");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(form);
  const payload = Object.fromEntries(formData.entries());

  try {
    await fetchJSON("/api/guests", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    form.reset();
    setMessage("Guest saved directly to the database.", "success");
    await loadGuests();
  } catch (error) {
    setMessage(error.message, "error");
  }
});

importForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(importForm);
  const uploadedFile = formData.get("file");

  if (!(uploadedFile instanceof File) || !uploadedFile.name) {
    setImportMessage("Please choose a CSV or Excel file.", "error");
    return;
  }

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
  }
});

refreshButton.addEventListener("click", async () => {
  await loadGuests();
});

exportButton.addEventListener("click", () => {
  window.location.href = "/api/export";
});

decisionFilter.addEventListener("change", () => {
  if (latestPayload) {
    renderGuests(latestPayload);
  }
});

guestSearch.addEventListener("input", () => {
  if (latestPayload) {
    renderGuests(latestPayload);
  }
});

guestSort.addEventListener("change", () => {
  if (latestPayload) {
    renderGuests(latestPayload);
  }
});

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

loadGuests();
