const escapeHtml = window.PerformanceUtils?.escapeHtml || ((value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[character]));
const number = (value) => value == null ? "—" : new Intl.NumberFormat().format(Number(value));
const percentage = (value) => value == null ? "—" : new Intl.NumberFormat(undefined, {maximumFractionDigits:1}).format(Number(value));
const safeUrl = (value) => { try { const parsed = new URL(String(value)); return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "#"; } catch { return "#"; } };
const empty = (message) => `<div class="insights-empty"><strong>Collecting automatically</strong><p>${escapeHtml(message)}</p></div>`;
const csrfToken = () => decodeURIComponent((document.cookie.match(/(?:^|;\s*)dashboard_csrf=([^;]+)/) || [])[1] || "");
const metricLabel = (value) => String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
const duration = (seconds) => seconds == null ? "Unavailable" : `${Math.floor(Number(seconds) / 60)}m ${Math.round(Number(seconds) % 60)}s`;
let providerLabels = {};
let trendRange = 24;
let audioRange = "all";
let latestPayload = null;
const providerLabel = (provider) => providerLabels[provider] || metricLabel(provider);
const formatDate = (value) => value ? new Intl.DateTimeFormat(undefined, {day:"numeric",month:"short",year:"numeric"}).format(new Date(`${value}T00:00:00`)) : "—";
const formatTimestamp = (value) => value ? new Intl.DateTimeFormat(undefined, {day:"numeric",month:"short",hour:"2-digit",minute:"2-digit"}).format(new Date(value)) : "Not checked yet";

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

function selectedAudioRows(rows) {
  if (!rows.length || audioRange === "all") return rows;
  const days = {"7d":7,"30d":30,"90d":90,"12m":365}[audioRange] || 30;
  const latest = new Date(`${rows.at(-1).period}T00:00:00Z`);
  latest.setDate(latest.getDate() - days + 1);
  const cutoff = latest.toISOString().slice(0, 10);
  return rows.filter((row) => row.period >= cutoff);
}

function audioTotals(rows) {
  const downloads = rows.reduce((total, row) => total + Number(row.downloads || 0), 0);
  const plays = rows.reduce((total, row) => total + Number(row.plays || 0), 0);
  return {downloads, plays, total:downloads + plays};
}

function audioView(rows) {
  const selected = selectedAudioRows(rows);
  const totals = audioTotals(selected);
  const start = selected[0]?.period || null;
  const end = selected.at(-1)?.period || null;
  let comparison = null;
  if (audioRange !== "all" && selected.length && start) {
    const priorEnd = new Date(`${start}T00:00:00Z`);
    priorEnd.setDate(priorEnd.getDate() - 1);
    const priorStart = new Date(priorEnd);
    priorStart.setDate(priorStart.getDate() - selected.length + 1);
    const previous = rows.filter((row) => row.period >= priorStart.toISOString().slice(0, 10) && row.period <= priorEnd.toISOString().slice(0, 10));
    const previousTotals = audioTotals(previous);
    comparison = previousTotals.total ? {
      delta: totals.total - previousTotals.total,
      delta_pct: Math.round((totals.total - previousTotals.total) * 1000 / previousTotals.total) / 10,
      previous_start: previous[0]?.period,
      previous_end: previous.at(-1)?.period,
    } : null;
  }
  return {rows:selected, ...totals, start, end, comparison};
}

function audioChartRows(rows) {
  if (audioRange === "7d" || audioRange === "30d" || audioRange === "90d") {
    return rows.map((row) => ({...row,total:Number(row.downloads || 0) + Number(row.plays || 0)}));
  }
  const months = new Map();
  rows.forEach((row) => {
    const period = row.period.slice(0, 7);
    const current = months.get(period) || {period,downloads:0,plays:0,total:0};
    current.downloads += Number(row.downloads || 0);
    current.plays += Number(row.plays || 0);
    current.total = current.downloads + current.plays;
    months.set(period, current);
  });
  return [...months.values()];
}

