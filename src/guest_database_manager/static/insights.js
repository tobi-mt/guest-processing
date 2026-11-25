const escapeHtml = window.PerformanceUtils?.escapeHtml || ((value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[character]));
const number = (value) => value == null ? "—" : new Intl.NumberFormat().format(Number(value));
const safeUrl = (value) => { try { const parsed = new URL(String(value)); return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "#"; } catch { return "#"; } };
const empty = (message) => `<div class="insights-empty"><strong>Collecting automatically</strong><p>${escapeHtml(message)}</p></div>`;
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

function trendChart(title, rows, series, options = {}) {
  const range = options.range ?? trendRange;
  const selected = range === 0 ? rows : rows.slice(-range);
  if (!selected.length) return `<article class="trend-card"><h3>${escapeHtml(title)}</h3>${empty(options.emptyMessage || "No comparable history is available yet.")}</article>`;
  const width = 720; const height = 210;
  const maxValue = Math.max(...selected.flatMap((row) => series.map((item) => Number(row[item.key] || 0))), 1);
  const first = selected[0].period; const middle = selected[Math.floor((selected.length - 1) / 2)].period; const last = selected.at(-1).period;
  const paths = series.map((item) => `<path class="trend-line ${item.className}" d="${linePath(selected.map((row) => row[item.key]), width, height, maxValue)}"></path>`).join("");
  const latest = selected.at(-1);
  const tableRows = selected.map((row) => `<tr><td>${escapeHtml(row.period)}</td>${series.map((item) => `<td>${number(row[item.key])}</td>`).join("")}</tr>`).join("");
  return `<article class="trend-card ${options.className || ""}"><div class="trend-card-heading"><div><h3>${escapeHtml(title)}</h3><p>${series.map((item) => `${escapeHtml(item.label)}: <strong>${number(latest[item.key])}</strong>`).join(" · ")} through ${escapeHtml(last)}</p></div><div class="trend-legend">${series.map((item) => `<span class="${item.className}">${escapeHtml(item.label)}</span>`).join("")}</div></div><svg class="line-chart" viewBox="0 0 ${width} ${height + 28}" role="img" aria-label="${escapeHtml(title)} trend from ${escapeHtml(first)} to ${escapeHtml(last)}"><line x1="0" y1="${height}" x2="${width}" y2="${height}" class="chart-axis"></line>${paths}<text x="0" y="${height + 22}">${escapeHtml(first)}</text><text x="${width / 2}" y="${height + 22}" text-anchor="middle">${escapeHtml(middle)}</text><text x="${width}" y="${height + 22}" text-anchor="end">${escapeHtml(last)}</text></svg><details class="trend-data"><summary>View exact values</summary><div class="trend-table-wrap"><table><thead><tr><th>${escapeHtml(options.periodLabel || "Period")}</th>${series.map((item) => `<th>${escapeHtml(item.label)}</th>`).join("")}</tr></thead><tbody>${tableRows}</tbody></table></div></details></article>`;
}

function renderMonthlyTrends(monthly) {
  const spotify = monthly.spotify || []; const apple = monthly.apple_podcasts || [];
  const target = document.getElementById("reach-trend");
  target.innerHTML = `<div class="trend-controls" aria-label="Trend range"><button type="button" data-trend-range="12" class="${trendRange === 12 ? "active" : ""}">12 months</button><button type="button" data-trend-range="24" class="${trendRange === 24 ? "active" : ""}">24 months</button><button type="button" data-trend-range="0" class="${trendRange === 0 ? "active" : ""}">All history</button></div><div class="monthly-trend-grid">${trendChart("Spotify activity", spotify, [{key:"downloads",label:"Downloads",className:"series-primary"},{key:"plays",label:"Spotify plays",className:"series-secondary"}])}${trendChart("Apple listening", apple, [{key:"plays",label:"Plays",className:"series-primary"},{key:"listeners",label:"Monthly listeners",className:"series-secondary"}])}</div>`;
  target.querySelectorAll("[data-trend-range]").forEach((button) => button.addEventListener("click", () => { trendRange = Number(button.dataset.trendRange); renderMonthlyTrends(monthly); }));
}

