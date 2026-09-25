const escapeHtml = window.PerformanceUtils?.escapeHtml || ((value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[character]));
const number = (value) => value == null ? "Unavailable" : new Intl.NumberFormat().format(Number(value));
const safeUrl = (value) => { try { const parsed = new URL(String(value)); return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "#"; } catch { return "#"; } };
const empty = (message) => `<div class="insights-empty"><strong>Not measured yet</strong><p>${escapeHtml(message)}</p><a href="/planning?tab=scheduling_intelligence#analytics-import">Import verified analytics</a></div>`;
const csrfToken = () => decodeURIComponent((document.cookie.match(/(?:^|;\s*)dashboard_csrf=([^;]+)/) || [])[1] || "");
const metricLabel = (value) => String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
const duration = (seconds) => seconds == null ? "Unavailable" : `${Math.floor(Number(seconds) / 60)}m ${Math.round(Number(seconds) % 60)}s`;
let providerLabels = {};
const providerLabel = (provider) => providerLabels[provider] || metricLabel(provider);

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
  const google = connectors.google || {}; const connections = google.connections || (google.connection ? [google.connection] : []);
  const cards = connections.map((connection) => `<article class="connection-card" data-connection-id="${Number(connection.id)}"><header><div><strong>${escapeHtml(connection.youtube_channel_title || "YouTube channel identification pending")}</strong><p>${escapeHtml(connection.account_email || "Google account")} · ${escapeHtml(connection.youtube_channel_id || "Reconnect once to identify this legacy channel")}</p></div><span class="connection-status ${escapeHtml(connection.status || "")}">${escapeHtml(connection.status || "unknown")}</span></header><p>${connection.sync_ga4 ? "YouTube Analytics + primary GA4 website sync" : "YouTube Analytics"}</p><small>Last successful sync: ${escapeHtml(connection.last_success_at || "never")} · ${Number(connection.consecutive_failures || 0)} consecutive failures${connection.next_retry_at ? ` · Retry ${escapeHtml(connection.next_retry_at)}` : ""}</small><div class="connection-actions"><button class="secondary-button" data-sync-google="${Number(connection.id)}" type="button" ${connection.status === "connected" ? "" : "disabled"}>Sync channel</button><button class="ghost-button" data-disconnect-google="${Number(connection.id)}" type="button">Disconnect channel</button></div></article>`).join("");
  const local = connectors.local_collectors || {}; const localConnections = local.connections || {};
  const localCards = [
    ["spotify", "Spotify for Creators"],
    ["apple_podcasts", "Apple Podcasts Connect"],
  ].map(([provider, label]) => {
    const connection = localConnections[provider] || {};
    const enabled = Boolean(connection.enabled);
    return `<article class="connection-card"><header><div><strong>${label}</strong><p>Browser session remains on the authorized local collector.</p></div><span class="connection-status ${escapeHtml(connection.status || "disconnected")}">${escapeHtml(connection.status || "disconnected")}</span></header><p>${enabled ? "Automatic validated export ingestion enabled" : "Local synchronization disabled"}</p><small>Last seen: ${escapeHtml(connection.last_seen_at || "never")} · Last successful sync: ${escapeHtml(connection.last_success_at || "never")}${connection.last_error_code ? ` · ${escapeHtml(connection.last_error_code)}` : ""}</small><div class="connection-actions"><button class="${enabled ? "ghost-button" : "secondary-button"}" data-local-provider="${provider}" data-local-enabled="${enabled ? "false" : "true"}" type="button" ${local.configured ? "" : "disabled"}>${enabled ? "Disable collector" : "Enable local collector"}</button></div></article>`;
  }).join("");
  target.innerHTML = `${cards || '<div class="insights-empty"><strong>No Google channels connected</strong><p>Authorize each channel owner account once.</p></div>'}<article class="connection-card add-connection-card"><header><div><strong>Add another YouTube channel</strong><p>Each Google account is stored and synchronized independently.</p></div></header><button id="connect-google" class="primary-button" type="button" ${google.oauth_configured ? "" : "disabled"}>Connect another Google account</button></article><div class="connection-group-heading"><strong>Local private-analytics collectors</strong><p>${local.configured ? "Railway accepts analytics only; provider sessions stay on your Mac." : "Configure the collector token in Railway before enabling these sources."}</p></div>${localCards}`;
  document.getElementById("connect-google")?.addEventListener("click", async () => { try { const result = await connectorRequest("/api/analytics-connectors/google/connect", {method:"POST", body:"{}"}); window.location.assign(result.authorization_url); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } });
  target.querySelectorAll("[data-sync-google]").forEach((button) => button.addEventListener("click", async () => { try { await connectorRequest("/api/analytics-connectors/google/sync", {method:"POST", body:JSON.stringify({connection_id:Number(button.dataset.syncGoogle)})}); await load(); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } }));
  target.querySelectorAll("[data-disconnect-google]").forEach((button) => button.addEventListener("click", async () => { if (!window.confirm("Disconnect this channel and delete only its retained refresh token?")) return; try { await connectorRequest(`/api/analytics-connectors/google?connection_id=${encodeURIComponent(button.dataset.disconnectGoogle)}`, {method:"DELETE"}); await load(); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } }));
  target.querySelectorAll("[data-local-provider]").forEach((button) => button.addEventListener("click", async () => { try { await connectorRequest("/api/analytics-connectors/local/configure", {method:"POST", body:JSON.stringify({provider:button.dataset.localProvider, enabled:button.dataset.localEnabled === "true"})}); await load(); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } }));
}