function renderOverallPerformance(daily) {
  const target = document.getElementById("overall-performance-trend");
  const view = audioView(daily || []);
  const change = changeLabel(view.comparison);
  const periodText = view.start && view.end ? `${formatDate(view.start)} – ${formatDate(view.end)}` : "Waiting for lifetime hosting history";
  target.innerHTML = `${view.comparison ? `<div class="performance-change ${change.className}"><strong>${escapeHtml(change.text)}</strong><span>${number(view.comparison.delta)} podcast activity change · previous period ${formatDate(view.comparison.previous_start)} – ${formatDate(view.comparison.previous_end)}</span></div>` : `<div class="performance-change neutral"><strong>${audioRange === "all" ? "Lifetime history" : "No prior comparable period"}</strong><span>${escapeHtml(periodText)}</span></div>`}${trendChart("Podcast downloads and plays", audioChartRows(view.rows), [{key:"total",label:"Downloads & plays",className:"series-total"},{key:"downloads",label:"Other podcast apps",className:"series-primary"},{key:"plays",label:"Spotify plays",className:"series-secondary"}], {range:0,className:"overall-trend-card",periodLabel:audioRange === "7d" || audioRange === "30d" || audioRange === "90d" ? "Date" : "Month",emptyMessage:"Lifetime hosting history is being collected automatically."})}`;
  return view;
}

