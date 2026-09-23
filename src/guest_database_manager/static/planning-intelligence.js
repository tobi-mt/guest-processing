(function () {
  "use strict";

  const MAPPING_FIELDS = [
    ["episode_id", "Episode database ID", false, ["episode id", "episode_id"]],
    ["episode_title", "Episode title", false, ["episode title", "episode_title", "title", "content title"]],
    ["guest_name", "Guest name", false, ["guest name", "guest_name", "guest", "speaker"]],
    ["provider", "Provider", false, ["provider", "platform", "channel"]],
    ["metric_name", "Metric name", false, ["metric name", "metric_name", "metric", "measure"]],
    ["metric_value", "Metric value", false, ["metric value", "metric_value", "value", "result"]],
    ["traffic_scope", "Traffic scope", false, ["traffic scope", "traffic_scope", "scope", "traffic type"]],
    ["period_start", "Period start *", true, ["period start", "period_start", "start date", "start", "from"]],
    ["period_end", "Period end *", true, ["period end", "period_end", "end date", "end", "to", "date"]],
    ["source_reference", "Source reference", false, ["source reference", "source_reference", "source file", "reference"]],
  ];

  let selectedCsvText = "";
  let previewedObservations = [];

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function normalize(value) {
    return String(value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }

  function csrfToken() {
    const match = document.cookie.match(/(?:^|;\s*)dashboard_csrf=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  async function request(path, options = {}) {
    const headers = { Accept: "application/json", ...(options.headers || {}) };
    if (options.method && options.method !== "GET") {
      headers["Content-Type"] = "application/json";
      const token = csrfToken();
      if (token) headers["X-CSRF-Token"] = token;
    }
    const response = await fetch(path, { credentials: "same-origin", ...options, headers });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "The request could not be completed.");
    return payload;
  }

  function setMessage(node, text, tone = "") {
    if (!node) return;
    node.textContent = text;
    node.className = `message ${tone}`.trim();
  }

  function parseCsvHeader(text) {
    const headers = [];
    let current = "";
    let quoted = false;
    const firstRecord = String(text || "").replace(/^\uFEFF/, "");
    for (let index = 0; index < firstRecord.length; index += 1) {
      const character = firstRecord[index];
      if (character === '"') {
        if (quoted && firstRecord[index + 1] === '"') {
          current += '"';
          index += 1;
        } else {
          quoted = !quoted;
        }
      } else if (character === "," && !quoted) {
        headers.push(current.trim());
        current = "";
      } else if ((character === "\n" || character === "\r") && !quoted) {
        break;
      } else {
        current += character;
      }
    }
    headers.push(current.trim());
    return headers.filter(Boolean);
  }

  function renderMappingFields(headers) {
    const container = document.getElementById("analytics-mapping-fields");
    if (!container) return;
    container.replaceChildren();
    MAPPING_FIELDS.forEach(([field, label, required, aliases]) => {
      const wrapper = document.createElement("label");
      wrapper.textContent = label;
      const select = document.createElement("select");
      select.dataset.analyticsMap = field;
      select.required = Boolean(required);
      select.append(new Option(required ? "Choose column" : "Not included", ""));
      headers.forEach((header) => select.append(new Option(header, header)));
      const normalizedAliases = aliases.map(normalize);
      const suggested = headers.find((header) => normalizedAliases.includes(normalize(header)));
      if (suggested) select.value = suggested;
      wrapper.append(select);
      container.append(wrapper);
    });
  }

  function currentMapping() {
    return Object.fromEntries(
      Array.from(document.querySelectorAll("[data-analytics-map]"))
        .filter((select) => select.value)
        .map((select) => [select.dataset.analyticsMap, select.value]),
    );
  }

  function renderAnalyticsPreview(payload) {
    const container = document.getElementById("analytics-preview");
    const importButton = document.getElementById("analytics-import-button");
    if (!container || !importButton) return;
    const summary = payload.summary || {};
    const quality = payload.quality || {};
    previewedObservations = Array.isArray(payload.observations) ? payload.observations : [];
    importButton.disabled = previewedObservations.length === 0;
    const missingMfs = quality.missing_mfs_metrics || [];
    const rowMarkup = (payload.rows || []).slice(0, 100).map((row) => {
      const observation = row.observation || {};
      const notes = [...(row.errors || []), ...(row.warnings || [])].join(" ") || "Ready to import";
      return `<article class="analytics-preview-row" role="listitem">
        <div class="analytics-preview-row-heading"><strong>CSV row ${Number(row.row || 0)}</strong><span class="status-chip ${row.status === "ready" ? "ready" : row.status === "invalid" ? "warning" : "pending"}">${escapeHtml(row.status)}</span></div>
        <dl>
          <div><dt>Metric</dt><dd>${escapeHtml(observation.metric_name || "—")}</dd></div>
          <div><dt>Value</dt><dd>${escapeHtml(observation.metric_value ?? "—")}</dd></div>
          <div><dt>Episode</dt><dd>${escapeHtml(observation.episode_id || "Unlinked")}</dd></div>
        </dl>
        <p>${escapeHtml(notes)}</p>
      </article>`;
    }).join("");
    container.classList.remove("hidden");
    container.innerHTML = `
      <div class="analytics-quality-grid">
        <article><span>Ready</span><strong>${Number(summary.ready || 0)}</strong></article>
        <article><span>Invalid</span><strong>${Number(summary.invalid || 0)}</strong></article>
        <article><span>Duplicates</span><strong>${Number(summary.duplicates || 0)}</strong></article>
        <article><span>Episode linked</span><strong>${Number(summary.linked_to_episode || 0)}</strong></article>
      </div>
      <div class="operations-preview">
        <strong class="insight-label">Data-quality assessment</strong>
        <p>Period: ${escapeHtml(quality.period_start || "—")} → ${escapeHtml(quality.period_end || "—")}</p>
        <p>Providers: ${escapeHtml((quality.providers || []).join(", ") || "—")}</p>
        <p>${missingMfs.length ? `Mirror Fan Score still needs: ${escapeHtml(missingMfs.join(", "))}.` : "All Mirror Fan Score dimensions are represented in the valid rows."}</p>
        ${Number(summary.unlinked || 0) ? `<p class="field-hint">${Number(summary.unlinked)} valid row(s) are not linked to an episode. They can inform aggregate metrics but not episode-level learning.</p>` : ""}
      </div>
      <div class="analytics-preview-rows" role="list" aria-label="Analytics import row preview">${rowMarkup}</div>`;
  }

  async function loadExceptions() {
    const container = document.getElementById("exception-center");
    if (!container) return;
    try {
      const payload = await request("/api/exceptions");
      const counts = payload.counts || {};
      const items = payload.items || [];
      if (!items.length) {
        container.innerHTML = '<div class="exception-clear"><strong>No active exceptions</strong><p>Integrity, evidence, delivery, and urgent workflow checks are clear.</p></div>';
        return;
      }
      const rows = items.slice(0, 10).map((item) => `
        <article class="exception-row ${escapeHtml(item.severity)}">
          <div><span class="exception-category">${escapeHtml(item.category.replaceAll("_", " "))}</span><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.reason)}</p></div>
          <a class="ghost-button" href="${escapeHtml(item.href)}">${escapeHtml(item.action_label)}</a>
        </article>`).join("");
      container.innerHTML = `
        <div class="exception-counts" aria-label="Exception counts">
          <span><strong>${Number(counts.critical || 0)}</strong> critical</span>
          <span><strong>${Number(counts.high || 0)}</strong> high</span>
          <span><strong>${Number(counts.normal || 0)}</strong> review</span>
        </div>
        <div class="exception-list">${rows}</div>
        ${items.length > 10 ? `<p class="field-hint">Showing the 10 highest-priority exception groups.</p>` : ""}`;
    } catch (error) {
      container.innerHTML = `<p class="message error">${escapeHtml(error.message)}</p>`;
    }
  }

  function confidenceFor(item) {
    const explicit = item.ai_copilot?.confidence || item.production_readiness_forecast?.confidence;
    if (explicit) return String(explicit);
    const score = Number(item.priority_score || 0);
    const blockers = item.promotion_readiness?.blockers || [];
    if (score >= 80 && blockers.length === 0) return "high";
    if (score >= 60) return "medium";
    return "low";
  }

  function improvementFor(item) {
    const blockers = item.promotion_readiness?.blockers || [];
    if (blockers.length) return `Resolve ${blockers.slice(0, 2).join(" and ")}.`;
    if (!(item.guest_research && Object.keys(item.guest_research).length)) return "Add fresh, source-backed guest research.";
    if ((item.watchouts || []).length) return String(item.watchouts[0]);
    return "No material blocker; confirm the editorial angle and slot.";
  }

  function renderRecommendationComparison(recommendations) {
    const container = document.getElementById("recommendation-comparison-grid");
    if (!container) return;
    const items = (Array.isArray(recommendations) ? recommendations : []).slice(0, 3);
    if (!items.length) {
      container.innerHTML = "<p>No eligible recommendations are available for comparison.</p>";
      return;
    }
    container.innerHTML = `<div class="comparison-grid">${items.map((item, index) => {
      const readiness = item.promotion_readiness || {};
      const whyNow = (item.why_now || [item.recommendation_reason]).filter(Boolean)[0] || "Strongest available queue fit.";
      const freshness = item.guest_research?.freshness?.label || item.guest_research?.research_freshness || "Evidence freshness unknown";
      const blockers = readiness.blockers || [];
      const audienceBalance = item.editorial_fit?.pillar || item.editorial_pillar || item.category || "Not classified";
      return `<article class="comparison-card">
        <span class="comparison-rank">#${index + 1}</span>
        <h4>${escapeHtml(item.episode_title || item.topic || "Untitled episode")}</h4>
        <p>${escapeHtml(item.guest_name || "Guest not set")}</p>
        <dl>
          <div><dt>Score</dt><dd>${escapeHtml(item.priority_score ?? 0)}</dd></div>
          <div><dt>Confidence</dt><dd>${escapeHtml(confidenceFor(item))}</dd></div>
          <div><dt>Readiness</dt><dd>${escapeHtml(readiness.score ?? "—")}${readiness.score != null ? "/100" : ""}</dd></div>
          <div><dt>Slot</dt><dd>${escapeHtml(String(item.recommended_release_date || "Not set").slice(0, 10))}</dd></div>
          <div><dt>Audience balance</dt><dd>${escapeHtml(audienceBalance)}</dd></div>
          <div><dt>Blockers</dt><dd>${escapeHtml(blockers.length ? blockers.join(", ") : "None")}</dd></div>
        </dl>
        <div><strong>Why now</strong><p>${escapeHtml(whyNow)}</p></div>
        <div><strong>What improves it</strong><p>${escapeHtml(improvementFor(item))}</p></div>
        <small>${escapeHtml(freshness)}</small>
      </article>`;
    }).join("")}</div>`;
  }

  function renderImportHistory(payload) {
    const container = document.getElementById("analytics-import-history");
    if (!container) return;
    const items = payload.import_history || [];
    container.innerHTML = `<h3>Recent verified imports</h3>${items.length ? `<div class="import-history-list">${items.map((item) => `
      <article><div><strong>${escapeHtml(item.source_reference || item.provider || "Verified import")}</strong><p>${escapeHtml(item.provider || "provider not set")} · ${escapeHtml(item.period_start || "—")} → ${escapeHtml(item.period_end || "—")}</p></div><span>${Number(item.observation_count || 0)} metrics · ${Number(item.episode_count || 0)} episodes</span></article>`).join("")}</div>` : "<p>No analytics have been imported yet.</p>"}`;
  }

  async function loadImportHistory() {
    const payload = await request("/api/growth-intelligence");
    renderImportHistory(payload);
  }

  function renderOutcomeReviews(payload) {
    const container = document.getElementById("outcome-review-queue");
    if (!container) return;
    const items = payload.pending_outcome_reviews || [];
    if (!items.length) {
      container.innerHTML = "<p class=\"field-hint\">No released recommendation outcomes are waiting for editorial review.</p>";
      return;
    }
    container.innerHTML = `<h3>Did the release meet expectations?</h3>${items.slice(0, 5).map((item) => `
      <article class="outcome-review-row"><div><strong>${escapeHtml(item.episode_title)}</strong><p>${escapeHtml(item.guest_name || "Guest not set")} · ${escapeHtml(item.release_date || "Release date unavailable")}</p></div><div class="outcome-review-actions" data-episode-id="${Number(item.episode_id)}"><button type="button" class="ghost-button" data-outcome="positive">Yes</button><button type="button" class="ghost-button" data-outcome="neutral">Partly</button><button type="button" class="ghost-button" data-outcome="negative">No</button></div></article>`).join("")}`;
  }

  async function loadOutcomeReviews() {
    const payload = await request("/api/recommendation-learning");
    renderOutcomeReviews(payload);
  }

  function initializeAnalyticsImport() {
    const form = document.getElementById("analytics-import-form");
    const fileInput = document.getElementById("analytics-file");
    const sourceInput = form?.elements.source_reference;
    const previewContainer = document.getElementById("analytics-preview");
    const importButton = document.getElementById("analytics-import-button");
    const message = document.getElementById("analytics-import-message");
    if (!form || !fileInput || !importButton) return;

    fileInput.addEventListener("change", async () => {
      previewedObservations = [];
      importButton.disabled = true;
      previewContainer?.classList.add("hidden");
      const file = fileInput.files?.[0];
      if (!file) return;
      selectedCsvText = await file.text();
      if (sourceInput && !sourceInput.value.trim()) sourceInput.value = file.name;
      renderMappingFields(parseCsvHeader(selectedCsvText));
      setMessage(message, "Review the suggested column mapping, then preview data quality.", "pending");
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!selectedCsvText) {
        setMessage(message, "Choose a CSV file first.", "error");
        return;
      }
      const button = document.getElementById("analytics-preview-button");
      button.disabled = true;
      setMessage(message, "Validating rows without changing the database…", "pending");
      try {
        const payload = await request("/api/growth-intelligence/preview", {
          method: "POST",
          body: JSON.stringify({
            csv_text: selectedCsvText,
            provider: form.elements.provider.value,
            source_reference: form.elements.source_reference.value,
            mapping: currentMapping(),
          }),
        });
        renderAnalyticsPreview(payload);
        setMessage(message, `${payload.summary.ready} row(s) are ready. Review the assessment before importing.`, payload.summary.invalid ? "pending" : "success");
      } catch (error) {
        setMessage(message, error.message, "error");
      } finally {
        button.disabled = false;
      }
    });

    importButton.addEventListener("click", async () => {
      if (!previewedObservations.length) return;
      importButton.disabled = true;
      setMessage(message, "Importing only the validated, non-duplicate rows…", "pending");
      try {
        const result = await request("/api/growth-intelligence/observations", {
          method: "POST",
          body: JSON.stringify({
            observations: previewedObservations,
            correlation_id: window.crypto?.randomUUID?.() || `analytics-${Date.now()}`,
          }),
        });
        setMessage(message, `Imported ${result.inserted}; skipped ${result.duplicates} duplicate(s). ${result.learning_outcomes || 0} released outcome(s) linked to recommendation learning.`, "success");
        previewedObservations = [];
        window.dispatchEvent(new CustomEvent("growth-intelligence-changed"));
        await loadExceptions();
        await loadImportHistory();
      } catch (error) {
        setMessage(message, error.message, "error");
        importButton.disabled = false;
      }
    });
  }

  function init() {
    initializeAnalyticsImport();
    document.getElementById("exception-center-refresh")?.addEventListener("click", loadExceptions);
    loadExceptions();
    loadImportHistory().catch(() => {});
    loadOutcomeReviews().catch(() => {});
    document.getElementById("outcome-review-queue")?.addEventListener("click", async (event) => {
      const button = event.target.closest("[data-outcome]");
      if (!button) return;
      const group = button.closest("[data-episode-id]");
      button.disabled = true;
      try {
        await request("/api/recommendation-learning/outcomes", {
          method: "POST",
          body: JSON.stringify({
            episode_id: Number(group.dataset.episodeId), outcome_type: button.dataset.outcome,
            source: "editor_review", idempotency_key: `editor-review:${group.dataset.episodeId}`,
          }),
        });
        await loadOutcomeReviews();
      } catch (error) {
        button.disabled = false;
        button.title = error.message;
      }
    });
  }

  window.PlanningIntelligence = {
    init,
    loadExceptions,
    renderRecommendationComparison,
    renderImportHistory,
    renderOutcomeReviews,
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
