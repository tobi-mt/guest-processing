(function () {
  "use strict";

  const STORAGE = {
    density: "mirror-talk-density",
    details: "mirror-talk-details-state",
    recent: "mirror-talk-recent-records",
  };
  const escapeHtml = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const readJson = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };

  async function getJson(url) {
    const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "Request failed");
    return payload;
  }

  function saveRecent(item) {
    const current = readJson(STORAGE.recent, []).filter((entry) => entry.key !== item.key);
    localStorage.setItem(STORAGE.recent, JSON.stringify([{ key: item.key, title: item.title, href: item.href, kind: item.kind }, ...current].slice(0, 8)));
  }

  function renderSearchResults(container, payload) {
    const items = payload.results || [];
    if (!items.length) {
      container.innerHTML = `<p class="command-empty">${payload.query?.length < 2 ? "Type at least two characters." : "No matching records or actions."}</p>`;
      return;
    }
    container.innerHTML = items.map((item) => `<article class="command-result"><span class="command-kind">${escapeHtml(item.kind)}</span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.subtitle || item.snippet || "")}</small><span class="command-actions"><a href="${escapeHtml(item.href)}" data-result-key="${escapeHtml(item.key)}" data-result-title="${escapeHtml(item.title)}" data-result-kind="${escapeHtml(item.kind)}">${escapeHtml(item.command || "Open")}</a>${item.secondary_command ? `<a href="${escapeHtml(item.secondary_href || item.href)}" data-result-key="${escapeHtml(item.key)}" data-result-title="${escapeHtml(item.title)}" data-result-kind="${escapeHtml(item.kind)}">${escapeHtml(item.secondary_command)}</a>` : ""}</span></article>`).join("");
  }

  function renderBriefing(container, payload) {
    const counts = payload.counts || {};
    const actions = [...(payload.overdue || []), ...(payload.upcoming || [])].slice(0, 8);
    container.innerHTML = `<div class="briefing-counts"><span><strong>${Number(counts.assigned || 0)}</strong> assigned</span><span><strong>${Number(counts.overdue || 0)}</strong> overdue</span><span><strong>${Number(counts.upcoming || 0)}</strong> due soon</span><span><strong>${Number(counts.actionable_exceptions || 0)}</strong> exceptions</span></div>${actions.length ? actions.map((item) => `<a class="command-result" href="${escapeHtml(item.href || "/dashboard")}"><strong>${escapeHtml(item.next_action || item.title)}</strong><small>${escapeHtml(item.title || item.reason || "")}</small></a>`).join("") : "<p class=\"command-empty\">Nothing assigned to you in this window.</p>"}<p class="field-hint">Quiet digest: notifications are only warranted when an actionable exception exists.</p>`;
  }

  function buildShell() {
    const density = localStorage.getItem(STORAGE.density) || "comfortable";
    document.documentElement.dataset.density = density;
    document.body.insertAdjacentHTML("beforeend", `
      <div class="workspace-utility-bar" aria-label="Workspace tools">
        <button type="button" data-open-command>Search <kbd>⌘K</kbd></button>
        <button type="button" data-open-briefing>My work</button>
        <button type="button" data-toggle-density>${density === "compact" ? "Comfortable" : "Compact"}</button>
      </div>
      <nav class="mobile-workspace-nav" aria-label="Workspace navigation"><a href="/dashboard">Guests</a><a href="/operations">Interviews</a><a href="/planning">Episodes</a><button type="button" data-open-command>Search</button></nav>
      <dialog id="workspace-command-dialog" class="workspace-dialog"><form method="dialog"><button class="dialog-close" aria-label="Close">×</button></form><p class="eyebrow">Global command menu</p><h2>Find anything</h2><label class="command-search-label">Search guests, interviews, episodes, transcripts, and actions<input id="workspace-command-input" type="search" autocomplete="off" placeholder="Search or type a command…" /></label><div id="workspace-command-results" class="command-results" aria-live="polite"></div><div id="workspace-recent-results" class="recent-results"></div></dialog>
      <dialog id="workspace-briefing-dialog" class="workspace-dialog"><form method="dialog"><button class="dialog-close" aria-label="Close">×</button></form><p class="eyebrow">Personal operating view</p><h2>My work</h2><div class="briefing-switch"><button type="button" data-briefing-window="daily">Today</button><button type="button" data-briefing-window="weekly">This week</button></div><div id="workspace-briefing-results" aria-live="polite"><p>Loading…</p></div></dialog>`);
  }

  function initializeDetailsPersistence() {
    const state = readJson(STORAGE.details, {});
    document.querySelectorAll("details").forEach((details, index) => {
      const key = details.id || `${location.pathname}:${index}:${details.querySelector("summary")?.textContent.trim().slice(0, 40) || "section"}`;
      if (Object.hasOwn(state, key)) details.open = Boolean(state[key]);
      details.addEventListener("toggle", () => {
        const next = readJson(STORAGE.details, {});
        next[key] = details.open;
        localStorage.setItem(STORAGE.details, JSON.stringify(next));
      });
    });
  }

  function initializeUnsavedWarnings() {
    const forms = Array.from(document.querySelectorAll("form")).filter((form) => !form.closest("dialog") && !form.matches("[method='get']"));
    const dirty = new WeakSet();
    forms.forEach((form) => {
      form.addEventListener("input", (event) => { if (event.isTrusted) dirty.add(form); });
      form.addEventListener("change", (event) => { if (event.isTrusted) dirty.add(form); });
      form.addEventListener("submit", () => dirty.delete(form));
      form.addEventListener("reset", () => dirty.delete(form));
      form.addEventListener("workspace-form-saved", () => dirty.delete(form));
    });
    window.addEventListener("beforeunload", (event) => {
      if (forms.some((form) => dirty.has(form))) { event.preventDefault(); event.returnValue = ""; }
    });
  }

  function init() {
    buildShell();
    initializeDetailsPersistence();
    initializeUnsavedWarnings();
    const command = document.getElementById("workspace-command-dialog");
    const input = document.getElementById("workspace-command-input");
    const results = document.getElementById("workspace-command-results");
    const recent = document.getElementById("workspace-recent-results");
    const briefing = document.getElementById("workspace-briefing-dialog");
    const briefingResults = document.getElementById("workspace-briefing-results");
    let timer;
    const openCommand = () => {
      const recentItems = readJson(STORAGE.recent, []);
      recent.innerHTML = recentItems.length ? `<h3>Recently viewed</h3>${recentItems.map((item) => `<a href="${escapeHtml(item.href)}">${escapeHtml(item.title)}</a>`).join("")}` : "";
      command.showModal(); input.focus();
    };
    document.querySelectorAll("[data-open-command]").forEach((button) => button.addEventListener("click", openCommand));
    document.addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openCommand(); }
      if (event.key === "/" && !/input|textarea|select/i.test(document.activeElement?.tagName || "")) { event.preventDefault(); openCommand(); }
    });
    input.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        try { renderSearchResults(results, await getJson(`/api/search?q=${encodeURIComponent(input.value)}`)); }
        catch (error) { results.innerHTML = `<p class="message error">${escapeHtml(error.message)}</p>`; }
      }, 180);
    });
    results.addEventListener("click", (event) => {
      const link = event.target.closest("[data-result-key]");
      if (link) saveRecent({ key: link.dataset.resultKey, title: link.dataset.resultTitle, kind: link.dataset.resultKind, href: link.href });
    });
    async function loadBriefing(windowName) {
      briefingResults.innerHTML = "<p>Loading actionable work…</p>";
      try { renderBriefing(briefingResults, await getJson(`/api/personal-briefing?window=${windowName}`)); }
      catch (error) { briefingResults.innerHTML = `<p class="message error">${escapeHtml(error.message)}</p>`; }
    }
    document.querySelectorAll("[data-open-briefing]").forEach((button) => button.addEventListener("click", () => { briefing.showModal(); loadBriefing("daily"); }));
    document.querySelectorAll("[data-briefing-window]").forEach((button) => button.addEventListener("click", () => loadBriefing(button.dataset.briefingWindow)));
    document.querySelector("[data-toggle-density]")?.addEventListener("click", (event) => {
      const next = document.documentElement.dataset.density === "compact" ? "comfortable" : "compact";
      document.documentElement.dataset.density = next; localStorage.setItem(STORAGE.density, next);
      event.currentTarget.textContent = next === "compact" ? "Comfortable" : "Compact";
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true }); else init();
})();
