const bookingMessage = document.getElementById("booking-message");
const bookingSubtitle = document.getElementById("booking-subtitle");
const bookingExisting = document.getElementById("booking-existing");
const bookingMeta = document.getElementById("booking-meta");
const bookingForm = document.getElementById("booking-form");
const bookingSubmit = document.getElementById("booking-submit");
const bookingTitle = document.getElementById("booking-title");
const panelHeading = document.getElementById("panel-heading");
const bookingInvitation = document.getElementById("booking-invitation");
const bookingAvailability = document.getElementById("booking-availability");
const bookingSelectedSlot = document.getElementById("booking-selected-slot");
const bookingCalendarGrid = document.getElementById("booking-calendar-grid");
const bookingTimes = document.getElementById("booking-times");
const bookingMonthLabel = document.getElementById("booking-month-label");
const bookingMonthPrev = document.getElementById("booking-month-prev");
const bookingMonthNext = document.getElementById("booking-month-next");

let bookingToken = "";
let selectedSlot = null;
let selectedDateKey = "";
let visibleMonthKey = "";
let availableSlots = [];
let availableMonths = [];
let slotTimezone = "Europe/Berlin";
let rescheduleMode = false;

function setMessage(text, tone = "") {
  bookingMessage.textContent = text;
  bookingMessage.className = `message ${tone}`.trim();
}

