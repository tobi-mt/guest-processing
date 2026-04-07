const bookingMessage = document.getElementById("booking-message");
const bookingSubtitle = document.getElementById("booking-subtitle");
const bookingExisting = document.getElementById("booking-existing");
const bookingMeta = document.getElementById("booking-meta");
const bookingSlots = document.getElementById("booking-slots");
const bookingForm = document.getElementById("booking-form");
const bookingSubmit = document.getElementById("booking-submit");
const bookingTitle = document.getElementById("booking-title");
const panelHeading = document.getElementById("panel-heading");
const bookingInvitation = document.getElementById("booking-invitation");

let bookingToken = "";
let selectedSlot = null;

function setMessage(text, tone = "") {
  bookingMessage.textContent = text;
  bookingMessage.className = `message ${tone}`.trim();
}

function showInvitationState() {
  bookingInvitation.classList.remove("hidden");
  bookingMeta.classList.add("hidden");
  bookingExisting.classList.add("hidden");
  bookingSlots.innerHTML = "";
  bookingForm.classList.add("hidden");
  bookingTitle.textContent = "Your Mirror Talk invitation link opens here";
  panelHeading.textContent = "A personal booking link keeps the experience secure and connected";
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

function formatSlot(dateText) {
  const date = new Date(dateText);
  return date.toLocaleString(undefined, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderExistingBooking(existing) {
  if (!existing) {
    bookingExisting.classList.add("hidden");
    bookingExisting.innerHTML = "";
    return;
  }
  bookingExisting.classList.remove("hidden");
  bookingExisting.innerHTML = `
    <strong>You already have a booking</strong>
    <p>${formatSlot(existing.scheduled_for)}${existing.timezone ? ` · ${existing.timezone}` : ""}</p>
    ${existing.join_url ? `<p>Your recording link: <a href="${existing.join_url}" target="_blank" rel="noopener">${existing.join_url}</a></p>` : ""}
    <p>If you need to reschedule, please reply to the email you received from Mirror Talk and we’ll support you directly.</p>
  `;
}

function renderSlots(slots, timezone) {
  bookingSlots.innerHTML = "";
  if (!slots.length) {
    bookingSlots.innerHTML = "<p>No booking slots are available right now. Please check back later or reply to the acceptance email.</p>";
    bookingForm.classList.add("hidden");
    return;
  }

  slots.forEach((slot) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "slot-card";
    button.innerHTML = `
      <strong>${formatSlot(slot.start)}</strong>
      <span>${timezone}</span>
    `;
    button.addEventListener("click", () => {
      selectedSlot = slot;
      bookingForm.elements.scheduled_for.value = slot.start;
      bookingSubmit.disabled = false;
      bookingSubmit.textContent = "Book This Slot";
      bookingSlots.querySelectorAll(".slot-card").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
    });
    bookingSlots.appendChild(button);
  });

  bookingForm.classList.remove("hidden");
}

async function loadBookingPage() {
  const params = new URLSearchParams(window.location.search);
  bookingToken = params.get("token") || "";
  if (!bookingToken) {
    showInvitationState();
    setMessage("This page is opened through a personal Mirror Talk invitation link. Please use the booking link sent to your email.", "success");
    return;
  }

  try {
    bookingInvitation.classList.add("hidden");
    setMessage("Loading your booking page...", "pending");
    const [context, availability] = await Promise.all([
      fetchJSON(`/api/booking/context?token=${encodeURIComponent(bookingToken)}`),
      fetchJSON(`/api/booking/availability?token=${encodeURIComponent(bookingToken)}`),
    ]);
    bookingTitle.textContent = `${context.guest_name}, choose your conversation slot`;
    panelHeading.textContent = "A calm and clear booking flow for your Mirror Talk interview";
    bookingSubtitle.textContent = `${context.guest_name}, choose the best time for your Mirror Talk conversation.`;
    bookingMeta.classList.remove("hidden");
    bookingMeta.innerHTML = `
      <p><strong>Booking timezone:</strong> ${availability.booking_timezone}</p>
      <p><strong>Email:</strong> ${context.guest_email || "Not set"}</p>
      <p><strong>Booking flow:</strong> Once you reserve a slot, we will confirm everything on our side automatically.</p>
    `;
    renderExistingBooking(context.existing_booking);
    if (context.existing_booking) {
      bookingSlots.innerHTML = "";
      bookingForm.classList.add("hidden");
    } else {
      renderSlots(availability.slots || [], availability.booking_timezone || "Europe/Berlin");
    }
    if (Intl.DateTimeFormat().resolvedOptions().timeZone) {
      bookingForm.elements.timezone.value = Intl.DateTimeFormat().resolvedOptions().timeZone;
    }
    if (context.existing_booking) {
      setMessage("Your interview is already booked. If you need any change, just reply to the Mirror Talk email and we’ll help you personally.", "success");
    } else {
      setMessage("Choose one of the available interview slots below. Once you book, we’ll send your confirmation details right away.", "success");
    }
  } catch (error) {
    showInvitationState();
    setMessage(error.message, "error");
  }
}

bookingForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedSlot) {
    setMessage("Please choose one of the available interview slots first.", "error");
    return;
  }

  bookingSubmit.disabled = true;
  bookingSubmit.textContent = "Booking...";
  setMessage("Booking your Mirror Talk interview...", "pending");

  try {
    const payload = {
      token: bookingToken,
      scheduled_for: bookingForm.elements.scheduled_for.value,
      timezone: bookingForm.elements.timezone.value,
      note: bookingForm.elements.note.value,
    };
    const result = await fetchJSON("/api/booking/confirm", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderExistingBooking(result.interview);
    bookingSlots.innerHTML = "";
    bookingForm.classList.add("hidden");
    panelHeading.textContent = "Your Mirror Talk conversation is now confirmed";
    setMessage("Your Mirror Talk conversation is booked. We’ve also sent you a confirmation email with the next steps.", "success");
  } catch (error) {
    bookingSubmit.disabled = false;
    bookingSubmit.textContent = "Book This Slot";
    setMessage(error.message, "error");
  }
});

loadBookingPage().catch((error) => {
  setMessage(error.message, "error");
});
