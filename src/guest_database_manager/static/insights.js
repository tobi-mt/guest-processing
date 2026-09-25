const escapeHtml = window.PerformanceUtils?.escapeHtml || ((value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[character]));
const number = (value) => value == null ? "Unavailable" : new Intl.NumberFormat().format(Number(value));
const safeUrl = (value) => { try { const parsed = new URL(String(value)); return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "#"; } catch { return "#"; } };
const empty = (message) => `<div class="insights-empty"><strong>Not measured yet</strong><p>${escapeHtml(message)}</p><a href="/planning?tab=scheduling_intelligence#analytics-import">Import verified analytics</a></div>`;
const csrfToken = () => decodeURIComponent((document.cookie.match(/(?:^|;\s*)dashboard_csrf=([^;]+)/) || [])[1] || "");
const metricLabel = (value) => String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
const duration = (seconds) => seconds == null ? "Unavailable" : `${Math.floor(Number(seconds) / 60)}m ${Math.round(Number(seconds) % 60)}s`;

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
  target.innerHTML = `<article class="connection-card"><header><div><strong>Google data connection</strong><p>YouTube Analytics${google.ga4_configured ? " + GA4 website analytics" : " · GA4 property not configured"}</p></div><span class="connection-status ${escapeHtml(connection.status || "")}">${escapeHtml(status)}</span></header><p>${escapeHtml(details)}</p><small>Last successful sync: ${escapeHtml(connection.last_success_at || "never")} · ${Number(connection.consecutive_failures || 0)} consecutive failures${connection.next_retry_at ? ` · Retry ${escapeHtml(connection.next_retry_at)}` : ""}</small><div class="connection-actions"><button id="connect-google" class="primary-button" type="button" ${google.oauth_configured ? "" : "disabled"}>${connection.status === "connected" ? "Reconnect" : "Connect Google"}</button><button id="sync-google" class="secondary-button" type="button" ${connection.status === "connected" ? "" : "disabled"}>Sync now</button><button id="disconnect-google" class="ghost-button" type="button" ${["connected", "error", "revoked"].includes(connection.status) ? "" : "disabled"}>Disconnect</button></div></article>`;
  document.getElementById("connect-google")?.addEventListener("click", async () => { try { const result = await connectorRequest("/api/analytics-connectors/google/connect", {method:"POST"}); window.location.assign(result.authorization_url); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } });
  document.getElementById("sync-google")?.addEventListener("click", async () => { try { await connectorRequest("/api/analytics-connectors/google/sync", {method:"POST"}); await load(); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } });
  document.getElementById("disconnect-google")?.addEventListener("click", async () => { if (!window.confirm("Disconnect Google analytics and delete the retained refresh token?")) return; try { await connectorRequest("/api/analytics-connectors/google", {method:"DELETE"}); await load(); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } });
}

function renderBars(items, target) {
  if (!items.length) { target.innerHTML = empty("Import a provider export with dimensional metrics to populate this view."); return; }
  const providers = [...new Set(items.map((item) => item.provider || "source"))];
  target.innerHTML = providers.map((provider) => {
    const group = items.filter((item) => (item.provider || "source") === provider);
    const max = Math.max(...group.map((item) => Number(item.value || 0)), 1);
    return `<div class="insight-bars"><h3>${escapeHtml(metricLabel(provider))}</h3>${group.map((item) => `<div class="insight-bar"><div><strong>${escapeHtml(item.name)}</strong><span>${number(item.value)}${item.share_pct == null ? "" : ` · ${item.share_pct}%`}</span></div><div class="insight-bar-track"><span style="width:${Math.max(2, Number(item.value || 0) * 100 / max)}%"></span></div><small>Through ${escapeHtml(item.period_end || "unknown")}</small></div>`).join("")}</div>`;
  }).join("");
}

