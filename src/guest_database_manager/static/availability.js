const form = document.querySelector("#availability-form");
const days = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"];
let availability = { blackouts: [] };
let events = [];
let month = new Date();
month.setDate(1);

const csrf = () => document.cookie.split(";").map((item) => item.trim()).find((item) => item.startsWith("dashboard_csrf="))?.split("=")[1] || "";
const iso = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function isoWeekNumber(date) {
  const utcDate = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const weekday = utcDate.getUTCDay() || 7;
  utcDate.setUTCDate(utcDate.getUTCDate() + 4 - weekday);
  const yearStart = new Date(Date.UTC(utcDate.getUTCFullYear(), 0, 1));
  return Math.ceil((((utcDate - yearStart) / 86400000) + 1) / 7);
}

function addTime(value = "") {
  const row = document.createElement("div");
  row.className = "time-row";
  row.innerHTML = `<input type="time" value="${escapeHtml(value)}" required><button type="button" class="secondary-button" aria-label="Remove time">×</button>`;
  row.querySelector("button").onclick = () => { row.remove(); render(); };
  document.querySelector("#times").append(row);
}

function eventDates(event) {
  const start = event.start?.slice(0, 10);
  const end = event.end?.slice(0, 10) || start;
  if (!start) return [];
  const endAt = event.end || event.start;
  const endIsMidnight = /T00:00(?::00)?(?:[Z+\-]|$)/.test(endAt || "");
  let finalDate = end;
  if (event.all_day || endIsMidnight) {
    const date = new Date(`${end}T12:00`);
    date.setDate(date.getDate() - 1);
    finalDate = iso(date);
  }
  if (start === end && !event.all_day) finalDate = start;
  const dates = [];
  for (let date = new Date(`${start}T12:00`); iso(date) <= finalDate; date.setDate(date.getDate() + 1)) dates.push(iso(date));
  return dates;
}

