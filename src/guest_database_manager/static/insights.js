const escapeHtml = window.PerformanceUtils?.escapeHtml || ((value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[character]));
const number = (value) => value == null ? "Unavailable" : new Intl.NumberFormat().format(Number(value));
const safeUrl = (value) => { try { const parsed = new URL(String(value)); return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "#"; } catch { return "#"; } };
const empty = (message) => `<div class="insights-empty"><strong>Not measured yet</strong><p>${escapeHtml(message)}</p><a href="/planning?tab=scheduling_intelligence#analytics-import">Import verified analytics</a></div>`;
const csrfToken = () => decodeURIComponent((document.cookie.match(/(?:^|;\s*)dashboard_csrf=([^;]+)/) || [])[1] || "");
const metricLabel = (value) => String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
const duration = (seconds) => seconds == null ? "Unavailable" : `${Math.floor(Number(seconds) / 60)}m ${Math.round(Number(seconds) % 60)}s`;
let providerLabels = {};
let trendRange = 24;
const providerLabel = (provider) => providerLabels[provider] || metricLabel(provider);

function linePath(values, width, height, maxValue) {
  if (!values.length) return "";
  return values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : index * width / (values.length - 1);
    const y = height - (Number(value || 0) / Math.max(maxValue, 1)) * height;
    return `${index ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function trendChart(title, rows, series) {
  const selected = trendRange === 0 ? rows : rows.slice(-trendRange);
  if (!selected.length) return `<article class="trend-card"><h3>${escapeHtml(title)}</h3>${empty("No monthly history is available.")}</article>`;
  const width = 720; const height = 210;
  const maxValue = Math.max(...selected.flatMap((row) => series.map((item) => Number(row[item.key] || 0))), 1);
  const first = selected[0].period; const middle = selected[Math.floor((selected.length - 1) / 2)].period; const last = selected.at(-1).period;
  const paths = series.map((item) => `<path class="trend-line ${item.className}" d="${linePath(selected.map((row) => row[item.key]), width, height, maxValue)}"></path>`).join("");
  const latest = selected.at(-1);
  const tableRows = selected.map((row) => `<tr><td>${escapeHtml(row.period)}</td>${series.map((item) => `<td>${number(row[item.key])}</td>`).join("")}</tr>`).join("");
  return `<article class="trend-card"><div class="trend-card-heading"><div><h3>${escapeHtml(title)}</h3><p>${series.map((item) => `${escapeHtml(item.label)}: <strong>${number(latest[item.key])}</strong>`).join(" · ")} in ${escapeHtml(last)}</p></div><div class="trend-legend">${series.map((item) => `<span class="${item.className}">${escapeHtml(item.label)}</span>`).join("")}</div></div><svg class="line-chart" viewBox="0 0 ${width} ${height + 28}" role="img" aria-label="${escapeHtml(title)} monthly trend from ${escapeHtml(first)} to ${escapeHtml(last)}"><line x1="0" y1="${height}" x2="${width}" y2="${height}" class="chart-axis"></line>${paths}<text x="0" y="${height + 22}">${escapeHtml(first)}</text><text x="${width / 2}" y="${height + 22}" text-anchor="middle">${escapeHtml(middle)}</text><text x="${width}" y="${height + 22}" text-anchor="end">${escapeHtml(last)}</text></svg><details class="trend-data"><summary>View monthly values</summary><div class="trend-table-wrap"><table><thead><tr><th>Month</th>${series.map((item) => `<th>${escapeHtml(item.label)}</th>`).join("")}</tr></thead><tbody>${tableRows}</tbody></table></div></details></article>`;
}

function renderMonthlyTrends(monthly) {
  const spotify = monthly.spotify || []; const apple = monthly.apple_podcasts || [];
  const target = document.getElementById("reach-trend");
  target.innerHTML = `<div class="trend-controls" aria-label="Trend range"><button type="button" data-trend-range="12" class="${trendRange === 12 ? "active" : ""}">12 months</button><button type="button" data-trend-range="24" class="${trendRange === 24 ? "active" : ""}">24 months</button><button type="button" data-trend-range="0" class="${trendRange === 0 ? "active" : ""}">All history</button></div><div class="monthly-trend-grid">${trendChart("Spotify activity", spotify, [{key:"downloads",label:"Downloads",className:"series-primary"},{key:"plays",label:"Spotify plays",className:"series-secondary"}])}${trendChart("Apple listening", apple, [{key:"plays",label:"Plays",className:"series-primary"},{key:"listeners",label:"Monthly listeners",className:"series-secondary"}])}</div>`;
  target.querySelectorAll("[data-trend-range]").forEach((button) => button.addEventListener("click", () => { trendRange = Number(button.dataset.trendRange); renderMonthlyTrends(monthly); }));
}

function renderDecisionIntelligence(intelligence) {
  const target = document.getElementById("decision-intelligence");
  const recommendations = intelligence.recommendations || [];
  const confidence = Number(intelligence.confidence_score || 0);
  document.getElementById("decision-confidence").textContent = `${Math.round(confidence * 100)}% evidence confidence · advisory shadow mode`;
  target.innerHTML = recommendations.length ? recommendations.map((item) => `<article class="decision-card ${escapeHtml(item.priority || "normal")}"><header><span>${escapeHtml(item.priority || "normal")} priority</span><span>${escapeHtml(item.confidence || "unknown")} confidence</span></header><h3>${escapeHtml(item.action)}</h3><p>${escapeHtml(item.rationale)}</p><small>No ranking or publishing change was made.</small></article>`).join("") : `<div class="insights-empty"><strong>No action required</strong><p>The current evidence does not support a material planning change.</p></div>`;
}

async function connectorRequest(path, options = {}) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 30000);
  const headers = {Accept:"application/json", "Content-Type":"application/json", ...(options.headers || {})};
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = csrfToken();
  try {
    const response = await fetch(path, {credentials:"same-origin", ...options, headers, signal:controller.signal});
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `The analytics connection request failed (${response.status}).`);
    return payload;
  } catch (error) {
    if (error?.name === "AbortError") throw new Error("The analytics request timed out. Check service health and try again.");
    if (error instanceof TypeError) throw new Error("The analytics service could not be reached. Refresh the page; if this continues, check /readyz and the latest deployment.");
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
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
  target.innerHTML = providers.map((provider, providerIndex) => {
    const all = items.filter((item) => (item.provider || "source") === provider);
    const group = all.slice(0, 8);
    const max = Math.max(...group.map((item) => Number(item.value || 0)), 1);
    const remainder = all.length - group.length;
    return `<details class="dimension-group" ${providerIndex === 0 ? "open" : ""}><summary><strong>${escapeHtml(providerLabel(provider))}</strong><span>${all.length} measured ${all.length === 1 ? "segment" : "segments"}</span></summary><div class="insight-bars">${group.map((item) => `<div class="insight-bar"><div><strong>${escapeHtml(item.name)}</strong><span>${number(item.value)}${item.share_pct == null ? "" : ` · ${item.share_pct}%`}</span></div><div class="insight-bar-track"><span style="width:${Math.max(2, Number(item.value || 0) * 100 / max)}%"></span></div><small>${escapeHtml(item.measure === "plays" ? "All-time plays" : `Through ${item.period_end || "unknown"}`)}</small></div>`).join("")}${remainder > 0 ? `<p class="dimension-note">Top 8 shown · ${remainder} additional ${remainder === 1 ? "entry" : "entries"} included in percentage totals.</p>` : ""}</div></details>`;
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
  document.getElementById("insights-quality").innerHTML = `<div><span class="coverage-pill ${quality.status}">${escapeHtml(quality.status || "unknown")} evidence</span><strong>${number(quality.observation_count)} verified observations</strong><p>Latest reporting-period end: ${escapeHtml(quality.latest_period_end || "none")}</p></div><div><strong>Automated collection</strong><p>${connections.some((item) => item.status === "connected") ? `${connections.filter((item) => item.status === "connected").length} channel connection(s) healthy · latest sync ${escapeHtml(latestConnectionSuccess || "pending")}` : "Connection needs attention"}</p></div><div><strong>Still unmeasured</strong><p>${(quality.missing_core_metrics || []).map(metricLabel).join(", ") || "None"}</p></div>`;
  const spotify = summary.spotify_28d || {};
  document.getElementById("insights-summary").innerHTML = [
    ["Published episodes", number(catalog.published_episodes), `RSS catalog: ${number(catalog.rss_items)} items`],
    ["YouTube views", number(summary.plays), summary.plays_period_end ? `Connected channels · 28-day window ending ${summary.plays_period_end}` : "Not measured"],
    ["YouTube watch time", youtubeChannels.length ? `${youtubeMetricTotal("watch_time_hours").toFixed(1)}h` : "Unavailable", `${youtubeChannels.length} connected channel${youtubeChannels.length === 1 ? "" : "s"}`],
    ["YouTube channel subscribers", youtubeChannels.length ? number(youtubeMetricTotal("subscribers")) : "Unavailable", `Sum of channel counters; not deduplicated people`],
    ["Spotify downloads", number(spotify.downloads), spotify.period_end ? `Rolling 28 days · ${spotify.period_start} – ${spotify.period_end}` : "Not measured"],
    ["Spotify plays", number(spotify.plays), spotify.period_end ? `Rolling 28 days · ${spotify.period_start} – ${spotify.period_end}` : "Not measured"],
  ].map(([label,value,detail]) => `<article class="summary-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`).join("");
  const youtubeDevices = (payload.devices || []).filter((item) => item.provider === "youtube" || item.provider.startsWith("youtube:"));
  const youtubeDeviceTotal = youtubeDevices.reduce((total, item) => total + Number(item.value || 0), 0);
  const youtubeMobileValue = youtubeDevices.filter((item) => item.name === "Mobile").reduce((total, item) => total + Number(item.value || 0), 0);
  const youtubeMobileShare = youtubeDeviceTotal ? Math.round(youtubeMobileValue * 1000 / youtubeDeviceTotal) / 10 : null;
  const weightedDuration = youtubeChannels.reduce((total, item) => total + Number(item.metrics?.average_view_duration_seconds || 0) * Number(item.metrics?.plays || 0), 0) / Math.max(youtubeMetricTotal("plays"), 1);
  const websiteCountries = (payload.countries || []).filter((item) => item.provider === "website");
  const topCountry = [...websiteCountries].sort((left, right) => Number(right.value) - Number(left.value))[0];
  document.getElementById("reach-highlights").innerHTML = [
    ["YouTube viewing", youtubeMobileShare == null ? "Device mix pending" : `${youtubeMobileShare}% mobile`, youtubeMobileShare == null ? "No YouTube device evidence is available." : `${number(youtubeMobileValue)} measured views came from mobile devices across connected channels.`],
    ["YouTube engagement", youtubeChannels.length ? duration(weightedDuration) : "Unavailable", "View-weighted average duration across connected channels in the latest measured window."],
    ["Website geography", topCountry ? `${topCountry.name} · ${topCountry.share_pct}%` : "Geography pending", topCountry ? `${number(topCountry.value)} source-backed active users in the leading country.` : "No GA4 country evidence is available."],
  ].map(([label,value,detail]) => `<article class="highlight-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><p>${escapeHtml(detail)}</p></article>`).join("");
  const spotifyLifetime = summary.spotify_lifetime || {};
  const apple = summary.apple || {};
  const totalCard = (label, value, detail) => `<div class="total-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></div>`;
  document.getElementById("platform-overviews").innerHTML = `<article class="platform-overview"><div class="platform-overview-heading"><div><span>Spotify for Creators</span><h2>Audio performance</h2></div><small>${escapeHtml(spotifyLifetime.period_start || "—")} – ${escapeHtml(spotifyLifetime.period_end || "—")}</small></div><div class="total-metric-grid">${totalCard("Lifetime downloads", number(spotifyLifetime.downloads), "Everywhere outside Spotify")}${totalCard("Lifetime Spotify plays", number(spotifyLifetime.plays), "Additive play starts")}${totalCard("Last 28 days", number((spotify.downloads || 0) + (spotify.plays || 0)), `${number(spotify.downloads)} downloads · ${number(spotify.plays)} plays`)}${totalCard("Latest daily audience", number(spotify.latest_daily_audience), `Single day ending ${spotify.period_end || "—"}; not a lifetime unique total`)}</div></article><article class="platform-overview"><div class="platform-overview-heading"><div><span>Apple Podcasts</span><h2>Listening performance</h2></div><small>${escapeHtml(apple.period_start || "—")} – ${escapeHtml(apple.period_end || "—")}</small></div><div class="total-metric-grid">${totalCard("Lifetime plays", number(apple.plays), "Additive country-month plays")}${totalCard("Lifetime listening time", apple.listening_time_hours == null ? "Unavailable" : `${number(Math.round(apple.listening_time_hours))}h`, "Summed listening seconds converted to hours")}${totalCard("Latest monthly listeners", number(apple.latest_month_listeners), `Reporting month ending ${apple.period_end || "—"}`)}${totalCard("Followers", number(apple.followers), "Latest net follower total")}</div></article>`;
  renderDecisionIntelligence(payload.decision_intelligence || {});
  const coverage = payload.source_coverage || {}; const publicSources = coverage.public || []; const privateSources = coverage.private || [];
  renderConnections(payload.analytics_connectors || {});
  const automated = privateSources.filter((source) => source.connection_mode === "automated"); const limited = privateSources.filter((source) => source.connection_mode === "provider_limited");
  const sourceRow = (source) => { const metrics = source.metrics_present?.length ? source.metrics_present : source.metrics || []; const shown = metrics.slice(0, 5); return `<article class="source-row"><div><strong>${escapeHtml(source.name)}</strong><span class="source-status ${escapeHtml(source.status)}">${escapeHtml(source.status === "data_present" ? "connected" : "access required")}</span></div><small>${source.status === "data_present" ? `${Number(source.observation_count || 0)} observations · through ${escapeHtml(source.latest_period_end || "unknown")}` : escapeHtml(source.access)}</small><p>${source.metrics_present?.length ? "Measured" : "Can provide"}: ${shown.map(metricLabel).map(escapeHtml).join(", ")}${metrics.length > shown.length ? ` +${metrics.length - shown.length} more` : ""}</p>${source.connection_mode === "provider_limited" ? '<a class="source-import-link" href="/planning?tab=scheduling_intelligence#analytics-import">Open supervised import</a>' : ""}</article>`; };
  document.getElementById("source-coverage").innerHTML = `<div class="source-column"><h3>Public distribution <span>${Number(coverage.public_available || 0)}/${Number(coverage.public_expected || 0)}</span></h3>${publicSources.length ? publicSources.map((source) => `<article class="source-row"><div><strong>${escapeHtml(source.source_name)}</strong><span class="source-status ${escapeHtml(source.status)}">${escapeHtml(source.status)}</span></div><small>Checked ${escapeHtml(source.checked_at || "not yet")} · ${number(source.latency_ms)} ms</small></article>`).join("") : empty("The daily public-source monitor has not completed its first run.")}</div><div class="source-column"><h3>Automated evidence <span>${Number(coverage.automated_connected || 0)}/${Number(coverage.automated_expected || 0)}</span></h3>${automated.map(sourceRow).join("")}</div><div class="source-column"><h3>Provider-limited <span>${Number(coverage.provider_limited_count || 0)}</span></h3>${limited.map(sourceRow).join("")}</div>`;
  document.getElementById("platform-grid").innerHTML = (payload.platforms || []).map((platform) => `<a class="platform-card" href="${escapeHtml(safeUrl(platform.url))}" target="_blank" rel="noopener noreferrer"><span>${escapeHtml(platform.kind)}</span><strong>${escapeHtml(platform.name)}</strong><small>Verified ${escapeHtml(platform.verified_on)} · ${escapeHtml(platform.source)}</small></a>`).join("");
  document.getElementById("provider-strength").innerHTML = providers.length ? providers.map((item) => `<article class="provider-row"><div><strong>${escapeHtml(providerLabel(item.provider))}</strong><span class="freshness ${escapeHtml(item.freshness)}">${escapeHtml(item.freshness)}</span></div><p class="metric-pairs">${Object.entries(item.metrics || {}).map(([key,value]) => `<span>${escapeHtml(metricLabel(key))}<strong>${number(value)}</strong></span>`).join("")}</p><small>${escapeHtml(item.period_start)} – ${escapeHtml(item.period_end)} · ${item.sources.length} verified source${item.sources.length === 1 ? "" : "s"}</small></article>`).join("") : empty("No private analytics have been collected.");
  const audience = payload.audience_by_platform || [];
  document.getElementById("audience-platform").innerHTML = audience.length ? audience.map((item) => `<article class="provider-row"><div><strong>${escapeHtml(providerLabel(item.provider))}</strong><span>${number(item.value)}</span></div><p>${escapeHtml(item.metric.replaceAll("_", " "))}</p><small>Through ${escapeHtml(item.period_end)}</small></article>`).join("") : empty("Import unique listeners, followers, or subscriber counts from each platform. These will remain separate to prevent double-counting.");
  renderBars(payload.devices || [], document.getElementById("device-breakdown"));
  renderBars(payload.countries || [], document.getElementById("country-breakdown"));
  renderBars(payload.cities || [], document.getElementById("city-breakdown"));
  renderMonthlyTrends(payload.monthly_trends || {});
  document.getElementById("metric-definitions").innerHTML = Object.entries(payload.definitions || {}).map(([key,value]) => `<article><strong>${escapeHtml(key.replaceAll("_", " "))}</strong><p>${escapeHtml(value)}</p></article>`).join("") + `<article><strong>Reliability guardrails</strong><p>${(quality.limitations || []).map(escapeHtml).join(" ")}</p></article>`;
}

async function load() {
  render(await connectorRequest("/api/podcast-insights"));
}
document.getElementById("insights-refresh")?.addEventListener("click", () => load().catch((error) => { document.getElementById("insights-quality").textContent = error.message; }));
load().catch((error) => { document.getElementById("insights-quality").textContent = error.message; });