function renderPlatformPerformance(global, monthly, listeningApps, audio) {
  const target = document.getElementById("platform-performance");
  const components = Object.fromEntries((global.components || []).map((item) => [item.key, item]));
  const comparison = global.comparison || {};
  const componentStats = comparison.components || {};
  const cards = [
    ["Podcast apps (RSS)", audio.downloads, "Downloads delivered across Apple Podcasts and every other open podcast app.", audio.total ? `${percentage(audio.downloads * 100 / audio.total)}% of selected podcast activity` : "Awaiting data", audio.start && audio.end ? `${formatDate(audio.start)} – ${formatDate(audio.end)}` : ""],
    ["Spotify", audio.plays, "Native Spotify play starts in the selected range.", audio.total ? `${percentage(audio.plays * 100 / audio.total)}% of selected podcast activity` : "Awaiting data", audio.start && audio.end ? `${formatDate(audio.start)} – ${formatDate(audio.end)}` : ""],
    ["YouTube", components.youtube_views?.value, "Video and podcast views from connected channels.", "Latest comparable window", changeLabel(componentStats.youtube_views).text],
  ].map(([label,value,description,meta,detail]) => `<article class="performance-platform-card"><div><span>${escapeHtml(label)}</span><strong>${number(value)}</strong></div><p>${escapeHtml(description)}</p><div class="platform-card-meta"><span>${escapeHtml(meta)}</span><span class="metric-change neutral">${escapeHtml(detail)}</span></div></article>`);
  const appleRows = monthly.apple_podcasts || [];
  const appleCurrent = appleRows.at(-1); const applePrevious = appleRows.at(-2);
  const appleStat = appleCurrent && applePrevious ? {delta_pct:applePrevious.plays ? Math.round((Number(appleCurrent.plays) - Number(applePrevious.plays)) * 1000 / Number(applePrevious.plays)) / 10 : null} : null;
  const appleChange = changeLabel(appleStat);
  cards.push(`<article class="performance-platform-card diagnostic"><div><span>Apple Podcasts engagement</span><strong>${number(appleCurrent?.plays)}</strong></div><p>Apple-native plays for ${escapeHtml(appleCurrent?.period || "the latest reported month")}; shown separately to prevent double-counting RSS delivery.</p><div class="platform-card-meta"><span>${number(appleCurrent?.listeners)} listeners</span><span class="metric-change ${appleChange.className}">${escapeHtml(appleChange.text)}</span></div></article>`);
  target.innerHTML = cards.join("");

  const appTarget = document.getElementById("listening-app-summary");
  const apps = (listeningApps || []).slice(0, 8);
  appTarget.innerHTML = apps.length ? `<div class="listening-app-heading"><h3>Lifetime podcast-app mix</h3><p>Host-reported delivery already included in the selected podcast total.</p></div><div class="listening-app-chips">${apps.map((item) => `<span><strong>${escapeHtml(item.name)}</strong>${item.is_percentage ? `${percentage(item.value)}%` : `${number(item.value)} · ${percentage(item.share_pct)}%`}</span>`).join("")}</div>` : `<p class="platform-coverage-note">The podcast total covers every open app. The per-app mix will appear when the hosting source provides it.</p>`;
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
    const reauth = enabled && connection.status === "reauth_required";
    const waiting = enabled && !current && !reauth;
    const statusLabel = current ? "Current" : reauth ? "Sign-in expired" : waiting ? "Waiting for Mac" : "Set up";
    const command = `python3 -m guest_database_manager.local_analytics_collector login ${provider}`;
    const guidance = current ? "Reports are arriving automatically." : reauth ? "Run the sign-in command once on the account owner's Mac." : enabled ? "The local collector is enabled; run the sign-in command if it has not synced yet." : "Enable the collector, then complete the one-time sign-in on the account owner's Mac.";
    return `<article class="connection-card"><header><div><strong>${label}</strong><p>The secure sign-in stays on the account owner's computer.</p></div><span class="connection-status ${current ? "connected" : "disconnected"}">${statusLabel}</span></header><p>${guidance}</p><small>Last update: ${escapeHtml(connection.last_success_at || "No successful update yet")}</small><div class="connection-actions"><button class="${enabled ? "ghost-button" : "secondary-button"}" data-local-provider="${provider}" data-local-enabled="${enabled ? "false" : "true"}" type="button" ${local.configured ? "" : "disabled"}>${enabled ? "Pause connection" : "Enable collector"}</button>${current ? "" : `<button class="secondary-button" data-copy-command="${escapeHtml(command)}" type="button">Copy sign-in command</button>`}</div></article>`;
  }).join("");
  target.innerHTML = `${cards || '<div class="insights-empty"><strong>Connect YouTube</strong><p>Authorize the channel owner once to unlock viewing, audience, and discovery insights.</p></div>'}<article class="connection-card add-connection-card"><header><div><strong>Add a YouTube channel</strong><p>Each owner approves access independently.</p></div></header><button id="connect-google" class="primary-button" type="button" ${google.oauth_configured ? "" : "disabled"}>Connect YouTube</button></article><div class="connection-group-heading"><strong>Podcast analytics</strong><p>Hosting and native-platform reports refresh automatically; private sign-ins never leave the account owner's computer.</p></div>${localCards}`;
  document.getElementById("connect-google")?.addEventListener("click", async () => { try { const result = await connectorRequest("/api/analytics-connectors/google/connect", {method:"POST", body:"{}"}); window.location.assign(result.authorization_url); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } });
  target.querySelectorAll("[data-sync-google]").forEach((button) => button.addEventListener("click", async () => { try { await connectorRequest("/api/analytics-connectors/google/sync", {method:"POST", body:JSON.stringify({connection_id:Number(button.dataset.syncGoogle)})}); await load(); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } }));
  target.querySelectorAll("[data-disconnect-google]").forEach((button) => button.addEventListener("click", async () => { if (!window.confirm("Disconnect this channel and delete only its retained refresh token?")) return; try { await connectorRequest(`/api/analytics-connectors/google?connection_id=${encodeURIComponent(button.dataset.disconnectGoogle)}`, {method:"DELETE"}); await load(); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } }));
  target.querySelectorAll("[data-local-provider]").forEach((button) => button.addEventListener("click", async () => { try { await connectorRequest("/api/analytics-connectors/local/configure", {method:"POST", body:JSON.stringify({provider:button.dataset.localProvider, enabled:button.dataset.localEnabled === "true"})}); await load(); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } }));
  target.querySelectorAll("[data-copy-command]").forEach((button) => button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.copyCommand);
      button.textContent = "Copied — run in Terminal";
    } catch (_error) {
      button.textContent = "Copy unavailable — use the command shown below";
      const command = document.createElement("code");
      command.textContent = button.dataset.copyCommand;
      button.parentElement.append(command);
    }
  }));
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
    return `<details class="dimension-group" ${providerIndex === 0 ? "open" : ""}><summary><strong>${escapeHtml(heading)}</strong><span>${all.length} measured ${all.length === 1 ? "segment" : "segments"}</span></summary><div class="insight-bars">${group.map((item) => `<div class="insight-bar"><div><strong>${escapeHtml(item.name)}</strong><span>${item.is_percentage ? `${percentage(item.value)}%` : `${number(item.value)}${item.share_pct == null ? "" : ` · ${percentage(item.share_pct)}%`}`}</span></div><div class="insight-bar-track"><span style="width:${Math.max(2, Number(item.value || 0) * 100 / max)}%"></span></div><small>${escapeHtml(item.measure === "plays" ? "All-time plays" : `Through ${item.period_end || "unknown"}`)}</small></div>`).join("")}${remainder > 0 ? `<p class="dimension-note">Top 8 shown · ${remainder} additional ${remainder === 1 ? "entry" : "entries"} included in percentage totals.</p>` : ""}</div></details>`;
  }).join("");
}