function render(payload) {
  const summary = payload.summary || {}; const quality = payload.quality || {};
  const catalog = payload.public_catalog || {};
  const providers = payload.provider_strength || [];
  const youtube = providers.find((item) => item.provider === "youtube") || {metrics:{}};
  const website = providers.find((item) => item.provider === "website") || {metrics:{}};
  const connection = payload.analytics_connectors?.google?.connection || {};
  document.getElementById("insights-quality").innerHTML = `<div><span class="coverage-pill ${quality.status}">${escapeHtml(quality.status || "unknown")} evidence</span><strong>${number(quality.observation_count)} verified observations</strong><p>Latest measured period: ${escapeHtml(quality.latest_period_end || "none")}</p></div><div><strong>Automated collection</strong><p>${connection.status === "connected" ? `Healthy · last sync ${escapeHtml(connection.last_success_at || "pending")}` : "Connection needs attention"}</p></div><div><strong>Still unmeasured</strong><p>${(quality.missing_core_metrics || []).map(metricLabel).join(", ") || "None"}</p></div>`;
  document.getElementById("insights-summary").innerHTML = [
    ["Published episodes", number(catalog.published_episodes), `RSS catalog: ${number(catalog.rss_items)} items`],
    ["YouTube plays", number(summary.plays), summary.plays_period_end ? `28-day window ending ${summary.plays_period_end}` : "Not measured"],
    ["YouTube watch time", youtube.metrics.watch_time_hours == null ? "Unavailable" : `${Number(youtube.metrics.watch_time_hours).toFixed(1)}h`, `Average view ${duration(youtube.metrics.average_view_duration_seconds)}`],
    ["YouTube subscribers", number(youtube.metrics.subscribers), `Snapshot through ${escapeHtml(youtube.period_end || "unknown")}`],
    ["Website active users", number(website.metrics.organic_reach), website.metrics.organic_reach == null ? "GA4 evidence unavailable" : `28-day GA4 window ending ${escapeHtml(website.period_end || "unknown")}`],
    ["Verified platforms", number(summary.verified_platforms), `${number(catalog.public_sources_available)} of ${number(catalog.public_sources_expected)} public checks healthy`],
  ].map(([label,value,detail]) => `<article class="summary-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`).join("");
  const youtubeMobile = (payload.devices || []).find((item) => item.provider === "youtube" && item.name === "Mobile");
  const websiteCountries = (payload.countries || []).filter((item) => item.provider === "website");
  const topCountry = [...websiteCountries].sort((left, right) => Number(right.value) - Number(left.value))[0];
  document.getElementById("reach-highlights").innerHTML = [
    ["YouTube viewing", youtubeMobile ? `${youtubeMobile.share_pct}% mobile` : "Device mix pending", youtubeMobile ? `${number(youtubeMobile.value)} of the measured YouTube plays came from mobile devices.` : "No YouTube device evidence is available."],
    ["Engagement", duration(youtube.metrics.average_view_duration_seconds), "Average YouTube view duration in the latest measured window."],
    ["Website geography", topCountry ? `${topCountry.name} · ${topCountry.share_pct}%` : "Geography pending", topCountry ? `${number(topCountry.value)} source-backed active users in the leading country.` : "No GA4 country evidence is available."],
  ].map(([label,value,detail]) => `<article class="highlight-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><p>${escapeHtml(detail)}</p></article>`).join("");
  const coverage = payload.source_coverage || {}; const publicSources = coverage.public || []; const privateSources = coverage.private || [];
  renderConnections(payload.analytics_connectors || {});
  const automated = privateSources.filter((source) => source.connection_mode === "automated"); const limited = privateSources.filter((source) => source.connection_mode === "provider_limited");
  const sourceRow = (source) => `<article class="source-row"><div><strong>${escapeHtml(source.name)}</strong><span class="source-status ${escapeHtml(source.status)}">${escapeHtml(source.status === "data_present" ? "connected" : "access required")}</span></div><small>${source.status === "data_present" ? `${Number(source.observation_count || 0)} observations · through ${escapeHtml(source.latest_period_end || "unknown")}` : escapeHtml(source.access)}</small><p>${source.metrics_present?.length ? `Measured: ${source.metrics_present.map(metricLabel).map(escapeHtml).join(", ")}` : `Can provide: ${source.metrics.map(escapeHtml).join(", ")}`}</p>${source.connection_mode === "provider_limited" ? '<a class="source-import-link" href="/planning?tab=scheduling_intelligence#analytics-import">Open supervised import</a>' : ""}</article>`;
  document.getElementById("source-coverage").innerHTML = `<div class="source-column"><h3>Public distribution <span>${Number(coverage.public_available || 0)}/${Number(coverage.public_expected || 0)}</span></h3>${publicSources.length ? publicSources.map((source) => `<article class="source-row"><div><strong>${escapeHtml(source.source_name)}</strong><span class="source-status ${escapeHtml(source.status)}">${escapeHtml(source.status)}</span></div><small>Checked ${escapeHtml(source.checked_at || "not yet")} · ${number(source.latency_ms)} ms</small></article>`).join("") : empty("The daily public-source monitor has not completed its first run.")}</div><div class="source-column"><h3>Automated evidence <span>${Number(coverage.automated_connected || 0)}/${Number(coverage.automated_expected || 0)}</span></h3>${automated.map(sourceRow).join("")}</div><div class="source-column"><h3>Provider-limited <span>${Number(coverage.provider_limited_count || 0)}</span></h3>${limited.map(sourceRow).join("")}</div>`;
  document.getElementById("platform-grid").innerHTML = (payload.platforms || []).map((platform) => `<a class="platform-card" href="${escapeHtml(safeUrl(platform.url))}" target="_blank" rel="noopener noreferrer"><span>${escapeHtml(platform.kind)}</span><strong>${escapeHtml(platform.name)}</strong><small>Verified ${escapeHtml(platform.verified_on)} · ${escapeHtml(platform.source)}</small></a>`).join("");
  document.getElementById("provider-strength").innerHTML = providers.length ? providers.map((item) => `<article class="provider-row"><div><strong>${escapeHtml(metricLabel(item.provider))}</strong><span class="freshness ${escapeHtml(item.freshness)}">${escapeHtml(item.freshness)}</span></div><p>${Object.entries(item.metrics || {}).map(([key,value]) => `${escapeHtml(metricLabel(key))}: <strong>${number(value)}</strong>`).join(" · ")}</p><small>${escapeHtml(item.period_start)} – ${escapeHtml(item.period_end)} · ${item.sources.length} verified source${item.sources.length === 1 ? "" : "s"}</small></article>`).join("") : empty("No private analytics have been collected.");
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
