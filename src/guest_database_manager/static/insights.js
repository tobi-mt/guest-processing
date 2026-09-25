const escapeHtml = window.PerformanceUtils?.escapeHtml || ((value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[character]));
const number = (value) => value == null ? "Unavailable" : new Intl.NumberFormat().format(Number(value));
const safeUrl = (value) => { try { const parsed = new URL(String(value)); return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "#"; } catch { return "#"; } };
const empty = (message) => `<div class="insights-empty"><strong>Not measured yet</strong><p>${escapeHtml(message)}</p><a href="/planning?tab=scheduling_intelligence#analytics-import">Import verified analytics</a></div>`;
const csrfToken = () => decodeURIComponent((document.cookie.match(/(?:^|;\s*)dashboard_csrf=([^;]+)/) || [])[1] || "");

async function connectorRequest(path, options = {}) {
  const headers = {Accept:"application/json", ...(options.headers || {})};
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = csrfToken();
  const response = await fetch(path, {credentials:"same-origin", ...options, headers});
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "The analytics connection request failed.");
  return payload;
}

function renderConnections(connectors) {
  const target = document.getElementById("analytics-connections");
  const google = connectors.google || {}; const connection = google.connection || {};
  const status = connection.status || (google.oauth_configured ? "not connected" : "configuration required");
  const details = connection.account_email ? `Authorized as ${connection.account_email}` : google.oauth_configured ? "Ready for one-time Google authorization." : "Production OAuth credentials and an encryption key must be configured first.";
  target.innerHTML = `<article class="connection-card"><header><div><strong>Google Analytics</strong><p>YouTube Analytics${google.ga4_configured ? " and GA4" : " · GA4 property not configured"}</p></div><span class="connection-status ${escapeHtml(connection.status || "")}">${escapeHtml(status)}</span></header><p>${escapeHtml(details)}</p><small>Last successful sync: ${escapeHtml(connection.last_success_at || "never")} · Failures: ${Number(connection.consecutive_failures || 0)}${connection.next_retry_at ? ` · Retry ${escapeHtml(connection.next_retry_at)}` : ""}</small><div class="connection-actions"><button id="connect-google" class="primary-button" type="button" ${google.oauth_configured ? "" : "disabled"}>${connection.status === "connected" ? "Reconnect Google" : "Connect Google"}</button><button id="sync-google" class="secondary-button" type="button" ${connection.status === "connected" ? "" : "disabled"}>Sync now</button><button id="disconnect-google" class="ghost-button" type="button" ${["connected", "error", "revoked"].includes(connection.status) ? "" : "disabled"}>Disconnect</button></div></article><article class="connection-card"><header><strong>Provider limitations</strong><span class="connection-status">Verified</span></header>${(connectors.unsupported || []).map((item) => `<p><strong>${escapeHtml(item.provider.replaceAll("_", " "))}</strong><br><small>${escapeHtml(item.reason)}</small></p>`).join("")}</article>`;
  document.getElementById("connect-google")?.addEventListener("click", async () => { try { const result = await connectorRequest("/api/analytics-connectors/google/connect", {method:"POST"}); window.location.assign(result.authorization_url); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } });
  document.getElementById("sync-google")?.addEventListener("click", async () => { try { await connectorRequest("/api/analytics-connectors/google/sync", {method:"POST"}); await load(); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } });
  document.getElementById("disconnect-google")?.addEventListener("click", async () => { if (!window.confirm("Disconnect Google analytics and delete the retained refresh token?")) return; try { await connectorRequest("/api/analytics-connectors/google", {method:"DELETE"}); await load(); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } });
}

function renderBars(items, target) {
  if (!items.length) { target.innerHTML = empty("Import a provider export with dimensional metrics to populate this view."); return; }
  const max = Math.max(...items.map((item) => Number(item.value || 0)), 1);
  target.innerHTML = `<div class="insight-bars">${items.map((item) => `<div class="insight-bar"><div><strong>${escapeHtml(item.name)}</strong><span>${number(item.value)}${item.share_pct == null ? "" : ` · ${item.share_pct}%`}</span></div><div class="insight-bar-track"><span style="width:${Math.max(2, Number(item.value || 0) * 100 / max)}%"></span></div><small>${escapeHtml(item.provider || "")} · through ${escapeHtml(item.period_end || "unknown")}</small></div>`).join("")}</div>`;
}