function renderBars(items, target) {
  if (!items.length) { target.innerHTML = empty("Import a provider export with dimensional metrics to populate this view."); return; }
  const providers = [...new Set(items.map((item) => item.provider || "source"))];
  target.innerHTML = providers.map((provider) => {
    const group = items.filter((item) => (item.provider || "source") === provider);
    const max = Math.max(...group.map((item) => Number(item.value || 0)), 1);
    return `<div class="insight-bars"><h3>${escapeHtml(providerLabel(provider))}</h3>${group.map((item) => `<div class="insight-bar"><div><strong>${escapeHtml(item.name)}</strong><span>${number(item.value)}${item.share_pct == null ? "" : ` · ${item.share_pct}%`}</span></div><div class="insight-bar-track"><span style="width:${Math.max(2, Number(item.value || 0) * 100 / max)}%"></span></div><small>Through ${escapeHtml(item.period_end || "unknown")}</small></div>`).join("")}</div>`;
  }).join("");
}

function render(payload) {
  const summary = payload.summary || {}; const quality = payload.quality || {};
  const catalog = payload.public_catalog || {};
  const providers = payload.provider_strength || [];
  const youtubeChannels = providers.filter((item) => item.provider === "youtube" || item.provider.startsWith("youtube:"));
  const youtube = youtubeChannels[0] || {metrics:{}};
  const youtubeMetricTotal = (metric) => youtubeChannels.reduce((total, item) => total + Number(item.metrics?.[metric] || 0), 0);
  const website = providers.find((item) => item.provider === "website") || {metrics:{}};
  const connections = payload.analytics_connectors?.google?.connections || [];
  providerLabels = Object.fromEntries(connections.filter((item) => item.youtube_channel_id).map((item) => [`youtube:${String(item.youtube_channel_id).toLowerCase()}`, item.youtube_channel_title || item.youtube_channel_id]));
  const latestConnectionSuccess = connections.map((item) => item.last_success_at).filter(Boolean).sort().at(-1);
  document.getElementById("insights-quality").innerHTML = `<div><span class="coverage-pill ${quality.status}">${escapeHtml(quality.status || "unknown")} evidence</span><strong>${number(quality.observation_count)} verified observations</strong><p>Latest measured period: ${escapeHtml(quality.latest_period_end || "none")}</p></div><div><strong>Automated collection</strong><p>${connections.some((item) => item.status === "connected") ? `${connections.filter((item) => item.status === "connected").length} channel connection(s) healthy · latest sync ${escapeHtml(latestConnectionSuccess || "pending")}` : "Connection needs attention"}</p></div><div><strong>Still unmeasured</strong><p>${(quality.missing_core_metrics || []).map(metricLabel).join(", ") || "None"}</p></div>`;
  document.getElementById("insights-summary").innerHTML = [
    ["Published episodes", number(catalog.published_episodes), `RSS catalog: ${number(catalog.rss_items)} items`],
    ["YouTube plays", number(summary.plays), summary.plays_period_end ? `28-day window ending ${summary.plays_period_end}` : "Not measured"],
    ["YouTube watch time", youtubeChannels.length ? `${youtubeMetricTotal("watch_time_hours").toFixed(1)}h` : "Unavailable", `${youtubeChannels.length} connected channel${youtubeChannels.length === 1 ? "" : "s"}`],
    ["YouTube channel subscribers", youtubeChannels.length ? number(youtubeMetricTotal("subscribers")) : "Unavailable", `Sum of channel counters; not deduplicated people`],
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
  document.getElementById("provider-strength").innerHTML = providers.length ? providers.map((item) => `<article class="provider-row"><div><strong>${escapeHtml(providerLabel(item.provider))}</strong><span class="freshness ${escapeHtml(item.freshness)}">${escapeHtml(item.freshness)}</span></div><p>${Object.entries(item.metrics || {}).map(([key,value]) => `${escapeHtml(metricLabel(key))}: <strong>${number(value)}</strong>`).join(" · ")}</p><small>${escapeHtml(item.period_start)} – ${escapeHtml(item.period_end)} · ${item.sources.length} verified source${item.sources.length === 1 ? "" : "s"}</small></article>`).join("") : empty("No private analytics have been collected.");
  const audience = payload.audience_by_platform || [];
  document.getElementById("audience-platform").innerHTML = audience.length ? audience.map((item) => `<article class="provider-row"><div><strong>${escapeHtml(providerLabel(item.provider))}</strong><span>${number(item.value)}</span></div><p>${escapeHtml(item.metric.replaceAll("_", " "))}</p><small>Through ${escapeHtml(item.period_end)}</small></article>`).join("") : empty("Import unique listeners, followers, or subscriber counts from each platform. These will remain separate to prevent double-counting.");
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
