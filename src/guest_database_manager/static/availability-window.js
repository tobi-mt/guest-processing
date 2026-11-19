(function availabilityWindowModule(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.AvailabilityWindow = api;
}(typeof globalThis !== "undefined" ? globalThis : this, () => {
  function startOfLocalDay(value) {
    const date = new Date(value);
    date.setHours(0, 0, 0, 0);
    return date;
  }

  function bookingWindow(reference, minNoticeHours, daysAhead) {
    const noticeDate = new Date(new Date(reference).getTime() + (Number(minNoticeHours) * 60 * 60 * 1000));
    const start = startOfLocalDay(noticeDate);
    const end = new Date(start);
    end.setDate(end.getDate() + Number(daysAhead));
    return { start, end };
  }

  function positionInBookingWindow(date, window) {
    const day = startOfLocalDay(date);
    if (day < window.start) return "before";
    if (day > window.end) return "after";
    return "inside";
  }

  return { bookingWindow, positionInBookingWindow };
}));
