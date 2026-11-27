(function () {
  "use strict";

  const thresholds = [25, 50, 75];
  const tracked = new WeakSet();

  function episodeReference(audio) {
    return String(
      audio.dataset.episodeId ||
      audio.closest("[data-episode-id]")?.dataset.episodeId ||
      window.location.pathname
    ).slice(0, 160);
  }

  function report(audio, eventName, extra = {}) {
    if (typeof window.gtag !== "function") return;
    window.gtag("event", eventName, {
      episode_reference: episodeReference(audio),
      player_location: window.location.pathname,
      transport_type: "beacon",
      ...extra,
    });
  }

  function instrument(audio) {
    if (!(audio instanceof HTMLAudioElement) || tracked.has(audio)) return;
    tracked.add(audio);
    const reached = new Set();
    audio.addEventListener("play", () => report(audio, "audio_play"), {passive: true});
    audio.addEventListener("pause", () => {
      if (!audio.ended && audio.currentTime > 0) report(audio, "audio_pause");
    }, {passive: true});
    audio.addEventListener("timeupdate", () => {
      if (!Number.isFinite(audio.duration) || audio.duration <= 0) return;
      const progress = audio.currentTime * 100 / audio.duration;
      thresholds.forEach((threshold) => {
        if (progress >= threshold && !reached.has(threshold)) {
          reached.add(threshold);
          report(audio, `audio_progress_${threshold}`, {progress_percent: threshold});
        }
      });
    }, {passive: true});
    audio.addEventListener("ended", () => report(audio, "audio_complete", {progress_percent: 100}), {passive: true});
  }

  function discover(root = document) {
    root.querySelectorAll("audio").forEach(instrument);
  }

  discover();
  new MutationObserver((mutations) => mutations.forEach((mutation) => mutation.addedNodes.forEach((node) => {
    if (!(node instanceof Element)) return;
    if (node.matches("audio")) instrument(node);
    discover(node);
  }))).observe(document.documentElement, {childList: true, subtree: true});
})();
