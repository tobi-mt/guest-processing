const bookingMessage = document.getElementById("booking-message");
const bookingSubtitle = document.getElementById("booking-subtitle");
const bookingExisting = document.getElementById("booking-existing");
const bookingMeta = document.getElementById("booking-meta");
const bookingProposal = document.getElementById("booking-proposal");
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
let conflictSlots = [];
let availableMonths = [];
let slotTimezone = "Europe/Berlin";
let rescheduleMode = false;
let conflictBufferMinutes = 30;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setMessage(text, tone = "") {
  bookingMessage.textContent = text;
  bookingMessage.className = `message ${tone}`.trim();
}

function showInvitationState() {
  bookingInvitation.classList.remove("hidden");
  bookingMeta.classList.add("hidden");
  bookingExisting.classList.add("hidden");
  bookingProposal.classList.add("hidden");
  bookingAvailability.classList.add("hidden");
  bookingSelectedSlot.classList.add("hidden");
  bookingCalendarGrid.innerHTML = "";
  bookingTimes.innerHTML = "";
  bookingForm.classList.add("hidden");
  bookingTitle.textContent = "Your Mirror Talk invitation link opens here";
  panelHeading.textContent = "A personal booking link keeps the experience secure and connected";
}

async function fetchJSON(url, options = {}) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 20000);
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    signal: controller.signal,
    ...options,
  });
  try {
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
      throw new Error(data.error || "Request failed");
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("This request took too long. Please refresh and try again.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function formatSlot(dateText, timezoneName = slotTimezone) {
  const date = new Date(dateText);
  return date.toLocaleString(undefined, {
    timeZone: timezoneName,
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

function conflictsForDate(dateKey) {
  return conflictSlots.filter((slot) => slotLocalDate(slot) === dateKey);
}

function renderExistingBooking(existing) {
  if (!existing) {
    bookingExisting.classList.add("hidden");
    bookingExisting.innerHTML = "";
    return;
  }
  bookingExisting.classList.remove("hidden");
  const guestTimezone = existing.guest_timezone || existing.timezone || slotTimezone;
  const guestTimezoneNote = guestTimezone !== slotTimezone
    ? `<p>${escapeHtml(formatSlot(existing.scheduled_for, guestTimezone))} · ${escapeHtml(guestTimezone)} <span class="muted">(your local time)</span></p>`
    : `<p class="muted">This time is shown in ${escapeHtml(guestTimezone)}, your timezone captured at booking.</p>`;
  bookingExisting.innerHTML = `
    <strong>${rescheduleMode ? "Current booking" : "You already have a booking"}</strong>
    <p>${escapeHtml(formatSlot(existing.scheduled_for, existing.timezone || slotTimezone))} · ${escapeHtml(existing.timezone || slotTimezone)} <span class="muted">(calendar timezone)</span></p>
    ${guestTimezoneNote}
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

function selectSlot(slot) {
  selectedSlot = slot;
  selectedDateKey = slotLocalDate(slot);
  visibleMonthKey = slotMonthKey(slot);
  bookingForm.elements.scheduled_for.value = slot.start;
  bookingSubmit.disabled = false;
  bookingSubmit.textContent = rescheduleMode ? "Confirm New Slot" : "Book This Slot";
  renderSelectedSlot(slot);
  renderCalendarMonth();
  renderTimeOptions(selectedDateKey);
  bookingSubmit.focus({ preventScroll: true });
  bookingForm.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderRescheduleProposal(proposal) {
  bookingProposal.innerHTML = "";
  if (!proposal || proposal.mode === "open_calendar" || !Array.isArray(proposal.options) || !proposal.options.length) {
    bookingProposal.classList.add("hidden");
    return;
  }
  bookingProposal.classList.remove("hidden");
  const heading = document.createElement("h3");
  heading.id = "booking-proposal-heading";
  heading.textContent = proposal.mode === "specific" ? "Your proposed new time" : "Choose from these proposed times";
  const intro = document.createElement("p");
  intro.textContent = proposal.mode === "specific"
    ? "Mirror Talk has suggested this time for your conversation. Confirm it below if it still works for you."
    : "Mirror Talk has suggested these alternatives. Choose the one that works best for you.";
  const options = document.createElement("div");
  options.className = "proposal-options";
  proposal.options.forEach((option) => {
    const row = document.createElement("div");
    row.className = `proposal-option${option.available ? "" : " unavailable"}`;
    const label = document.createElement("strong");
    label.textContent = `${formatSlot(option.start)} · ${proposal.timezone || slotTimezone}`;
    row.appendChild(label);
    if (option.available) {
      const slot = availableSlots.find((item) => new Date(item.start).getTime() === new Date(option.start).getTime());
      const button = document.createElement("button");
      button.type = "button";
      button.className = "primary-button";
      button.textContent = proposal.mode === "specific" ? "Select this time" : "Choose this time";
      button.addEventListener("click", () => {
        if (slot) selectSlot(slot);
        bookingForm.scrollIntoView({ behavior: "smooth", block: "center" });
      });
      row.appendChild(button);
    } else {
      const unavailable = document.createElement("span");
      unavailable.textContent = "No longer available";
      row.appendChild(unavailable);
    }
    options.appendChild(row);
  });
  const another = document.createElement("p");
  another.textContent = "Prefer another time? You can still use the full availability calendar below.";
  bookingProposal.append(heading, intro, options, another);
}

function renderTimeOptions(dateKey) {
  bookingTimes.innerHTML = "";
  const daySlots = slotsForDate(dateKey);
  const dayConflicts = conflictsForDate(dateKey);
  if (!daySlots.length && !dayConflicts.length) {
    bookingTimes.innerHTML = "";
    bookingForm.classList.add("hidden");
    bookingSubmit.disabled = true;
    renderSelectedSlot(null);
    return;
  }

  const intro = document.createElement("div");
  intro.className = "time-grid-intro";
  const referenceSlot = daySlots[0] || dayConflicts[0];
  intro.innerHTML = `
    <strong>Times for ${formatSlotDay(referenceSlot.start)}</strong>
    <p>${daySlots.length ? "Choose a time below to continue." : "There are no bookable times on this date. Please choose another date."}</p>
  `;
  bookingTimes.appendChild(intro);

  if (dayConflicts.length) {
    const notice = document.createElement("p");
    notice.className = "date-availability-notice";
    notice.textContent = daySlots.length
      ? "Some times on this date are unavailable."
      : "This date is unavailable.";
    bookingTimes.appendChild(notice);
  }

  daySlots.forEach((slot) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "time-slot-button";
    const slotTime = formatSlotTime(slot.start);
    button.textContent = `Select ${slotTime} · ${slotTimezone}`;
    button.setAttribute("aria-pressed", "false");
    if (selectedSlot && selectedSlot.start === slot.start) {
      button.classList.add("active");
      button.textContent = `Selected: ${slotTime} · ${slotTimezone}`;
      button.setAttribute("aria-pressed", "true");
    }
    button.addEventListener("click", () => {
      selectSlot(slot);
    });
    bookingTimes.appendChild(button);
  });

  dayConflicts.forEach((slot) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "time-slot-button conflict";
    button.disabled = true;
    button.textContent = `${formatSlotTime(slot.start)} · Unavailable`;
    bookingTimes.appendChild(button);
  });

  bookingForm.classList.toggle("hidden", !daySlots.length);
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
  const conflictDateKeys = new Set(conflictSlots.filter((slot) => slotMonthKey(slot) === visibleMonthKey).map(slotLocalDate));

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
    const hasConflict = conflictDateKeys.has(dateKey);
    if (!isAvailable && !hasConflict) {
      button.disabled = true;
      button.classList.add("disabled");
    } else {
      button.classList.add(isAvailable ? "available" : "conflict");
      if (hasConflict) button.setAttribute("aria-label", `${day}, calendar conflict`);
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
        if (!isAvailable) {
          setMessage("That date has no bookable times. Please choose one of the available dates.", "error");
        } else {
          setMessage("Now choose a time below to activate the booking button.", "success");
          window.requestAnimationFrame(() => {
            const firstTime = bookingTimes.querySelector(".time-slot-button:not(:disabled)");
            firstTime?.focus({ preventScroll: true });
            bookingTimes.scrollIntoView({ behavior: "smooth", block: "nearest" });
          });
        }
      });
    }
    bookingCalendarGrid.appendChild(button);
  }
}

function setAvailableSlots(slots, conflicts, timezone, bookingWindow = {}, bufferMinutes = 30) {
  availableSlots = Array.isArray(slots) ? [...slots].sort((left, right) => new Date(left.start) - new Date(right.start)) : [];
  conflictSlots = Array.isArray(conflicts) ? [...conflicts].sort((left, right) => new Date(left.start) - new Date(right.start)) : [];
  slotTimezone = timezone || "Europe/Berlin";
  conflictBufferMinutes = Number(bufferMinutes) || 0;
  availableMonths = [...new Set([...availableSlots, ...conflictSlots].map(slotMonthKey))].sort();
  visibleMonthKey = availableMonths[0] || "";
  selectedDateKey = "";
  selectedSlot = null;
  bookingSubmit.disabled = true;
  bookingSubmit.textContent = rescheduleMode ? "Confirm New Slot" : "Book This Slot";
  renderSelectedSlot(null);

  bookingAvailability.classList.remove("hidden");
  if (!availableSlots.length && !conflictSlots.length) {
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

  visibleMonthKey = slotMonthKey(availableSlots[0] || conflictSlots[0]);
  renderCalendarMonth();
  bookingTimes.innerHTML = "";
  bookingForm.classList.add("hidden");
}

async function loadBookingPage() {
  const params = new URLSearchParams(window.location.search);
  bookingToken = params.get("token") || "";
  if (!bookingToken) {
    showInvitationState();
    setMessage("This page is opened through a personal Mirror Talk invitation link. Please use the booking link sent to your email, or reply to Mirror Talk and we’ll send you a fresh one.", "success");
    document.body.classList.remove("booking-loading");
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
    slotTimezone = availability.booking_timezone || "Europe/Berlin";
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
      setAvailableSlots(
        availability.slots || [],
        availability.conflicts || [],
        availability.booking_timezone || "Europe/Berlin",
        availability.booking_window || {},
        availability.conflict_buffer_minutes ?? 30,
      );
      renderRescheduleProposal(availability.reschedule_proposal || context.reschedule_proposal);
    }
    if (Intl.DateTimeFormat().resolvedOptions().timeZone) {
      bookingForm.elements.timezone.value = Intl.DateTimeFormat().resolvedOptions().timeZone;
    }
    if (context.existing_booking && !rescheduleMode) {
      setMessage("Your interview is already booked. If you need any change, just reply to the Mirror Talk email and we’ll help you personally.", "success");
    } else if (rescheduleMode) {
      setMessage(context.reschedule_proposal?.mode && context.reschedule_proposal.mode !== "open_calendar"
        ? "Review the proposed time below, or choose another available slot from the calendar."
        : "Choose a new date in the calendar, then select a time to reschedule your conversation.", "success");
    } else {
      setMessage("Choose a date in the calendar, then select a time and confirm your booking below.", "success");
    }
  } catch (error) {
    showInvitationState();
    setMessage(error.message, "error");
  } finally {
    document.body.classList.remove("booking-loading");
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
    const delivery = result.interview?.booking_confirmation || {};
    const deliveryMessage = delivery.message || (
      delivery.status === "sent"
        ? "Your confirmation email and calendar invite have been accepted for delivery."
        : "Your booking is confirmed. We are preparing your confirmation email and calendar invite now."
    );
    setMessage(
      rescheduleMode
        ? `Your Soulful Conversation has been rescheduled. ${deliveryMessage}`
        : `Your Soulful Conversation is booked. ${deliveryMessage}`,
      delivery.status === "unavailable" ? "error" : "success"
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
