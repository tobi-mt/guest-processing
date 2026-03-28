const form = document.getElementById("guest-form");
const importForm = document.getElementById("import-form");
const importMessage = document.getElementById("import-message");
const message = document.getElementById("form-message");
const guestList = document.getElementById("guest-list");
const template = document.getElementById("guest-card-template");
const refreshButton = document.getElementById("refresh-button");
const exportButton = document.getElementById("export-button");

const metrics = {
  total: document.getElementById("metric-total"),
  processed: document.getElementById("metric-processed"),
  unprocessed: document.getElementById("metric-unprocessed"),
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
  metrics.total.textContent = payload.stats.total ?? 0;
  metrics.processed.textContent = payload.stats.processed ?? 0;
  metrics.unprocessed.textContent = payload.stats.unprocessed ?? 0;

  guestList.innerHTML = "";
  if (!payload.guests.length) {
    guestList.innerHTML = "<p class='guest-summary'>No guests yet. Add the first one with the form.</p>";
    return;
  }

  payload.guests.forEach((guest) => {
    const node = template.content.cloneNode(true);
    const card = node.querySelector(".guest-card");
    const statusPill = node.querySelector(".status-pill");

    node.querySelector(".guest-name").textContent = guest.full_name || "Unnamed Guest";
    node.querySelector(".guest-meta").textContent = guest.email || "No email provided";
    node.querySelector(".guest-summary").textContent =
      guest.background || guest.additional_info || "No background added yet.";

    statusPill.textContent = guestStatusLabel(guest);
    statusPill.classList.add(guestStatusLabel(guest));

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

loadGuests();