function renderEpisodePerformance(episodes, platformItems) {
  const target = document.getElementById("episode-performance");
  const rows = episodes.length ? episodes : platformItems.map((item) => ({
    title:item.title || item.platform_content_id,
    activity:Number(item.metrics?.video_views || 0),
    metrics:{plays:item.metrics?.video_views,watch_time_hours:item.metrics?.video_watch_time_hours,average_view_duration_seconds:item.metrics?.video_average_view_duration_seconds},
    providers:[item.provider],period_end:item.period_end,freshness:"current",
  }));
  if (!rows.length) { target.innerHTML = empty("Connected sources have not returned episode-level performance yet."); return; }
  target.innerHTML = `<div class="episode-table-wrap"><table class="episode-table"><thead><tr><th>Episode</th><th>Activity</th><th>Depth</th><th>Coverage</th></tr></thead><tbody>${rows.slice(0, 12).map((item) => {
    const metrics = item.metrics || {};
    const depth = metrics.consumption_depth_pct != null ? `${percentage(metrics.consumption_depth_pct)}% consumed` : metrics.average_view_duration_seconds != null ? duration(metrics.average_view_duration_seconds) : "Not provided";
    const providerText = (item.providers || []).map(providerLabel).join(", ");
    return `<tr><td><strong>${escapeHtml(item.title)}</strong><small>Through ${escapeHtml(item.period_end || "unknown")}</small></td><td><strong>${number(item.activity)}</strong><small>downloads, plays or views</small></td><td>${escapeHtml(depth)}</td><td><span class="freshness ${escapeHtml(item.freshness || "current")}">${escapeHtml(item.freshness === "stale" ? "Refresh needed" : "Current")}</span><small>${escapeHtml(providerText)}</small></td></tr>`;
  }).join("")}</tbody></table></div>`;
}