const changeLabel = (stat) => {
  if (!stat || stat.delta_pct == null) return {text:"No prior comparable period", className:"neutral"};
  const direction = Number(stat.delta_pct) > 0 ? "+" : "";
  return {text:`${direction}${number(stat.delta_pct)}% vs prior period`, className:Number(stat.delta_pct) > 0 ? "positive" : Number(stat.delta_pct) < 0 ? "negative" : "neutral"};
};

function renderOverallPerformance(trend, global) {
  const target = document.getElementById("overall-performance-trend");
  const comparable = (trend || []).filter((item) => item.coverage === "complete");
  const excluded = (trend || []).length - comparable.length;
  const comparison = global.comparison || {};
  const change = changeLabel(comparison.total);
  target.innerHTML = `${comparison.available ? `<div class="performance-change ${change.className}"><strong>${escapeHtml(change.text)}</strong><span>${number(comparison.total.delta)} activity change · ${escapeHtml(comparison.current_period_start)}–${escapeHtml(comparison.current_period_end)} compared with ${escapeHtml(comparison.previous_period_start)}–${escapeHtml(comparison.previous_period_end)}</span></div>` : ""}${trendChart("Overall measured activity", comparable, [{key:"total",label:"Total activity",className:"series-total"},{key:"audio",label:"Audio starts",className:"series-primary"},{key:"video",label:"Video views",className:"series-secondary"}], {range:12,className:"overall-trend-card",periodLabel:"Window ending",emptyMessage:"Two fully covered reporting windows are needed to show reliable movement."})}${excluded ? `<p class="trend-quality-note">${number(excluded)} incomplete reporting window${excluded === 1 ? " was" : "s were"} excluded from growth comparisons.</p>` : ""}`;
}

function renderPlatformPerformance(global, monthly, listeningApps) {
  const target = document.getElementById("platform-performance");
  const total = Number(global.measured_activity || 0);
  const components = Object.fromEntries((global.components || []).map((item) => [item.key, item]));
  const comparison = global.comparison || {};
  const componentStats = comparison.components || {};
  const cards = [
    ["open_rss_downloads", "Podcast apps (RSS)", "Downloads delivered across Apple Podcasts and every other RSS app."],
    ["spotify_native_plays", "Spotify", "Native Spotify play starts."],
    ["youtube_views", "YouTube", "Video and podcast views from connected channels."],
  ].map(([key,label,description]) => {
    const component = components[key] || {};
    const value = component.value;
    const share = value == null || !total ? null : Math.round(Number(value) * 1000 / total) / 10;
    const change = changeLabel(componentStats[key]);
    return `<article class="performance-platform-card"><div><span>${escapeHtml(label)}</span><strong>${number(value)}</strong></div><p>${escapeHtml(description)}</p><div class="platform-card-meta"><span>${share == null ? "Awaiting data" : `${number(share)}% of measured activity`}</span><span class="metric-change ${change.className}">${escapeHtml(change.text)}</span></div></article>`;
  });
  const appleRows = monthly.apple_podcasts || [];
  const appleCurrent = appleRows.at(-1); const applePrevious = appleRows.at(-2);
  const appleStat = appleCurrent && applePrevious ? {delta_pct:applePrevious.plays ? Math.round((Number(appleCurrent.plays) - Number(applePrevious.plays)) * 1000 / Number(applePrevious.plays)) / 10 : null} : null;
  const appleChange = changeLabel(appleStat);
  cards.push(`<article class="performance-platform-card diagnostic"><div><span>Apple Podcasts engagement</span><strong>${number(appleCurrent?.plays)}</strong></div><p>Apple-native plays for ${escapeHtml(appleCurrent?.period || "the latest reported month")}; shown separately to prevent double-counting RSS delivery.</p><div class="platform-card-meta"><span>${number(appleCurrent?.listeners)} listeners</span><span class="metric-change ${appleChange.className}">${escapeHtml(appleChange.text)}</span></div></article>`);
  target.innerHTML = cards.join("");

  const appTarget = document.getElementById("listening-app-summary");
  const apps = (listeningApps || []).slice(0, 8);
  appTarget.innerHTML = apps.length ? `<div class="listening-app-heading"><h3>Podcast-app breakdown</h3><p>Host-reported delivery already included in the RSS total above.</p></div><div class="listening-app-chips">${apps.map((item) => `<span><strong>${escapeHtml(item.name)}</strong>${item.is_percentage ? `${number(item.value)}%` : `${number(item.value)} · ${number(item.share_pct)}%`}</span>`).join("")}</div>` : `<p class="platform-coverage-note">The RSS total covers all podcast apps. Per-app contribution will appear here when the hosting source provides listening-app detail.</p>`;
}

