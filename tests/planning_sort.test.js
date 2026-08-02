const test = require("node:test");
const assert = require("node:assert/strict");
const { compareEpisodes } = require("../src/guest_database_manager/static/planning-sort.js");

const rows = [
  { id: 3, release_date: null, release_status: "unplanned", legacy_episode_number: "TBD" },
  { id: 2, release_date: "2026-08-12T17:00:00", release_status: "scheduled", legacy_episode_number: "502" },
  { id: 1, release_date: "2026-08-01T17:00:00", release_status: "released", legacy_episode_number: "501" },
  { id: 4, release_date: "2026-08-05T17:00:00", release_status: "scheduled", legacy_episode_number: "503" },
];

function orderedIds(mode) {
  return [...rows].sort((left, right) => compareEpisodes(left, right, mode)).map((row) => row.id);
}

test("release dates sort in both directions and undated rows stay last", () => {
  assert.deepEqual(orderedIds("release_asc"), [1, 4, 2, 3]);
  assert.deepEqual(orderedIds("release_desc"), [2, 4, 1, 3]);
});

test("episode numbers sort numerically instead of lexicographically", () => {
  assert.deepEqual(orderedIds("episode_number_asc"), [1, 2, 4, 3]);
  assert.deepEqual(orderedIds("episode_number_desc"), [4, 2, 1, 3]);
});

test("status grouping keeps scheduled before released with release-date ordering", () => {
  assert.deepEqual(orderedIds("status_release"), [4, 2, 1, 3]);
});

test("equal values have a deterministic id tie-break", () => {
  const equal = [{ id: 9, release_date: "2026-08-05" }, { id: 7, release_date: "2026-08-05" }];
  assert.deepEqual(equal.sort((left, right) => compareEpisodes(left, right, "release_asc")).map((row) => row.id), [7, 9]);
});
