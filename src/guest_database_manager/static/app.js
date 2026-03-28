const form = document.getElementById("guest-form");
const message = document.getElementById("form-message");
const guestList = document.getElementById("guest-list");
const template = document.getElementById("guest-card-template");
const refreshButton = document.getElementById("refresh-button");

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

function setMessage(text, tone = "") {
  message.textContent = text;
  message.className = `message ${tone}`.trim();
}

function guestStatusLabel(guest) {
  if (guest.email_status) {
    return guest.email_status;
  }
  return guest.is_processed ? "processed" : "unprocessed";
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
          if (action === "delete") {
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

refreshButton.addEventListener("click", async () => {
  await loadGuests();
});

loadGuests();