function render(payload) {
  latestPayload = payload;
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
  const setupActions = visibleSetupItems.filter((item) => {
    const check = release.checks?.[item.code === "provider_collectors_not_ready" ? "provider_collectors" : item.code === "youtube_analytics_not_ready" ? "youtube_analytics" : ""];
    return item.code === "schema_outdated" || check?.resolution === "owner_action";
  }).map((item) => {
    if (item.code === "provider_collectors_not_ready") {
      const missing = release.checks?.provider_collectors?.not_connected || [];
      return {code:item.code, title:`Reconnect ${missing.map(providerLabel).join(" and ") || "private analytics"}`, detail:"The saved provider session expired. Sign in again only for the named provider."};
    }
    return {code:item.code, ...(setupLabels[item.code] ? {title:setupLabels[item.code][0], detail:setupLabels[item.code][1]} : {title:"Complete data setup", detail:item.message})};
  });
  const failedAutomatic = releaseChecks.filter(([, item]) => item.status !== "pass" && item.resolution !== "owner_action");
  const healthRows = releaseChecks.filter(([, item]) => item.status === "pass").map(([key]) => `<span>${escapeHtml(metricLabel(key).replace("Analytics Evidence", "Audience data"))}</span>`).join("");
  document.getElementById("release-readiness").innerHTML = `<div class="source-column setup-overview"><div class="health-heading"><div><span class="eyebrow">Connection health</span><h3>${setupActions.length ? `${setupActions.length} action needed` : "Core analytics connected"}</h3></div><span class="source-status ${setupActions.length ? "provider_access_required" : "data_present"}">${releaseChecks.filter(([, item]) => item.status === "pass").length}/${releaseChecks.length} checks</span></div><div class="health-list">${healthRows || "No completed checks yet"}</div><button class="secondary-button" type="button" data-refresh-reach>Check now</button></div><div class="source-column"><h3>${setupActions.length ? "Your action" : "No action needed"}</h3>${setupActions.length ? setupActions.map((item) => `<article class="source-row"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.detail)}</p></article>`).join("") : '<p class="source-note">Connected analytics refresh automatically.</p>'}${failedAutomatic.length ? `<details class="background-checks"><summary>${failedAutomatic.length} background check${failedAutomatic.length === 1 ? "" : "s"} could not complete</summary>${failedAutomatic.map(([key]) => `<p>${escapeHtml(metricLabel(key))} will retry during the next scheduled refresh.</p>`).join("")}</details>` : ""}</div>`;
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
  const topline = summary.topline || {};
  const dailyAudio = payload.daily_trends?.spotify || [];
  const audio = audioView(dailyAudio);
  const lifetime = summary.spotify_lifetime || {};
  const lifetimeRange = lifetime.period_start && lifetime.period_end ? `${formatDate(lifetime.period_start)} – ${formatDate(lifetime.period_end)}` : "Automatic lifetime collection is starting";
  const growth = topline.growth_pct;
  const growthValue = growth == null ? "—" : `${Number(growth) > 0 ? "+" : ""}${percentage(growth)}%`;
  const relationshipBreakdown = topline.audience_relationship_breakdown || {};
  const relationshipDetail = [
    relationshipBreakdown.subscribers ? `${number(relationshipBreakdown.subscribers)} subscriptions` : "",
    relationshipBreakdown.followers ? `${number(relationshipBreakdown.followers)} followers` : "",
  ].filter(Boolean).join(" · ");
  const periodAudience = (topline.audience_relationship_by_platform || [])
    .filter((item) => ["unique_listeners", "unique_viewers", "listeners"].includes(item.metric))
    .map((item) => `${providerLabel(item.provider)}: ${number(item.value)} ${metricLabel(item.metric).toLowerCase()} in its latest reported period through ${item.period_end || "unknown"}`)
    .join(" · ");
  document.getElementById("insights-summary").innerHTML = [
    ["Downloads & plays", number(topline.downloads_plays), `${lifetimeRange} · podcast and lifetime video activity`, "global"],
    ["Listening & watch hours", topline.listening_watch_hours == null ? "—" : percentage(topline.listening_watch_hours), topline.hours_coverage_note || "Awaiting duration data"],
    ["Countries reached", number(topline.countries_reached), "Distinct countries across connected audience reports"],
    ["Platforms available", number(topline.platforms_available), "Confirmed listening and watching destinations"],
    ["Audience relationships", number(topline.audience_relationships), `${relationshipDetail || "Follower and subscription counters are still syncing"}. Followers and subscribers chose an ongoing connection.${periodAudience ? ` Recent listeners measure period activity and are not added: ${periodAudience}` : ""}`],
    ["Growth trend", growthValue, topline.growth_basis || "Latest comparable podcast periods"],
  ].map(([label,value,detail,className]) => `<article class="summary-card ${className || ""}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`).join("");
  const attention = payload.attention_items || [];
  document.getElementById("insight-alerts").innerHTML = attention.length ? `<div class="attention-heading"><span class="eyebrow">Changes worth attention</span><strong>${attention.length}</strong></div>${attention.map((item) => `<article class="attention-item ${escapeHtml(item.severity || "neutral")}"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.detail)}</span></article>`).join("")}` : `<div class="attention-heading"><span class="eyebrow">Changes worth attention</span></div><article class="attention-item positive"><strong>No unusual movement detected</strong><span>Connected sources are within their recent ranges.</span></article>`;
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
  renderOverallPerformance(dailyAudio);
  renderPlatformPerformance(global, payload.monthly_trends || {}, payload.listening_apps || [], audio);
  renderDecisionIntelligence(payload.decision_intelligence || {});
  const coverage = payload.source_coverage || {}; const publicSources = coverage.public || []; const privateSources = coverage.private || [];
  renderConnections(payload.analytics_connectors || {});
  const automated = privateSources.filter((source) => source.connection_mode === "automated"); const limited = privateSources.filter((source) => source.connection_mode === "provider_limited");
  const sourceRow = (source) => { const metrics = source.metrics_present?.length ? source.metrics_present : source.metrics || []; const shown = metrics.slice(0, 5); const active = source.status === "data_present"; return `<article class="source-row"><div><strong>${escapeHtml(source.name)}</strong><span class="source-status ${active ? "data_present" : "provider_access_required"}">${active ? "Current" : "Connecting"}</span></div><small>${active ? `${Number(source.observation_count || 0)} data points · through ${escapeHtml(source.latest_period_end || "unknown")}` : "The automatic collector is waiting for owner-approved provider access."}</small><p>${source.metrics_present?.length ? "Available" : "Expected"}: ${shown.map(metricLabel).map(escapeHtml).join(", ")}${metrics.length > shown.length ? ` +${metrics.length - shown.length} more` : ""}</p></article>`; };
  document.getElementById("source-coverage").innerHTML = `<div class="source-column"><h3>Public availability <span>${Number(coverage.public_available || 0)}/${Number(coverage.public_expected || 0)}</span></h3>${publicSources.length ? publicSources.map((source) => { const retrying = source.status === "retrying"; const available = source.status === "available"; return `<article class="source-row"><div><strong>${escapeHtml(source.source_name)}</strong><span class="source-status ${available ? "data_present" : retrying ? "refreshing" : "unavailable"}">${available ? "Verified" : retrying ? "Verified · retrying check" : "Temporarily unavailable"}</span></div><small>${escapeHtml(retrying && source.last_success_at ? `Verified ${formatTimestamp(source.last_success_at)} · retry attempted ${formatTimestamp(source.checked_at)}` : formatTimestamp(source.checked_at))}</small></article>`; }).join("") : empty("The first availability check will run automatically.")}</div><div class="source-column"><h3>Connected sources <span>${Number(coverage.automated_connected || 0)}/${Number(coverage.automated_expected || 0)}</span></h3>${automated.map(sourceRow).join("")}</div><div class="source-column"><h3>Private analytics <span>${limited.filter((source) => source.status === "data_present").length}/${limited.length}</span></h3>${limited.map(sourceRow).join("")}</div>`;
  document.getElementById("platform-grid").innerHTML = (payload.platforms || []).map((platform) => {
    const status = platform.availability === "available" ? "Confirmed" : platform.distribution_mode === "expected_missing" ? "Not listed" : "Being checked";
    const mode = {direct_listing:"Official listing",direct_video:"Video channel",catalog_listing:"Podcast directory",rss_subscription:"Opens with RSS",expected_missing:"Optional destination"}[platform.distribution_mode] || "Podcast destination";
    const checked = platform.verified_on ? `Checked ${String(platform.verified_on).slice(0, 10)}` : "Automatic check scheduled";
    return `<a class="platform-card" href="${escapeHtml(safeUrl(platform.url))}" target="_blank" rel="noopener noreferrer"><span>${escapeHtml(mode)}</span><strong>${escapeHtml(platform.name)}</strong><small>${escapeHtml(status)} · ${escapeHtml(checked)}</small></a>`;
  }).join("");
  document.getElementById("provider-strength").innerHTML = providers.length ? providers.map((item) => `<article class="provider-row"><div><strong>${escapeHtml(providerLabel(item.provider))}</strong><span class="freshness ${escapeHtml(item.freshness)}">${item.freshness === "current" ? "Up to date" : "Refresh needed"}</span></div><p class="metric-pairs">${Object.entries(item.metrics || {}).map(([key,value]) => `<span>${escapeHtml(metricLabel(key))}<strong>${number(value)}</strong></span>`).join("")}</p><small>${escapeHtml(item.period_start)} – ${escapeHtml(item.period_end)}</small></article>`).join("") : empty("Connect a provider to see its performance here.");
  const audience = payload.audience_by_platform || [];
  const audienceExplanation = `<p class="section-context"><strong>Why these numbers differ:</strong> followers and subscribers are people who opted into an ongoing relationship. Listeners are people who played the show during the provider's stated reporting period; they may not follow, can return in later periods, and cannot be summed across platforms.</p>`;
  document.getElementById("audience-platform").innerHTML = audienceExplanation + (audience.length ? audience.map((item) => `<article class="provider-row"><div><strong>${escapeHtml(providerLabel(item.provider))}</strong><span>${number(item.value)}</span></div><p>${escapeHtml(metricLabel(item.metric))}</p><small>${["unique_listeners", "new_listeners", "returning_listeners", "unique_viewers", "listeners"].includes(item.metric) ? "Latest reported period through" : "Current counter through"} ${escapeHtml(item.period_end)}</small></article>`).join("") : empty("Automatic collectors have not received compatible unique-listener or follower counters yet."));
  renderBars(payload.devices || [], document.getElementById("device-breakdown"));
  renderBars(payload.countries || [], document.getElementById("country-breakdown"));
  renderBars(payload.cities || [], document.getElementById("city-breakdown"));
  renderBars(payload.demographics || [], document.getElementById("demographic-breakdown"));
  renderBars(payload.traffic_sources || [], document.getElementById("traffic-source-breakdown"));
  renderBars(payload.listening_apps || [], document.getElementById("listening-app-breakdown"));
  renderEpisodePerformance(payload.episode_performance || [], payload.top_platform_content || []);
  renderMonthlyTrends(payload.monthly_trends || {});
  const coverageItems = payload.measurement_coverage || [];
  document.getElementById("measurement-coverage").innerHTML = coverageItems.length ? `<div class="coverage-heading"><div><span class="eyebrow">Measurement coverage</span><h3>${coverageItems.filter((item) => item.available).length}/${coverageItems.length} insight groups available</h3></div><p>Unavailable provider metrics remain blank—not zero.</p></div><div class="coverage-grid">${coverageItems.map((item) => `<article><span class="coverage-dot ${item.available ? "available" : "missing"}"></span><div><strong>${escapeHtml(item.label)}</strong><small>${item.available ? escapeHtml((item.providers || []).map(providerLabel).join(", ") || "Connected source") : "Not exposed by connected sources"}</small></div></article>`).join("")}</div>` : "";
  document.getElementById("metric-definitions").innerHTML = Object.entries(payload.definitions || {}).map(([key,value]) => `<article><strong>${escapeHtml(key.replaceAll("_", " "))}</strong><p>${escapeHtml(value)}</p></article>`).join("") + `<article><strong>Reliability guardrails</strong><p>${(quality.limitations || []).map(escapeHtml).join(" ")}</p></article>`;
  document.querySelectorAll("[data-audio-range]").forEach((button) => {
    button.classList.toggle("active", button.dataset.audioRange === audioRange);
    button.setAttribute("aria-pressed", button.dataset.audioRange === audioRange ? "true" : "false");
    button.onclick = () => {
      audioRange = button.dataset.audioRange || "all";
      if (latestPayload) render(latestPayload);
    };
  });
}

async function load() {
  render(await connectorRequest("/api/podcast-insights"));
}
document.getElementById("insights-refresh")?.addEventListener("click", () => load().catch((error) => { document.getElementById("insights-quality").textContent = error.message; }));
window.addEventListener("growth-intelligence-changed", () => load().catch(() => {}));
load()
  .catch((error) => { document.getElementById("insights-quality").textContent = error.message; })
  .finally(() => { document.body.classList.remove("page-loading"); });
