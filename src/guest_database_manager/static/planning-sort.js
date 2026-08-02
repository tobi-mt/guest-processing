(function exposePlanningSort(root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.PlanningSort = api;
}(typeof window !== "undefined" ? window : globalThis, () => {
  function normalize(value) {
    return String(value || "").trim().toLowerCase();
  }

  function timestamp(value) {
    if (!value) return null;
    const parsed = new Date(value).getTime();
    return Number.isFinite(parsed) ? parsed : null;
  }

  function episodeNumber(value) {
    const matches = String(value || "").match(/\d+/g);
    return matches?.length ? Number.parseInt(matches[matches.length - 1], 10) : null;
  }

  function compareNullable(left, right, direction = 1) {
    if (left === null && right === null) return 0;
    if (left === null) return 1;
    if (right === null) return -1;
    return (left - right) * direction;
  }

  function compareEpisodes(left, right, mode = "release_asc") {
    const stableTieBreak = () => Number(left.id || 0) - Number(right.id || 0);
    let result = 0;
    if (mode === "guest_name" || mode === "category") {
      const field = mode === "guest_name" ? "guest_name" : "category";
      result = normalize(left[field]).localeCompare(normalize(right[field]));
    } else if (mode === "priority") {
      result = Number(right.priority_score || 0) - Number(left.priority_score || 0);
    } else if (mode === "latest_interview") {
      result = compareNullable(timestamp(left.interview_date), timestamp(right.interview_date), -1);
    } else if (mode === "updated_desc") {
      result = compareNullable(timestamp(left.updated_at), timestamp(right.updated_at), -1);
    } else if (mode === "episode_number_asc" || mode === "episode_number_desc") {
      result = compareNullable(
        episodeNumber(left.legacy_episode_number),
        episodeNumber(right.legacy_episode_number),
        mode === "episode_number_desc" ? -1 : 1,
      );
    } else {
      if (mode === "status_release") {
        const rank = { scheduled: 0, released: 1, unplanned: 2 };
        result = (rank[normalize(left.release_status)] ?? 3) - (rank[normalize(right.release_status)] ?? 3);
      }
      if (!result) {
        result = compareNullable(
          timestamp(left.release_date),
          timestamp(right.release_date),
          mode === "release_desc" ? -1 : 1,
        );
      }
    }
    return result || stableTieBreak();
  }

  return { compareEpisodes, episodeNumber };
}));
