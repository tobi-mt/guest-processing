const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const script = fs.readFileSync(
  path.join(__dirname, "../src/guest_database_manager/static/insights.js"),
  "utf8",
);
const start = script.indexOf("function renderEpisodePerformance(");
const end = script.indexOf("\nfunction renderPodcastAdvisory(", start);
assert.notEqual(start, -1);
assert.notEqual(end, -1);

test("episode performance keeps same-titled records and unlinked platform content separate", () => {
  const target = {innerHTML: ""};
  const context = vm.createContext({
    document: {getElementById: () => target},
    episodes: [
      {episode_id: 10, title: "Shared title", activity: 100, metrics: {}, providers: ["spotify"], period_end: "2026-11-27"},
      {episode_id: 11, title: "Shared title", activity: 200, metrics: {}, providers: ["spotify"], period_end: "2026-11-27"},
    ],
    platformItems: [{
      provider: "spotify",
      platform_content_id: "title:shared title",
      title: "Shared title",
      period_start: "2020-06-12",
      period_end: "2026-11-27",
      freshness: "stale",
      metrics: {plays_downloads: 50},
    }],
    escapeHtml: (value) => String(value ?? "").replace(/[&<>"']/g, (character) => (
      {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[character]
    )),
    number: (value) => String(value ?? "—"),
    percentage: (value) => String(value ?? "—"),
    duration: (value) => String(value ?? "—"),
    freshnessLabel: (value) => ({current: "Current", aging: "Aging", stale: "Refresh needed"}[value] || "Unknown"),
    empty: (message) => message,
    providerLabel: (provider) => provider,
  });

  vm.runInContext(
    `${script.slice(start, end)}\nrenderEpisodePerformance(episodes, platformItems);`,
    context,
  );

  assert.equal((target.innerHTML.match(/<tr>/g) || []).length - 1, 3);
  assert.match(target.innerHTML, /spotify · Episode record 10/);
  assert.match(target.innerHTML, /spotify · Episode record 11/);
  assert.match(target.innerHTML, /period starts 2020-06-12/);
  assert.match(target.innerHTML, /class="freshness stale">Refresh needed<\/span>/);
  assert.match(target.innerHTML, /<strong>100<\/strong>/);
  assert.match(target.innerHTML, /<strong>200<\/strong>/);
  assert.match(target.innerHTML, /<strong>50<\/strong>/);
});

test("public ratings render escaped storefronts, totals and unrated audience markets", () => {
  const ratingsStart = script.indexOf("function renderPublicRatings(");
  const ratingsEnd = script.indexOf("\nfunction renderEpisodePerformance(", ratingsStart);
  assert.notEqual(ratingsStart, -1);
  const target = {innerHTML: ""};
  const context = vm.createContext({
    document: {getElementById: () => target},
    escapeHtml: (value) => String(value ?? "").replace(/[&<>"']/g, (character) => (
      {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[character]
    )),
    number: (value) => value == null ? "—" : String(value),
    percentage: (value) => value == null ? "—" : String(value),
    formatDate: (value) => String(value ?? "—"),
    empty: (message) => `EMPTY:${message}`,
    ratings: {
      total_ratings: 74, weighted_average: 4.9, new_ratings_30d: 3, period_end: "2026-11-28", freshness: "current",
      unrated_audience_markets: ["France", "<Mars>"], definition: "Public Apple ratings.",
      storefronts: [
        {name: "United States", average: 4.9, count: 65, change_30d: 3},
        {name: "<b>Nigeria</b>", average: 5, count: 1, change_30d: 0},
      ],
    },
  });

  vm.runInContext(`${script.slice(ratingsStart, ratingsEnd)}\nrenderPublicRatings(ratings, {status: "connected"});`, context);

  assert.match(target.innerHTML, /Ratings<strong>74<\/strong>/);
  assert.match(target.innerHTML, /65 ratings<\/span>.*Apple storefront · \+3 in 30 days/);
  assert.match(target.innerHTML, /1 rating<\/span>/);
  assert.match(target.innerHTML, /&lt;b&gt;Nigeria/);
  assert.match(target.innerHTML, /France, &lt;Mars&gt;/);
  assert.doesNotMatch(target.innerHTML, /<b>|<Mars>/);

  vm.runInContext("renderPublicRatings(null, {status: 'error'});", context);
  assert.match(target.innerHTML, /^EMPTY:The last automatic Apple ratings check could not be read/);
});
