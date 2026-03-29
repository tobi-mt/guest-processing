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
const guestLoadMoreButton = document.getElementById("guest-load-more");
const guestPresetButtons = Array.from(document.querySelectorAll("[data-guest-preset]"));

const GUEST_PAGE_SIZE = 12;

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
let activeGuestEditor = null;
let activeGuestPreset = "all";
let activeGuestActionFeedback = null;
let visibleGuestCount = GUEST_PAGE_SIZE;

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

function normalizeText(value) {
  return String(value || "").trim().toLowerCase();
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
  if (preset === "all") return true;
  if (preset === "needs_review") return !guest.is_processed;
  if (preset === "accepted") return guestStatusLabel(guest) === "accepted";
  if (preset === "rejected") return guestStatusLabel(guest) === "rejected";
  if (preset === "no_email") return !normalizeText(guest.email);
  return true;
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
        <input name="website" type="url" value="${escapeHtml(activeGuestEditor.website)}" />
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

    node.querySelector(".guest-name").textContent = guest.full_name || "Unnamed Guest";
    node.querySelector(".guest-meta").textContent = guest.email || "No email provided";
    node.querySelector(".guest-summary").textContent =
      guest.background || guest.additional_info || "No background added yet.";

    statusPill.textContent = guestStatusLabel(guest);
    statusPill.classList.add(guestStatusLabel(guest));

    if (!emailEnabled) {
      node.querySelectorAll("[data-action='accepted_email'], [data-action='rejected_email']").forEach((button) => {
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
    if (guest.passionate_topics) details.push(`Topics: ${guest.passionate_topics}`);
    if (guest.original_file_name) details.push(`Source: ${guest.original_file_name}`);
    node.querySelector(".guest-details").innerHTML = details.map((detail) => `<span>${detail}</span>`).join("");
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
          } else if (action === "delete") {
            activeGuestActionFeedback = { guestId: guest.id, text: `Deleting ${guest.full_name || "guest"}...`, tone: "pending" };
            renderGuests(latestPayload);
            await fetchJSON(`/api/guests/${guest.id}`, { method: "DELETE" });
            activeGuestActionFeedback = null;
            setMessage(`Deleted ${guest.full_name}.`, "success");
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
  visibleGuestCount = GUEST_PAGE_SIZE;
  if (latestPayload) {
    renderGuests(latestPayload);
  }
});

guestSearch.addEventListener("input", () => {
  visibleGuestCount = GUEST_PAGE_SIZE;
  if (latestPayload) {
    renderGuests(latestPayload);
  }
});

guestSort.addEventListener("change", () => {
  if (latestPayload) {
    renderGuests(latestPayload);
  }
});

guestLoadMoreButton.addEventListener("click", () => {
  visibleGuestCount += GUEST_PAGE_SIZE;
  if (latestPayload) {
    renderGuests(latestPayload);
  }
});

guestPresetButtons.forEach((button) => {
  button.addEventListener("click", () => {
    activeGuestPreset = button.dataset.guestPreset || "all";
    visibleGuestCount = GUEST_PAGE_SIZE;
    if (activeGuestPreset === "accepted" || activeGuestPreset === "rejected") {
      decisionFilter.value = activeGuestPreset;
    } else if (activeGuestPreset === "needs_review") {
      decisionFilter.value = "unprocessed";
    } else {
      decisionFilter.value = "all";
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

applyUrlState();
loadGuests();
