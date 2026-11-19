const test = require('node:test');
const assert = require('node:assert/strict');

const { bookingWindow, positionInBookingWindow } = require('../src/guest_database_manager/static/availability-window.js');

test('booking window begins on the minimum-notice day and ends after configured days', () => {
  const window = bookingWindow('2026-11-19T10:00:00Z', 24, 45);

  assert.equal(positionInBookingWindow('2026-11-19T12:00:00Z', window), 'before');
  assert.equal(positionInBookingWindow('2026-11-20T12:00:00Z', window), 'inside');
  assert.equal(positionInBookingWindow('2027-01-04T12:00:00Z', window), 'inside');
  assert.equal(positionInBookingWindow('2027-01-05T12:00:00Z', window), 'after');
});

test('dates beyond a short configured horizon are never treated as open', () => {
  const window = bookingWindow('2026-11-19T10:00:00Z', 2, 7);

  assert.equal(positionInBookingWindow('2026-11-26T12:00:00Z', window), 'inside');
  assert.equal(positionInBookingWindow('2026-11-27T12:00:00Z', window), 'after');
});