function renderDecisionIntelligence(intelligence) {
  const target = document.getElementById("decision-intelligence");
  const recommendations = (intelligence.recommendations || []).filter((item) => item.id !== "learning-evidence");
  const confidence = Number(intelligence.confidence_score || 0);
  document.getElementById("decision-confidence").textContent = confidence >= .7 ? "Strong evidence" : confidence >= .4 ? "Useful early signal" : "Building from available history";
  target.innerHTML = recommendations.length ? recommendations.slice(0, 4).map((item, index) => `<article class="decision-card ${escapeHtml(item.priority || "normal")}"><header><span>Next move ${index + 1}</span><span>${item.confidence === "high" ? "Well supported" : "Directional"}</span></header><h3>${escapeHtml(item.action)}</h3><p>${escapeHtml(item.rationale)}</p></article>`).join("") : `<div class="insights-empty"><strong>Stay the course</strong><p>No meaningful change is supported by the current audience pattern.</p></div>`;
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
  const cards = connections.map((connection) => `<article class="connection-card" data-connection-id="${Number(connection.id)}"><header><div><strong>${escapeHtml(connection.youtube_channel_title || "YouTube channel")}</strong><p>${escapeHtml(connection.account_email || "Google account")}</p></div><span class="connection-status ${connection.status === "connected" ? "connected" : "disconnected"}">${connection.status === "connected" ? "Current" : "Reconnect"}</span></header><p>${connection.sync_ga4 ? "YouTube and website audience insights" : "YouTube audience insights"}</p><small>Last update: ${escapeHtml(connection.last_success_at || "No successful update yet")}</small><div class="connection-actions"><button class="secondary-button" data-sync-google="${Number(connection.id)}" type="button" ${connection.status === "connected" ? "" : "disabled"}>Update channel</button><button class="ghost-button" data-disconnect-google="${Number(connection.id)}" type="button">Disconnect</button></div></article>`).join("");
  const local = connectors.local_collectors || {}; const localConnections = local.connections || {};
  const localCards = [
    ["spotify", "Spotify for Creators"],
    ["apple_podcasts", "Apple Podcasts Connect"],
  ].map(([provider, label]) => {
    const connection = localConnections[provider] || {};
    const enabled = Boolean(connection.enabled);
    const current = enabled && connection.status === "connected";
    return `<article class="connection-card"><header><div><strong>${label}</strong><p>The secure sign-in stays on the account owner's computer.</p></div><span class="connection-status ${current ? "connected" : "disconnected"}">${current ? "Current" : enabled ? "Complete sign-in" : "Set up"}</span></header><p>${current ? "Reports are arriving automatically." : "One owner-approved connection unlocks private audience data."}</p><small>Last update: ${escapeHtml(connection.last_success_at || "No successful update yet")}</small><div class="connection-actions"><button class="${enabled ? "ghost-button" : "secondary-button"}" data-local-provider="${provider}" data-local-enabled="${enabled ? "false" : "true"}" type="button" ${local.configured ? "" : "disabled"}>${enabled ? "Pause connection" : "Start setup"}</button></div></article>`;
  }).join("");
  target.innerHTML = `${cards || '<div class="insights-empty"><strong>Connect YouTube</strong><p>Authorize the channel owner once to unlock viewing, audience, and discovery insights.</p></div>'}<article class="connection-card add-connection-card"><header><div><strong>Add a YouTube channel</strong><p>Each owner approves access independently.</p></div></header><button id="connect-google" class="primary-button" type="button" ${google.oauth_configured ? "" : "disabled"}>Connect YouTube</button></article><div class="connection-group-heading"><strong>Podcast analytics</strong><p>Hosting and native-platform reports refresh automatically; private sign-ins never leave the account owner's computer.</p></div>${localCards}`;
  document.getElementById("connect-google")?.addEventListener("click", async () => { try { const result = await connectorRequest("/api/analytics-connectors/google/connect", {method:"POST", body:"{}"}); window.location.assign(result.authorization_url); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } });
  target.querySelectorAll("[data-sync-google]").forEach((button) => button.addEventListener("click", async () => { try { await connectorRequest("/api/analytics-connectors/google/sync", {method:"POST", body:JSON.stringify({connection_id:Number(button.dataset.syncGoogle)})}); await load(); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } }));
  target.querySelectorAll("[data-disconnect-google]").forEach((button) => button.addEventListener("click", async () => { if (!window.confirm("Disconnect this channel and delete only its retained refresh token?")) return; try { await connectorRequest(`/api/analytics-connectors/google?connection_id=${encodeURIComponent(button.dataset.disconnectGoogle)}`, {method:"DELETE"}); await load(); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } }));
  target.querySelectorAll("[data-local-provider]").forEach((button) => button.addEventListener("click", async () => { try { await connectorRequest("/api/analytics-connectors/local/configure", {method:"POST", body:JSON.stringify({provider:button.dataset.localProvider, enabled:button.dataset.localEnabled === "true"})}); await load(); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } }));
}