function showInvitationState() {
  bookingInvitation.classList.remove("hidden");
  bookingMeta.classList.add("hidden");
  bookingExisting.classList.add("hidden");
  bookingAvailability.classList.add("hidden");
  bookingSelectedSlot.classList.add("hidden");
  bookingCalendarGrid.innerHTML = "";
  bookingTimes.innerHTML = "";
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
    timeZone: slotTimezone,
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatSlotDay(dateText) {
  const date = new Date(dateText);
  return date.toLocaleDateString(undefined, {
    timeZone: slotTimezone,
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function formatSlotTime(dateText) {
  const date = new Date(dateText);
  return date.toLocaleTimeString(undefined, {
    timeZone: slotTimezone,
    hour: "2-digit",
    minute: "2-digit",
  });
}

function slotLocalDate(slot) {
  const date = new Date(slot.start);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: slotTimezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const year = parts.find((part) => part.type === "year")?.value || "0000";
  const month = parts.find((part) => part.type === "month")?.value || "01";
  const day = parts.find((part) => part.type === "day")?.value || "01";
  return `${year}-${month}-${day}`;
}

function slotMonthKey(slot) {
  return slotLocalDate(slot).slice(0, 7);
}

function monthStartFromKey(monthKey) {
  const [year, month] = monthKey.split("-").map(Number);
  return new Date(year, month - 1, 1);
}

function monthLabel(monthKey) {
  return monthStartFromKey(monthKey).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}

function slotsForDate(dateKey) {
  return availableSlots.filter((slot) => slotLocalDate(slot) === dateKey);
}

function renderExistingBooking(existing) {
  if (!existing) {
    bookingExisting.classList.add("hidden");
    bookingExisting.innerHTML = "";
    return;
  }
  bookingExisting.classList.remove("hidden");
  bookingExisting.innerHTML = `
    <strong>${rescheduleMode ? "Current booking" : "You already have a booking"}</strong>
    <p>${formatSlot(existing.scheduled_for)}${existing.timezone ? ` · ${existing.timezone}` : ""}</p>
    ${existing.join_url ? `<p>Your recording link: <a href="${existing.join_url}" target="_blank" rel="noopener">${existing.join_url}</a></p>` : ""}
    <p>${rescheduleMode ? "Choose a new date below to reschedule this conversation." : "If you need to reschedule, please reply to the email you received from Mirror Talk and we’ll support you directly."}</p>
  `;
}

function renderSelectedSlot(slot) {
  if (!slot) {
    bookingSelectedSlot.classList.add("hidden");
    bookingSelectedSlot.innerHTML = "";
    return;
  }
  bookingSelectedSlot.classList.remove("hidden");
  bookingSelectedSlot.innerHTML = `
    <strong>Selected slot</strong>
    <p>${formatSlot(slot.start)}</p>
    <span>${slotTimezone}</span>
  `;
}

function renderTimeOptions(dateKey) {
  bookingTimes.innerHTML = "";
  const daySlots = slotsForDate(dateKey);
  if (!daySlots.length) {
    bookingTimes.innerHTML = "";
    bookingForm.classList.add("hidden");
    bookingSubmit.disabled = true;
    renderSelectedSlot(null);
    return;
  }

  const intro = document.createElement("div");
  intro.className = "time-grid-intro";
  intro.innerHTML = `
    <strong>Available times for ${formatSlotDay(daySlots[0].start)}</strong>
    <p>Select the time that works best for you.</p>
  `;
  bookingTimes.appendChild(intro);

  daySlots.forEach((slot) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "time-slot-button";
    button.textContent = `${formatSlotTime(slot.start)} · ${slotTimezone}`;
    if (selectedSlot && selectedSlot.start === slot.start) {
      button.classList.add("active");
    }
    button.addEventListener("click", () => {
      selectedSlot = slot;
      bookingForm.elements.scheduled_for.value = slot.start;
      bookingSubmit.disabled = false;
      bookingSubmit.textContent = rescheduleMode ? "Confirm New Slot" : "Book This Slot";
      renderSelectedSlot(slot);
      bookingTimes.querySelectorAll(".time-slot-button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
    });
    bookingTimes.appendChild(button);
  });

  bookingForm.classList.remove("hidden");
}

function renderCalendarMonth() {
  bookingCalendarGrid.innerHTML = "";
  if (!visibleMonthKey) {
    bookingMonthLabel.textContent = "Available dates";
    bookingMonthPrev.disabled = true;
    bookingMonthNext.disabled = true;
    return;
  }

  bookingMonthLabel.textContent = monthLabel(visibleMonthKey);
  const visibleMonthIndex = availableMonths.indexOf(visibleMonthKey);
  bookingMonthPrev.disabled = visibleMonthIndex <= 0;
  bookingMonthNext.disabled = visibleMonthIndex === -1 || visibleMonthIndex >= availableMonths.length - 1;

  const monthDate = monthStartFromKey(visibleMonthKey);
  const year = monthDate.getFullYear();
  const month = monthDate.getMonth();
  const firstWeekday = (new Date(year, month, 1).getDay() + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const availableDateKeys = new Set(availableSlots.filter((slot) => slotMonthKey(slot) === visibleMonthKey).map(slotLocalDate));

  for (let index = 0; index < firstWeekday; index += 1) {
    const filler = document.createElement("div");
    filler.className = "calendar-day empty";
    bookingCalendarGrid.appendChild(filler);
  }

  for (let day = 1; day <= daysInMonth; day += 1) {
    const dateKey = `${visibleMonthKey}-${String(day).padStart(2, "0")}`;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "calendar-day";
    button.textContent = String(day);
    const isAvailable = availableDateKeys.has(dateKey);
    if (!isAvailable) {
      button.disabled = true;
      button.classList.add("disabled");
    } else {
      button.classList.add("available");
      if (selectedDateKey === dateKey) {
        button.classList.add("active");
      }
      button.addEventListener("click", () => {
        selectedDateKey = dateKey;
        selectedSlot = null;
        bookingSubmit.disabled = true;
        renderSelectedSlot(null);
        renderCalendarMonth();
        renderTimeOptions(dateKey);
      });
    }
    bookingCalendarGrid.appendChild(button);
  }
}

function setAvailableSlots(slots, timezone, bookingWindow = {}) {
  availableSlots = Array.isArray(slots) ? [...slots].sort((left, right) => new Date(left.start) - new Date(right.start)) : [];
  slotTimezone = timezone || "Europe/Berlin";
  availableMonths = [...new Set(availableSlots.map(slotMonthKey))];
  visibleMonthKey = availableMonths[0] || "";
  selectedDateKey = "";
  selectedSlot = null;
  bookingSubmit.disabled = true;
  bookingSubmit.textContent = rescheduleMode ? "Confirm New Slot" : "Book This Slot";
  renderSelectedSlot(null);

  bookingAvailability.classList.remove("hidden");
  if (!availableSlots.length) {
    bookingCalendarGrid.innerHTML = `
      <div class="empty-slot-state">
        <strong>No booking slots are available right now.</strong>
        <p>Please reply to the Mirror Talk email and we’ll help you find a suitable time personally.</p>
      </div>
    `;
    bookingTimes.innerHTML = "";
    bookingForm.classList.add("hidden");
    bookingMonthLabel.textContent = "Available dates";
    bookingMonthPrev.disabled = true;
    bookingMonthNext.disabled = true;
    return;
  }

  renderCalendarMonth();
  const firstAvailableDate = slotLocalDate(availableSlots[0]);
  selectedDateKey = firstAvailableDate;
  visibleMonthKey = slotMonthKey(availableSlots[0]);
  renderCalendarMonth();
  renderTimeOptions(firstAvailableDate);
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
    rescheduleMode = Boolean(context.reschedule_mode);
    bookingTitle.textContent = `${context.guest_name}, choose your conversation slot`;
    panelHeading.textContent = rescheduleMode ? "Choose a new time for your Soulful Conversation" : "A calm and clear booking flow for your Mirror Talk interview";
    bookingSubtitle.textContent = rescheduleMode
      ? `${context.guest_name}, choose the new time that works best for your Soulful Conversation.`
      : `${context.guest_name}, choose the best time for your Soulful Conversation.`;
    bookingMeta.classList.remove("hidden");
    bookingMeta.innerHTML = `
      <p><strong>Booking timezone:</strong> ${availability.booking_timezone}</p>
      <p><strong>Email:</strong> ${context.guest_email || "Not set"}</p>
      <p><strong>Booking flow:</strong> ${rescheduleMode ? "Once you choose a new slot, we will update your interview and send a fresh confirmation automatically." : "Once you reserve a slot, we will confirm everything on our side automatically."}</p>
    `;
    renderExistingBooking(context.existing_booking);
    if (context.existing_booking && !rescheduleMode) {
      bookingAvailability.classList.add("hidden");
      bookingCalendarGrid.innerHTML = "";
      bookingTimes.innerHTML = "";
      bookingForm.classList.add("hidden");
    } else {
      setAvailableSlots(availability.slots || [], availability.booking_timezone || "Europe/Berlin", availability.booking_window || {});
    }
    if (Intl.DateTimeFormat().resolvedOptions().timeZone) {
      bookingForm.elements.timezone.value = Intl.DateTimeFormat().resolvedOptions().timeZone;
    }
    if (context.existing_booking && !rescheduleMode) {
      setMessage("Your interview is already booked. If you need any change, just reply to the Mirror Talk email and we’ll help you personally.", "success");
    } else if (rescheduleMode) {
      setMessage("Choose a new date in the calendar, then select a time to reschedule your conversation.", "success");
    } else {
      setMessage("Choose a date in the calendar, then select a time and confirm your booking below.", "success");
    }
  } catch (error) {
    showInvitationState();
    setMessage(error.message, "error");
  }
}

bookingMonthPrev.addEventListener("click", () => {
  const currentIndex = availableMonths.indexOf(visibleMonthKey);
  if (currentIndex > 0) {
    visibleMonthKey = availableMonths[currentIndex - 1];
    renderCalendarMonth();
  }
});

bookingMonthNext.addEventListener("click", () => {
  const currentIndex = availableMonths.indexOf(visibleMonthKey);
  if (currentIndex !== -1 && currentIndex < availableMonths.length - 1) {
    visibleMonthKey = availableMonths[currentIndex + 1];
    renderCalendarMonth();
  }
});

async function submitBooking() {
  if (!selectedSlot) {
    setMessage("Please choose a date and time first.", "error");
    return;
  }

  bookingSubmit.disabled = true;
  bookingSubmit.textContent = "Booking...";
  setMessage(rescheduleMode ? "Rescheduling your Mirror Talk interview..." : "Booking your Mirror Talk interview...", "pending");

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
    selectedSlot = null;
    selectedDateKey = "";
    bookingSubmit.disabled = true;
    bookingSubmit.textContent = rescheduleMode ? "Rescheduled" : "Booked";
    renderExistingBooking(result.interview);
    bookingAvailability.classList.add("hidden");
    bookingCalendarGrid.innerHTML = "";
    bookingTimes.innerHTML = "";
    bookingForm.classList.add("hidden");
    bookingSelectedSlot.classList.add("hidden");
    bookingSelectedSlot.innerHTML = "";
    panelHeading.textContent = rescheduleMode ? "Your Soulful Conversation is now rescheduled" : "Your Soulful Conversation is now confirmed";
    setMessage(
      rescheduleMode
        ? "Your Soulful Conversation has been rescheduled. We’ve also sent you a fresh confirmation email with the updated invite."
        : "Your Soulful Conversation is booked. We’ve also sent you a confirmation email with the next steps.",
      "success"
    );
  } catch (error) {
    bookingSubmit.disabled = false;
    bookingSubmit.textContent = rescheduleMode ? "Confirm New Slot" : "Book This Slot";
    setMessage(error.message, "error");
  }
}

bookingForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await submitBooking();
});

bookingSubmit.addEventListener("click", async () => {
  await submitBooking();
});

loadBookingPage().catch((error) => {
  setMessage(error.message, "error");
});