async function refresh() {
  const response = await fetch(`/api/availability/calendar?year=${month.getFullYear()}&month=${month.getMonth() + 1}`, { credentials: "same-origin" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Could not read calendar");
  events = data.events || [];
  document.querySelector("#message").textContent = data.status?.connected ? "Live Google calendar (read-only)." : data.status?.message || "";
  render();
}

function dayEvents(date) { return events.filter((event) => eventDates(event).includes(date)); }

function render() {
  const year = month.getFullYear();
  const monthIndex = month.getMonth();
  const firstOfMonth = new Date(year, monthIndex, 1);
  const mondayOffset = (firstOfMonth.getDay() + 6) % 7;
  const start = new Date(year, monthIndex, 1 - mondayOffset);
  const selected = [...document.querySelectorAll("#weekdays input:checked")].map((input) => input.value);
  const slotCount = [...document.querySelectorAll(".time-row input")].filter((input) => input.value).length;
  const codes = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"];
  const todayKey = iso(new Date());
  let open = 0;
  let booked = 0;
  let away = 0;
  let fullyBookedThrough = null;

  document.querySelector("#calendar-title").textContent = month.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  const headers = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((label) => `<div class="calendar-weekday" role="columnheader">${label}</div>`).join("");
  const rows = [...Array(6)].map((_, weekIndex) => {
    const weekStart = new Date(start);
    weekStart.setDate(start.getDate() + (weekIndex * 7));
    const daysMarkup = [...Array(7)].map((__, dayIndex) => {
      const date = new Date(weekStart);
      date.setDate(weekStart.getDate() + dayIndex);
      const key = iso(date);
      const inside = date.getMonth() === monthIndex;
      const items = dayEvents(key);
      const manualAway = availability.blackouts.includes(key);
      const googleAway = items.some((item) => item.all_day && /podcast break|vacation|away|holiday/i.test(item.title || ""));
      const busy = items.length > 0;
      const eligible = inside && selected.includes(codes[date.getDay()]);
      const capacity = eligible ? slotCount : 0;
      const available = capacity && !busy && !manualAway && !googleAway ? capacity : 0;
      const status = !inside ? "outside this month" : manualAway || googleAway ? "Away" : busy ? `${items.length} calendar item${items.length > 1 ? "s" : ""}` : available ? `${available} open slot${available > 1 ? "s" : ""}` : "Closed";
      if (inside) {
        open += available;
        booked += items.length;
        away += Number(manualAway || googleAway);
        if (eligible && available === 0 && !fullyBookedThrough) fullyBookedThrough = key;
      }
      const fullDate = date.toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "long", day: "numeric" });
      return `<button type="button" class="calendar-day ${!inside ? "outside " : ""}${manualAway || googleAway ? "blackout" : busy ? "booked" : available ? "open" : ""}${key === todayKey ? " today" : ""}" data-date="${key}" aria-label="${escapeHtml(`${fullDate}: ${status}`)}" ${key === todayKey ? 'aria-current="date"' : ""} ${inside ? "" : 'tabindex="-1"'}><strong>${date.getDate()}</strong><small>${inside ? escapeHtml(status) : ""}</small></button>`;
    }).join("");
    const weekNumber = isoWeekNumber(weekStart);
    return `<div class="calendar-week-number" role="rowheader" aria-label="ISO week ${weekNumber}">W${weekNumber}</div>${daysMarkup}`;
  }).join("");

  document.querySelector("#availability-calendar").innerHTML = `<div class="calendar-week-number-heading" role="columnheader" aria-label="ISO week number">Week</div>${headers}${rows}`;
  document.querySelector("#open-count").firstChild.textContent = open;
  document.querySelector("#booked-count").firstChild.textContent = booked;
  document.querySelector("#away-count").firstChild.textContent = away;
  document.querySelector("#booked-through").firstChild.textContent = fullyBookedThrough ? new Date(`${fullyBookedThrough}T12:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "Not full";
  document.querySelectorAll(".calendar-day[data-date]").forEach((button) => { button.onclick = () => showDay(button.dataset.date); });
  document.querySelector("#blackout-list").innerHTML = availability.blackouts.map((date) => `<button type="button" data-date="${escapeHtml(date)}">${escapeHtml(date)} ×</button>`).join("");
  document.querySelectorAll("#blackout-list button").forEach((button) => { button.onclick = () => { availability.blackouts = availability.blackouts.filter((date) => date !== button.dataset.date); render(); }; });
}

function showDay(date) {
  const items = dayEvents(date);
  const blocked = availability.blackouts.includes(date);
  const detail = items.length ? items.map((item) => `<li><strong>${escapeHtml(item.title)}</strong> · ${item.source === "google" ? "Google Calendar" : "Mirror Talk"}${item.all_day ? " · all day" : ""}</li>`).join("") : "<li>No booked calendar entries.</li>";
  let dialog = document.querySelector("#calendar-day-dialog");
  if (!dialog) { dialog = document.createElement("dialog"); dialog.id = "calendar-day-dialog"; document.body.append(dialog); }
  const fullDate = new Date(`${date}T12:00`).toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "long", day: "numeric" });
  dialog.innerHTML = `<form method="dialog"><h2>${escapeHtml(fullDate)}</h2><p>${blocked ? "Manually blocked as vacation/blackout." : "Read-only calendar preview."}</p><ul>${detail}</ul><button class="primary-button">Close</button></form>`;
  dialog.showModal();
}

async function load() {
  availability = await fetch("/api/availability", { credentials: "same-origin" }).then((response) => response.json());
  document.querySelector("#weekdays").innerHTML = days.map((day) => `<label><input type="checkbox" value="${day}" ${availability.weekdays.includes(day) ? "checked" : ""}> ${day}</label>`).join("");
  form.timezone.value = availability.timezone;
  form.days_ahead.value = availability.days_ahead;
  form.min_notice_hours.value = availability.min_notice_hours;
  availability.slot_times.forEach(addTime);
  await refresh();
}

for (const [id, delta] of [["calendar-prev", -1], ["calendar-next", 1]]) document.querySelector(`#${id}`).onclick = async () => { month.setMonth(month.getMonth() + delta); await refresh(); };
document.querySelector("#calendar-today").onclick = async () => { month = new Date(); month.setDate(1); await refresh(); };
document.querySelector("#add-time").onclick = () => { addTime(); render(); };
form.addEventListener("input", render);
document.querySelector("#blackout-form").onsubmit = (event) => { event.preventDefault(); const date = document.querySelector("#blackout-date").value; if (date && !availability.blackouts.includes(date)) availability.blackouts.push(date); render(); };
form.onsubmit = async (event) => {
  event.preventDefault();
  const payload = { timezone: form.timezone.value, weekdays: [...document.querySelectorAll("#weekdays input:checked")].map((input) => input.value), slot_times: [...document.querySelectorAll(".time-row input")].map((input) => input.value), days_ahead: form.days_ahead.value, min_notice_hours: form.min_notice_hours.value, blackouts: availability.blackouts };
  const response = await fetch("/api/availability", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": decodeURIComponent(csrf()) }, body: JSON.stringify(payload) });
  const data = await response.json();
  document.querySelector("#message").textContent = response.ok ? "Availability saved." : data.error;
  if (response.ok) { availability = data; render(); }
};
load().catch((error) => { document.querySelector("#message").textContent = error.message; });