function render(payload) {
  const summary = payload.summary || {}; const quality = payload.quality || {};
  const catalog = payload.public_catalog || {};
  document.getElementById("insights-quality").innerHTML = `<div><span class="coverage-pill ${quality.status}">${escapeHtml(quality.status || "unknown")} coverage</span><strong>${number(quality.observation_count)} verified observations</strong><p>Latest evidence: ${escapeHtml(quality.latest_period_end || "none imported")} · ${number(quality.stale_provider_count)} stale providers</p></div><div><strong>Missing core evidence</strong><p>${(quality.missing_core_metrics || []).map(escapeHtml).join(", ") || "None"}</p></div>`;
  document.getElementById("insights-summary").innerHTML = [
    ["Published episodes", number(catalog.published_episodes), `RSS catalog: ${number(catalog.rss_items)} items`],
    ["Latest public release", catalog.latest_release ? new Date(catalog.latest_release).toLocaleDateString() : "Unavailable", `${number(catalog.public_sources_available)} of ${number(catalog.public_sources_expected)} public sources healthy`],
    ["Verified platforms", number(summary.verified_platforms), `${number(summary.platforms_with_private_analytics)} with private analytics`],
    ["Cross-platform listeners", number(summary.unique_listeners), summary.unique_listener_explanation],
    ["Downloads", number(summary.downloads), summary.latest_period_end ? `Compatible period ending ${summary.latest_period_end}` : "No compatible period imported"],
    ["Plays / streams", number(summary.plays), "Kept separate from downloads in source data"],
  ].map(([label,value,detail]) => `<article class="summary-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`).join("");
  const coverage = payload.source_coverage || {}; const publicSources = coverage.public || []; const privateSources = coverage.private || [];
  renderConnections(payload.analytics_connectors || {});
  document.getElementById("source-coverage").innerHTML = `<div class="source-column"><h3>Public monitoring <span>${Number(coverage.public_available || 0)}/${Number(coverage.public_expected || 0)}</span></h3>${publicSources.length ? publicSources.map((source) => `<article class="source-row"><div><strong>${escapeHtml(source.source_name)}</strong><span class="source-status ${escapeHtml(source.status)}">${escapeHtml(source.status)}</span></div><small>Checked ${escapeHtml(source.checked_at || "not yet")} · ${number(source.latency_ms)} ms</small></article>`).join("") : empty("The daily public-source monitor has not completed its first run.")}</div><div class="source-column"><h3>Private analytics <span>${Number(coverage.private_connected || 0)}/${Number(coverage.private_expected || 0)}</span></h3>${privateSources.map((source) => `<article class="source-row"><div><strong>${escapeHtml(source.name)}</strong><span class="source-status ${escapeHtml(source.status)}">${escapeHtml(source.status.replaceAll("_", " "))}</span></div><small>${escapeHtml(source.metrics.join(", "))}</small><p>${escapeHtml(source.access)}</p></article>`).join("")}</div>`;
  document.getElementById("platform-grid").innerHTML = (payload.platforms || []).map((platform) => `<a class="platform-card" href="${escapeHtml(safeUrl(platform.url))}" target="_blank" rel="noopener noreferrer"><span>${escapeHtml(platform.kind)}</span><strong>${escapeHtml(platform.name)}</strong><small>Verified ${escapeHtml(platform.verified_on)} · ${escapeHtml(platform.source)}</small></a>`).join("");
  const providers = payload.provider_strength || [];
  document.getElementById("provider-strength").innerHTML = providers.length ? providers.map((item) => `<article class="provider-row"><div><strong>${escapeHtml(item.provider)}</strong><span class="freshness ${escapeHtml(item.freshness)}">${escapeHtml(item.freshness)}</span></div><p>${Object.entries(item.metrics || {}).map(([key,value]) => `${escapeHtml(key.replaceAll("_", " "))}: <strong>${number(value)}</strong>`).join(" · ")}</p><small>${escapeHtml(item.period_start)} – ${escapeHtml(item.period_end)} · ${item.sources.length} source${item.sources.length === 1 ? "" : "s"}</small></article>`).join("") : empty("No private platform exports have been imported.");
  const audience = payload.audience_by_platform || [];
  document.getElementById("audience-platform").innerHTML = audience.length ? audience.map((item) => `<article class="provider-row"><div><strong>${escapeHtml(item.provider)}</strong><span>${number(item.value)}</span></div><p>${escapeHtml(item.metric.replaceAll("_", " "))}</p><small>Through ${escapeHtml(item.period_end)}</small></article>`).join("") : empty("Import unique listeners, followers, or subscriber counts from each platform. These will remain separate to prevent double-counting.");
  renderBars(payload.devices || [], document.getElementById("device-breakdown"));
  renderBars(payload.countries || [], document.getElementById("country-breakdown"));
  const trend = payload.trend || [];
  document.getElementById("reach-trend").innerHTML = trend.length ? `<div class="trend-table" role="table"><div class="trend-row trend-head" role="row"><span>Period</span><span>Downloads</span><span>Plays</span></div>${trend.map((item) => `<div class="trend-row" role="row"><span>${escapeHtml(item.period_end)}</span><strong>${number(item.downloads)}</strong><strong>${number(item.plays)}</strong></div>`).join("")}</div>` : empty("Import at least two reporting periods to establish a trend.");
  document.getElementById("metric-definitions").innerHTML = Object.entries(payload.definitions || {}).map(([key,value]) => `<article><strong>${escapeHtml(key.replaceAll("_", " "))}</strong><p>${escapeHtml(value)}</p></article>`).join("") + `<article><strong>Reliability guardrails</strong><p>${(quality.limitations || []).map(escapeHtml).join(" ")}</p></article>`;
}

async function load() {
  const response = await fetch("/api/podcast-insights", {headers:{Accept:"application/json"}});
  if (!response.ok) throw new Error("Podcast insights could not be loaded");
  render(await response.json());
}
document.getElementById("insights-refresh")?.addEventListener("click", () => load().catch((error) => { document.getElementById("insights-quality").textContent = error.message; }));
load().catch((error) => { document.getElementById("insights-quality").textContent = error.message; });