function renderBars(items, target) {
  if (!items.length) { target.innerHTML = empty("Connected sources have not exposed this breakdown yet. Podcast Reach will show it as soon as the source provides it."); return; }
  const groups = [...new Set(items.map((item) => `${item.provider || "source"}\u0000${item.dimension_group || ""}`))];
  target.innerHTML = groups.map((groupKey, providerIndex) => {
    const [provider, dimensionGroup] = groupKey.split("\u0000");
    const all = items.filter((item) => (item.provider || "source") === provider && (item.dimension_group || "") === dimensionGroup);
    const group = all.slice(0, 8);
    const max = Math.max(...group.map((item) => Number(item.value || 0)), 1);
    const remainder = all.length - group.length;
    const heading = dimensionGroup ? `${providerLabel(provider)} · ${dimensionGroup}` : providerLabel(provider);
    return `<details class="dimension-group" ${providerIndex === 0 ? "open" : ""}><summary><strong>${escapeHtml(heading)}</strong><span>${all.length} measured ${all.length === 1 ? "segment" : "segments"}</span></summary><div class="insight-bars">${group.map((item) => `<div class="insight-bar"><div><strong>${escapeHtml(item.name)}</strong><span>${item.is_percentage ? `${number(item.value)}%` : `${number(item.value)}${item.share_pct == null ? "" : ` · ${item.share_pct}%`}`}</span></div><div class="insight-bar-track"><span style="width:${Math.max(2, Number(item.value || 0) * 100 / max)}%"></span></div><small>${escapeHtml(item.measure === "plays" ? "All-time plays" : `Through ${item.period_end || "unknown"}`)}</small></div>`).join("")}${remainder > 0 ? `<p class="dimension-note">Top 8 shown · ${remainder} additional ${remainder === 1 ? "entry" : "entries"} included in percentage totals.</p>` : ""}</div></details>`;
  }).join("");
}

function renderTopPlatformContent(items) {
  const target = document.getElementById("video-performance");
  if (!items.length) { target.innerHTML = empty("Connected content sources have not returned item-level performance yet."); return; }
  target.innerHTML = items.slice(0, 12).map((item) => `<article class="provider-row"><div><strong>${escapeHtml(item.title || item.platform_content_id)}</strong><span>${number(item.metrics?.video_views)} views</span></div><p class="metric-pairs"><span>Watch time<strong>${number(Number(item.metrics?.video_watch_time_hours || 0).toFixed(1))}h</strong></span><span>Average view<strong>${duration(item.metrics?.video_average_view_duration_seconds)}</strong></span></p><small>${escapeHtml(providerLabel(item.provider))} · through ${escapeHtml(item.period_end || "unknown")}</small></article>`).join("");
}

function render(payload) {
  const summary = payload.summary || {}; const quality = payload.quality || {};
  const release = payload.release_readiness || {};
  const providers = payload.provider_strength || [];
  const youtubeChannels = providers.filter((item) => item.provider === "youtube" || item.provider.startsWith("youtube:"));
  const youtubeMetricTotal = (metric) => youtubeChannels.reduce((total, item) => total + Number(item.metrics?.[metric] || 0), 0);
  const connections = payload.analytics_connectors?.google?.connections || [];
  providerLabels = Object.fromEntries(connections.filter((item) => item.youtube_channel_id).map((item) => [`youtube:${String(item.youtube_channel_id).toLowerCase()}`, item.youtube_channel_title || item.youtube_channel_id]));
  const releaseReady = release.status === "ready";
  const measuredSourcesCurrent = providers.length > 0 && providers.every((item) => item.freshness === "current");
  const rawSetupItems = release.blockers || [];
  const sourceSetupPending = rawSetupItems.some((item) => ["youtube_analytics_not_ready", "provider_collectors_not_ready"].includes(item.code));
  const visibleSetupItems = rawSetupItems.filter((item) => item.code !== "analytics_evidence_incomplete" || !sourceSetupPending);
  document.getElementById("insights-quality").innerHTML = `<div class="overview-status"><span class="coverage-pill ${measuredSourcesCurrent ? "covered" : "building"}">${measuredSourcesCurrent ? "Live data" : "Connecting data"}</span><div><strong>${number(summary.verified_platforms)} listening destinations tracked</strong><p>${measuredSourcesCurrent ? "All contributing analytics sources are current." : "Automatic collection is active; unavailable source details are never estimated."}</p></div></div><div><strong>Latest audience data</strong><p>${escapeHtml(quality.latest_period_end || "Automatic collection is starting")}</p></div><button id="refresh-podcast-reach" class="primary-button" type="button">Refresh now</button>`;
  const releaseChecks = Object.entries(release.checks || {});
  const setupLabels = {
    distribution_incomplete: ["Refresh platform availability", "We will recheck every known listing and podcast app."],
    public_sources_incomplete: ["Update public listings", "Run a fresh check of the RSS feed and public directories."],
    youtube_analytics_not_ready: ["Connect YouTube", "Authorize the channel owner once to unlock viewing and audience insights."],
    provider_collectors_not_ready: ["Finish Spotify and Apple setup", "The account owner must complete the local sign-in once."],
    analytics_evidence_incomplete: ["Refresh audience evidence", "Automatic collectors will retry the connected hosting, native, video, and website sources."],
    schema_outdated: ["Finish the data upgrade", "Restart the current release so the latest database upgrade can complete."],
  };
  const setupActions = visibleSetupItems.map((item) => ({code:item.code, ...(setupLabels[item.code] ? {title:setupLabels[item.code][0], detail:setupLabels[item.code][1]} : {title:"Complete data setup", detail:item.message})}));
  document.getElementById("release-readiness").innerHTML = `<div class="source-column setup-overview"><h3>${releaseReady ? "Everything is current" : "Finish setup"}<span>${releaseReady ? "Ready" : `${setupActions.length} remaining`}</span></h3><p>${releaseReady ? "All required sources are connected, refreshed, and contributing data." : "We will handle public checks automatically. Account connections remain owner-approved for security."}</p><button class="secondary-button" type="button" data-refresh-reach>Refresh what can be automated</button></div><div class="source-column"><h3>Next actions <span>${setupActions.length}</span></h3>${setupActions.length ? setupActions.map((item) => `<article class="source-row"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.detail)}</p></article>`).join("") : '<article class="source-row"><strong>No action needed</strong><p>Your reach data is current.</p></article>'}</div><div class="source-column"><h3>Source check <span>${releaseChecks.filter(([, item]) => item.status === "pass").length}/${releaseChecks.length}</span></h3>${releaseChecks.map(([key, item]) => `<article class="source-row"><div><strong>${escapeHtml(metricLabel(key).replace("Analytics Evidence", "Audience Data"))}</strong><span class="source-status ${item.status === "pass" ? "data_present" : "provider_access_required"}">${item.status === "pass" ? "Current" : "Needs setup"}</span></div></article>`).join("")}</div>`;
  const refreshReach = async (button) => {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Updating…";
    try {
      await connectorRequest("/api/podcast-reach/refresh", {method:"POST", body:"{}"});
      await load();
    } catch (error) {
      button.textContent = "Open setup to continue";
      button.title = error.message;
      button.disabled = false;
      return;
    }
    button.textContent = original;
  };
  document.querySelectorAll("#refresh-podcast-reach,[data-refresh-reach]").forEach((button) => button.addEventListener("click", () => refreshReach(button)));
  const global = summary.global_rollup || {};
  const reach = global.reach_range || {};
  const reachValue = reach.minimum == null ? "Not yet measurable" : reach.maximum == null ? `At least ${number(reach.minimum)}` : `${number(reach.minimum)}–${number(reach.maximum)}`;
  const totalChange = changeLabel(global.comparison?.total);
  const audioComponents = (global.components || []).filter((item) => item.key !== "youtube_views");
  const audioDetail = audioComponents.length
    ? audioComponents.map((item) => `${number(item.value)} ${String(item.label || "activity").toLowerCase()}`).join(" · ")
    : "Hosting data covers every RSS listening app";
  const activityDetail = global.measured_activity == null
    ? "Connect the hosting account and YouTube to calculate this"
    : `${global.comparison?.available ? totalChange.text : global.coverage === "complete" ? "Latest comparable window" : "Connected channels"} · through ${global.period_end}`;
  document.getElementById("insights-summary").innerHTML = [
    ["Podcast downloads & plays", number(global.audio_starts), audioDetail, "global"],
    ["All measured activity", number(global.measured_activity), activityDetail],
    ["Video views", number(global.video_views), summary.plays_period_end ? `YouTube window through ${summary.plays_period_end}` : "Connect YouTube to begin"],
    ["People reached", reachValue, reach.minimum == null ? "Awaiting compatible unique-audience reports" : `Bounded estimate through ${reach.period_end}`],
  ].map(([label,value,detail,className]) => `<article class="summary-card ${className || ""}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`).join("");
  const youtubeDevices = (payload.devices || []).filter((item) => item.provider === "youtube" || item.provider.startsWith("youtube:"));
  const youtubeDeviceTotal = youtubeDevices.reduce((total, item) => total + Number(item.value || 0), 0);
  const youtubeMobileValue = youtubeDevices.filter((item) => item.name === "Mobile").reduce((total, item) => total + Number(item.value || 0), 0);
  const youtubeMobileShare = youtubeDeviceTotal ? Math.round(youtubeMobileValue * 1000 / youtubeDeviceTotal) / 10 : null;
  const hasViewDuration = youtubeChannels.some((item) => item.metrics?.average_view_duration_seconds != null);
  const weightedDuration = hasViewDuration ? youtubeChannels.reduce((total, item) => total + Number(item.metrics?.average_view_duration_seconds || 0) * Number(item.metrics?.plays || 0), 0) / Math.max(youtubeMetricTotal("plays"), 1) : null;
  document.getElementById("reach-highlights").innerHTML = [
    ["Places to listen", `${number(summary.verified_platforms)} destinations`, `${number(summary.distribution_coverage_pct)}% of known destinations confirmed.`],
    ["How people watch", youtubeMobileShare == null ? "Connect YouTube for device mix" : `${youtubeMobileShare}% watch on mobile`, youtubeMobileShare == null ? "One connection unlocks mobile, TV, desktop, and tablet viewing." : `${number(youtubeMobileValue)} recent views came from mobile devices.`],
    ["How long they stay", hasViewDuration ? duration(weightedDuration) : "Watch-time detail unavailable", hasViewDuration ? "Average viewing time across connected channels." : "The connected source has not returned average viewing duration yet."],
  ].map(([label,value,detail]) => `<article class="highlight-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><p>${escapeHtml(detail)}</p></article>`).join("");
  renderOverallPerformance(payload.performance_trend || [], global);
  renderPlatformPerformance(global, payload.monthly_trends || {}, payload.listening_apps || []);
  renderDecisionIntelligence(payload.decision_intelligence || {});
  const coverage = payload.source_coverage || {}; const publicSources = coverage.public || []; const privateSources = coverage.private || [];
  renderConnections(payload.analytics_connectors || {});
  const automated = privateSources.filter((source) => source.connection_mode === "automated"); const limited = privateSources.filter((source) => source.connection_mode === "provider_limited");
  const sourceRow = (source) => { const metrics = source.metrics_present?.length ? source.metrics_present : source.metrics || []; const shown = metrics.slice(0, 5); const active = source.status === "data_present"; return `<article class="source-row"><div><strong>${escapeHtml(source.name)}</strong><span class="source-status ${active ? "data_present" : "provider_access_required"}">${active ? "Current" : "Connecting"}</span></div><small>${active ? `${Number(source.observation_count || 0)} data points · through ${escapeHtml(source.latest_period_end || "unknown")}` : "The automatic collector is waiting for owner-approved provider access."}</small><p>${source.metrics_present?.length ? "Available" : "Expected"}: ${shown.map(metricLabel).map(escapeHtml).join(", ")}${metrics.length > shown.length ? ` +${metrics.length - shown.length} more` : ""}</p></article>`; };
  document.getElementById("source-coverage").innerHTML = `<div class="source-column"><h3>Public availability <span>${Number(coverage.public_available || 0)}/${Number(coverage.public_expected || 0)}</span></h3>${publicSources.length ? publicSources.map((source) => `<article class="source-row"><div><strong>${escapeHtml(source.source_name)}</strong><span class="source-status ${source.status === "available" ? "data_present" : "provider_access_required"}">${source.status === "available" ? "Current" : "Rechecking"}</span></div><small>Last checked ${escapeHtml(source.checked_at || "not yet")}</small></article>`).join("") : empty("The first availability check will run automatically.")}</div><div class="source-column"><h3>Connected sources <span>${Number(coverage.automated_connected || 0)}/${Number(coverage.automated_expected || 0)}</span></h3>${automated.map(sourceRow).join("")}</div><div class="source-column"><h3>Owner-approved sources <span>${Number(coverage.provider_limited_count || 0)}</span></h3>${limited.map(sourceRow).join("")}</div>`;
  document.getElementById("platform-grid").innerHTML = (payload.platforms || []).map((platform) => {
    const status = platform.availability === "available" ? "Confirmed" : platform.distribution_mode === "expected_missing" ? "Not listed" : "Being checked";
    const mode = {direct_listing:"Official listing",direct_video:"Video channel",catalog_listing:"Podcast directory",rss_subscription:"Opens with RSS",expected_missing:"Optional destination"}[platform.distribution_mode] || "Podcast destination";
    const checked = platform.verified_on ? `Checked ${String(platform.verified_on).slice(0, 10)}` : "Automatic check scheduled";
    return `<a class="platform-card" href="${escapeHtml(safeUrl(platform.url))}" target="_blank" rel="noopener noreferrer"><span>${escapeHtml(mode)}</span><strong>${escapeHtml(platform.name)}</strong><small>${escapeHtml(status)} · ${escapeHtml(checked)}</small></a>`;
  }).join("");
  document.getElementById("provider-strength").innerHTML = providers.length ? providers.map((item) => `<article class="provider-row"><div><strong>${escapeHtml(providerLabel(item.provider))}</strong><span class="freshness ${escapeHtml(item.freshness)}">${item.freshness === "current" ? "Up to date" : "Refresh needed"}</span></div><p class="metric-pairs">${Object.entries(item.metrics || {}).map(([key,value]) => `<span>${escapeHtml(metricLabel(key))}<strong>${number(value)}</strong></span>`).join("")}</p><small>${escapeHtml(item.period_start)} – ${escapeHtml(item.period_end)}</small></article>`).join("") : empty("Connect a provider to see its performance here.");
  const audience = payload.audience_by_platform || [];
  document.getElementById("audience-platform").innerHTML = audience.length ? audience.map((item) => `<article class="provider-row"><div><strong>${escapeHtml(providerLabel(item.provider))}</strong><span>${number(item.value)}</span></div><p>${escapeHtml(item.metric.replaceAll("_", " "))}</p><small>Through ${escapeHtml(item.period_end)}</small></article>`).join("") : empty("Automatic collectors have not received compatible unique-listener or follower counters yet.");
  renderBars(payload.devices || [], document.getElementById("device-breakdown"));
  renderBars(payload.countries || [], document.getElementById("country-breakdown"));
  renderBars(payload.cities || [], document.getElementById("city-breakdown"));
  renderBars(payload.demographics || [], document.getElementById("demographic-breakdown"));
  renderBars(payload.traffic_sources || [], document.getElementById("traffic-source-breakdown"));
  renderBars(payload.listening_apps || [], document.getElementById("listening-app-breakdown"));
  renderTopPlatformContent(payload.top_platform_content || []);
  renderMonthlyTrends(payload.monthly_trends || {});
  document.getElementById("metric-definitions").innerHTML = Object.entries(payload.definitions || {}).map(([key,value]) => `<article><strong>${escapeHtml(key.replaceAll("_", " "))}</strong><p>${escapeHtml(value)}</p></article>`).join("") + `<article><strong>Reliability guardrails</strong><p>${(quality.limitations || []).map(escapeHtml).join(" ")}</p></article>`;
}

async function load() {
  render(await connectorRequest("/api/podcast-insights"));
}
document.getElementById("insights-refresh")?.addEventListener("click", () => load().catch((error) => { document.getElementById("insights-quality").textContent = error.message; }));
document.getElementById("growth-experiment-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const message = document.getElementById("growth-experiment-message");
  const button = form.querySelector("button[type='submit']");
  button.disabled = true;
  message.textContent = "Registering experiment…";
  message.className = "message pending";
  try {
    const result = await connectorRequest("/api/growth-intelligence/experiments", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form).entries())) });
    message.textContent = `Registered ${result.name} as a draft experiment.`;
    message.className = "message success";
    form.reset();
  } catch (error) {
    message.textContent = error.message;
    message.className = "message error";
  } finally {
    button.disabled = false;
  }
});
window.addEventListener("growth-intelligence-changed", () => load().catch(() => {}));
load()
  .catch((error) => { document.getElementById("insights-quality").textContent = error.message; })
  .finally(() => { document.body.classList.remove("page-loading"); });
