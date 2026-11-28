const escapeHtml = window.PerformanceUtils?.escapeHtml || ((value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[character]));
const number = (value) => value == null ? "—" : new Intl.NumberFormat().format(Number(value));
const percentage = (value) => value == null ? "—" : new Intl.NumberFormat(undefined, {maximumFractionDigits:1}).format(Number(value));
const safeUrl = (value) => { try { const parsed = new URL(String(value)); return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "#"; } catch { return "#"; } };
const empty = (message) => `<div class="insights-empty"><strong>Collecting automatically</strong><p>${escapeHtml(message)}</p></div>`;
const csrfToken = () => decodeURIComponent((document.cookie.match(/(?:^|;\s*)dashboard_csrf=([^;]+)/) || [])[1] || "");
const metricLabel = (value) => String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
const freshnessLabel = (value) => ({current:"Current",aging:"Aging",stale:"Refresh needed"})[value] || "Unknown";
const duration = (seconds) => seconds == null ? "Unavailable" : `${Math.floor(Number(seconds) / 60)}m ${Math.round(Number(seconds) % 60)}s`;
let providerLabels = {};
let trendRange = 24;
let audioRange = "all";
let latestPayload = null;
const providerLabel = (provider) => providerLabels[provider] || metricLabel(provider);
const formatDate = (value) => value ? new Intl.DateTimeFormat(undefined, {day:"numeric",month:"short",year:"numeric"}).format(new Date(`${value}T00:00:00`)) : "—";
const formatTimestamp = (value) => value ? new Intl.DateTimeFormat(undefined, {day:"numeric",month:"short",hour:"2-digit",minute:"2-digit"}).format(new Date(value)) : "Not checked yet";

function linePath(values, xScale, yScale) {
  if (!values.length) return "";
  return values.map((value, index) => {
    const x = xScale(index);
    const y = yScale(Number(value || 0));
    return `${index ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

const compactNumber = (value) => new Intl.NumberFormat(undefined, {notation:"compact",maximumFractionDigits:1}).format(Number(value || 0));
const chartPeriodLabel = (value) => {
  if (!value) return "—";
  const text = String(value);
  const date = new Date(text.length === 7 ? `${text}-01T00:00:00Z` : `${text}T00:00:00Z`);
  return new Intl.DateTimeFormat(undefined, text.length === 7 ? {month:"short",year:"numeric",timeZone:"UTC"} : {day:"numeric",month:"short",timeZone:"UTC"}).format(date);
};

function trendChart(title, rows, series, options = {}) {
  const range = options.range ?? trendRange;
  const selected = range === 0 ? rows : rows.slice(-range);
  if (!selected.length) return `<article class="trend-card"><h3>${escapeHtml(title)}</h3>${empty(options.emptyMessage || "No comparable history is available yet.")}</article>`;
  const width = 720; const height = 210; const left = 58; const right = 14; const top = 12; const bottom = 38;
  const plotWidth = width - left - right; const plotHeight = height - top - bottom;
  const rawMax = Math.max(...selected.flatMap((row) => series.map((item) => Number(row[item.key] || 0))), 1);
  const magnitude = 10 ** Math.floor(Math.log10(rawMax));
  const niceMax = Math.ceil(rawMax / magnitude * 2) / 2 * magnitude;
  const xScale = (index) => selected.length === 1 ? left + plotWidth / 2 : left + index * plotWidth / (selected.length - 1);
  const yScale = (value) => top + plotHeight - (value / Math.max(niceMax, 1)) * plotHeight;
  const first = selected[0].period; const last = selected.at(-1).period;
  const paths = series.map((item) => `<path class="trend-line ${item.className}" d="${linePath(selected.map((row) => row[item.key]), xScale, yScale)}"></path>`).join("");
  const yAxis = Array.from({length:5}, (_, index) => niceMax * index / 4).map((value) => { const y = yScale(value); return `<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" class="chart-gridline"></line><text x="${left - 10}" y="${y + 4}" text-anchor="end">${escapeHtml(compactNumber(value))}</text>`; }).join("");
  const xTickCount = Math.min(5, selected.length);
  const xIndexes = [...new Set(Array.from({length:xTickCount}, (_, index) => Math.round(index * (selected.length - 1) / Math.max(xTickCount - 1, 1))))];
  const xAxis = xIndexes.map((index) => `<line x1="${xScale(index)}" y1="${height - bottom}" x2="${xScale(index)}" y2="${height - bottom + 5}" class="chart-axis"></line><text x="${xScale(index)}" y="${height - 13}" text-anchor="middle">${escapeHtml(chartPeriodLabel(selected[index].period))}</text>`).join("");
  const points = selected.flatMap((row, index) => series.map((item) => `<circle class="trend-point ${item.className}" data-point-index="${index}" cx="${xScale(index)}" cy="${yScale(Number(row[item.key] || 0))}" r="4"></circle>`)).join("");
  const hitWidth = selected.length === 1 ? plotWidth : Math.max(12, plotWidth / (selected.length - 1));
  const hitTargets = selected.map((row, index) => {
    const values = series.map((item) => ({label:item.label,value:Number(row[item.key] || 0)}));
    const spoken = values.map((item) => `${item.label} ${number(item.value)}`).join(", ");
    const x = Math.max(left, xScale(index) - hitWidth / 2);
    return `<rect class="trend-hit-target" data-trend-index="${index}" data-period="${escapeHtml(String(row.period))}" data-values="${escapeHtml(JSON.stringify(values))}" x="${x}" y="${top}" width="${Math.min(hitWidth, width - right - x)}" height="${plotHeight}" tabindex="0" role="button" aria-label="${escapeHtml(`${chartPeriodLabel(row.period)}: ${spoken}`)}"></rect>`;
  }).join("");
  const latest = selected.at(-1);
  const tableRows = selected.map((row) => `<tr><td>${escapeHtml(row.period)}</td>${series.map((item) => `<td>${number(row[item.key])}</td>`).join("")}</tr>`).join("");
  return `<article class="trend-card ${options.className || ""}"><div class="trend-card-heading"><div><h3>${escapeHtml(title)}</h3><p>${series.map((item) => `${escapeHtml(item.label)}: <strong>${number(latest[item.key])}</strong>`).join(" · ")} through ${escapeHtml(last)}</p></div><div class="trend-legend">${series.map((item) => `<span class="${item.className}">${escapeHtml(item.label)}</span>`).join("")}</div></div><div class="chart-interactive"><svg class="line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(title)} trend from ${escapeHtml(first)} to ${escapeHtml(last)}"><text class="axis-title" x="14" y="${top + plotHeight / 2}" text-anchor="middle" transform="rotate(-90 14 ${top + plotHeight / 2})">${escapeHtml(options.yAxisLabel || "Count")}</text>${yAxis}<line x1="${left}" y1="${top}" x2="${left}" y2="${height - bottom}" class="chart-axis"></line><line x1="${left}" y1="${height - bottom}" x2="${width - right}" y2="${height - bottom}" class="chart-axis"></line>${xAxis}${paths}${points}${hitTargets}</svg><div class="trend-tooltip" role="status" aria-live="polite" hidden></div></div><details class="trend-data"><summary>View exact values</summary><div class="trend-table-wrap"><table><thead><tr><th>${escapeHtml(options.periodLabel || "Period")}</th>${series.map((item) => `<th>${escapeHtml(item.label)}</th>`).join("")}</tr></thead><tbody>${tableRows}</tbody></table></div></details></article>`;
}

function attachTrendInteractions(root) {
  root.querySelectorAll(".chart-interactive").forEach((chart) => {
    const tooltip = chart.querySelector(".trend-tooltip");
    const points = [...chart.querySelectorAll(".trend-point")];
    const show = (target) => {
      const index = Number(target.dataset.trendIndex);
      const values = JSON.parse(target.dataset.values || "[]");
      points.forEach((point) => point.classList.toggle("active", Number(point.dataset.pointIndex) === index));
      tooltip.innerHTML = `<strong>${escapeHtml(chartPeriodLabel(target.dataset.period))}</strong>${values.map((item) => `<span>${escapeHtml(item.label)} <b>${number(item.value)}</b></span>`).join("")}`;
      tooltip.hidden = false;
      const chartBox = chart.getBoundingClientRect(); const targetBox = target.getBoundingClientRect();
      const x = targetBox.left + targetBox.width / 2 - chartBox.left;
      tooltip.style.left = `${Math.min(Math.max(x, 90), Math.max(chartBox.width - 90, 90))}px`;
    };
    const hide = () => { tooltip.hidden = true; points.forEach((point) => point.classList.remove("active")); };
    chart.querySelectorAll("[data-trend-index]").forEach((target) => {
      target.addEventListener("mouseenter", () => show(target));
      target.addEventListener("focus", () => show(target));
      target.addEventListener("mouseleave", hide);
      target.addEventListener("blur", hide);
    });
  });
}

function renderMonthlyTrends(monthly) {
  const target = document.getElementById("reach-trend");
  const charts = Object.entries(monthly || {}).filter(([, rows]) => rows?.length).map(([provider, rows]) => {
    if (provider === "spotify") return trendChart("Spotify activity", rows, [{key:"downloads",label:"Downloads",className:"series-primary"},{key:"plays",label:"Spotify plays",className:"series-secondary"}]);
    if (provider === "apple_podcasts") return trendChart("Apple Podcasts activity", rows, [{key:"plays",label:"Plays",className:"series-primary"},{key:"listeners",label:"Monthly listeners",className:"series-secondary"}]);
    return trendChart(`${providerLabel(provider)} activity`, rows, [{key:"activity",label:"Measured activity",className:"series-primary"},{key:"listeners",label:"Reported audience",className:"series-secondary"}]);
  });
  target.innerHTML = `<div class="trend-controls" aria-label="Trend range"><button type="button" data-trend-range="12" class="${trendRange === 12 ? "active" : ""}">12 months</button><button type="button" data-trend-range="24" class="${trendRange === 24 ? "active" : ""}">24 months</button><button type="button" data-trend-range="0" class="${trendRange === 0 ? "active" : ""}">All history</button></div><div class="monthly-trend-grid">${charts.join("") || empty("No provider has returned comparable monthly history yet.")}</div>`;
  attachTrendInteractions(target);
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
  target.innerHTML = `${view.comparison ? `<div class="performance-change ${change.className}"><strong>${escapeHtml(change.text)}</strong><span>${number(view.comparison.delta)} podcast activity change · previous period ${formatDate(view.comparison.previous_start)} – ${formatDate(view.comparison.previous_end)}</span></div>` : `<div class="performance-change neutral"><strong>${audioRange === "all" ? "Lifetime history" : "No prior comparable period"}</strong><span>${escapeHtml(periodText)}</span></div>`}${trendChart("Podcast downloads and plays", audioChartRows(view.rows), [{key:"total",label:"Downloads & plays",className:"series-total"},{key:"downloads",label:"Open podcast apps (hosting/RSS)",className:"series-primary"},{key:"plays",label:"Spotify-native plays",className:"series-secondary"}], {range:0,className:"overall-trend-card",periodLabel:audioRange === "7d" || audioRange === "30d" || audioRange === "90d" ? "Date" : "Month",emptyMessage:"Lifetime hosting history is being collected automatically."})}`;
  attachTrendInteractions(target);
  return view;
}

function renderPlatformPerformance(global, monthly, listeningApps, audio, platformMeasurement) {
  const target = document.getElementById("platform-performance");
  const components = Object.fromEntries((global.components || []).map((item) => [item.key, item]));
  const comparison = global.comparison || {};
  const componentStats = comparison.components || {};
  const cards = [
    ["Open podcast apps (hosting/RSS)", audio.downloads, "Authoritative downloads delivered across Apple Podcasts and every other open-RSS app; counted once.", audio.total ? `${percentage(audio.downloads * 100 / audio.total)}% of selected podcast activity` : "Awaiting data", audio.start && audio.end ? `${formatDate(audio.start)} – ${formatDate(audio.end)}` : ""],
    ["Spotify-native", audio.plays, "Native Spotify play starts outside the open-RSS download component.", audio.total ? `${percentage(audio.plays * 100 / audio.total)}% of selected podcast activity` : "Awaiting data", audio.start && audio.end ? `${formatDate(audio.start)} – ${formatDate(audio.end)}` : ""],
    ["YouTube", components.youtube_views?.value, "Video and podcast views from connected channels.", "Latest comparable window", changeLabel(componentStats.youtube_views).text],
  ].map(([label,value,description,meta,detail]) => `<article class="performance-platform-card"><div><span>${escapeHtml(label)}</span><strong>${number(value)}</strong></div><p>${escapeHtml(description)}</p><div class="platform-card-meta"><span>${escapeHtml(meta)}</span><span class="metric-change neutral">${escapeHtml(detail)}</span></div></article>`);
  const appleRows = monthly.apple_podcasts || [];
  const appleCurrent = appleRows.at(-1); const applePrevious = appleRows.at(-2);
  const appleStat = appleCurrent && applePrevious ? {delta_pct:applePrevious.plays ? Math.round((Number(appleCurrent.plays) - Number(applePrevious.plays)) * 1000 / Number(applePrevious.plays)) / 10 : null} : null;
  const appleChange = changeLabel(appleStat);
  cards.push(`<article class="performance-platform-card diagnostic"><div><span>Apple Podcasts engagement</span><strong>${number(appleCurrent?.plays)}</strong></div><p>Apple-native plays for ${escapeHtml(appleCurrent?.period || "the latest reported month")}; shown separately to prevent double-counting RSS delivery.</p><div class="platform-card-meta"><span>${number(appleCurrent?.listeners)} listeners</span><span class="metric-change ${appleChange.className}">${escapeHtml(appleChange.text)}</span></div></article>`);
  const website = (latestPayload?.provider_strength || []).find((item) => ["website", "ga4", "google_analytics"].includes(item.provider));
  if (website) {
    const hasPlayerEvents = website.metrics?.web_player_play_starts != null;
    cards.push(`<article class="performance-platform-card diagnostic"><div><span>Mirror Talk Web Player</span><strong>${hasPlayerEvents ? number(website.metrics.web_player_play_starts) : "Awaiting events"}</strong></div><p>${hasPlayerEvents ? "Player starts on the Mirror Talk website; kept separate from hosting downloads to prevent double-counting." : "Website analytics is connected, but no audio-player event has arrived. Install the supplied player-tracking snippet on the web player, then play one episode to verify collection."}</p><div class="platform-card-meta"><span>${hasPlayerEvents ? `${number(website.metrics?.web_player_completions)} completions` : "No value is shown as zero"}</span><span>${hasPlayerEvents ? `${number(website.metrics?.web_player_unique_users)} users` : "Tracking action required"}</span></div></article>`);
  }
  target.innerHTML = cards.join("");

  const appTarget = document.getElementById("listening-app-summary");
  const apps = (listeningApps || []).slice(0, 8);
  const scope = platformMeasurement || {};
  const scopeNote = `<p class="platform-coverage-note"><strong>${number(scope.covered_count)} of ${number(scope.available_count)} confirmed destinations are included in measured totals.</strong> ${escapeHtml(scope.note || "Separate app figures appear only when the source provides them.")}</p>`;
  appTarget.innerHTML = scopeNote + (apps.length ? `<div class="listening-app-heading"><h3>Lifetime podcast-app mix</h3><p>Host-reported delivery already included in the selected podcast total.</p></div><div class="listening-app-chips">${apps.map((item) => `<span><strong>${escapeHtml(item.name)}</strong>${item.is_percentage ? `${percentage(item.value)}%` : `${number(item.value)} · ${percentage(item.share_pct)}%`}</span>`).join("")}</div>` : `<p class="platform-coverage-note">The podcast total covers every open app. The per-app mix will appear when the hosting source provides it.</p>`);
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

function bindCopyButtons(target) {
  target.querySelectorAll("[data-copy-command]").forEach((button) => button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.copyCommand);
      button.textContent = "Copied";
    } catch (_error) {
      button.textContent = "Copy unavailable — use the text shown below";
      const command = document.createElement("code");
      command.textContent = button.dataset.copyCommand;
      button.parentElement.append(command);
    }
  }));
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
    const stale = enabled && connection.status === "stale";
    const failed = enabled && connection.status === "error";
    const waiting = enabled && connection.status === "waiting";
    const partial = enabled && connection.status === "degraded";
    const missingReports = (connection.missing_reports || []).map((name) => ({age:"age", apps:"listening apps", audience:"audience", gender:"gender", geography:"geography"})[name] || "breakdown");
    const statusLabel = current ? "Current" : partial ? "Partial reports" : reauth ? "Sign-in expired" : failed ? "Sync failed" : stale ? "Mac overdue" : waiting ? "Waiting for first sync" : "Set up";
    const command = `python3 -m guest_database_manager.local_analytics_collector login ${provider} --server ${window.location.origin}`;
    const profileName = provider === "apple_podcasts" ? "apple_podcasts" : "spotify";
    const resetCommand = `pkill -f "Google Chrome --user-data-dir=$HOME/Library/Application Support/MirrorTalkAnalyticsCollector/${profileName}"`;
    const failureGuidance = connection.last_error_code === "export_control_changed" ? "The provider changed its analytics export page; the collector needs review." : "The last automatic collection failed. Run the sign-in command to verify access and synchronize immediately.";
    const guidance = current ? "Reports are arriving automatically." : partial ? `Core reports arrived automatically. ${missingReports.length ? `Spotify did not provide: ${missingReports.join(", ")}.` : "Some breakdowns were unavailable."} The next daily run retries them; no action is needed unless this persists.` : reauth ? (provider === "apple_podcasts" ? "Run the sign-in command, complete MFA, and leave the dedicated Apple Chrome window open so automatic sync can reuse that session." : "Run the sign-in command once; it will verify access and synchronize before it finishes.") : failed ? failureGuidance : stale ? "The Mac has not checked in for more than two days. Its daily collector will retry automatically when the Mac is awake." : waiting ? "The collector is enabled but has not completed its first synchronization." : "Enable the collector, then complete the one-time sign-in on the account owner's Mac.";
    return `<article class="connection-card"><header><div><strong>${label}</strong><p>The secure sign-in stays on the account owner's computer.</p></div><span class="connection-status ${current || partial ? "connected" : "disconnected"}">${statusLabel}</span></header><p>${escapeHtml(guidance)}</p><small>Last update: ${escapeHtml(connection.last_success_at || "No successful update yet")}</small><div class="connection-actions"><button class="${enabled ? "ghost-button" : "secondary-button"}" data-local-provider="${provider}" data-local-enabled="${enabled ? "false" : "true"}" type="button" ${local.configured ? "" : "disabled"}>${enabled ? "Pause connection" : "Enable collector"}</button>${current || partial ? "" : `<button class="secondary-button" data-copy-command="${escapeHtml(command)}" type="button">Copy sign-in command</button>`}<button class="ghost-button" data-copy-command="${escapeHtml(resetCommand)}" type="button" title="Use only when the dedicated provider Chrome window is stuck">Copy browser reset</button></div></article>`;
  }).join("");
  target.innerHTML = `${cards || '<div class="insights-empty"><strong>Connect YouTube</strong><p>Authorize the channel owner once to unlock viewing, audience, and discovery insights.</p></div>'}<article class="connection-card add-connection-card"><header><div><strong>Add a YouTube channel</strong><p>Each owner approves access independently.</p></div></header><button id="connect-google" class="primary-button" type="button" ${google.oauth_configured ? "" : "disabled"}>Connect YouTube</button></article><div class="connection-group-heading"><strong>Podcast analytics</strong><p>Hosting and native-platform reports refresh automatically; private sign-ins never leave the account owner's computer.</p></div>${localCards}`;
  document.getElementById("connect-google")?.addEventListener("click", async () => { try { const result = await connectorRequest("/api/analytics-connectors/google/connect", {method:"POST", body:"{}"}); window.location.assign(result.authorization_url); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } });
  target.querySelectorAll("[data-sync-google]").forEach((button) => button.addEventListener("click", async () => { try { await connectorRequest("/api/analytics-connectors/google/sync", {method:"POST", body:JSON.stringify({connection_id:Number(button.dataset.syncGoogle)})}); await load(); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } }));
  target.querySelectorAll("[data-disconnect-google]").forEach((button) => button.addEventListener("click", async () => { if (!window.confirm("Disconnect this channel and delete only its retained refresh token?")) return; try { await connectorRequest(`/api/analytics-connectors/google?connection_id=${encodeURIComponent(button.dataset.disconnectGoogle)}`, {method:"DELETE"}); await load(); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } }));
  target.querySelectorAll("[data-local-provider]").forEach((button) => button.addEventListener("click", async () => { try { await connectorRequest("/api/analytics-connectors/local/configure", {method:"POST", body:JSON.stringify({provider:button.dataset.localProvider, enabled:button.dataset.localEnabled === "true"})}); await load(); } catch (error) { target.prepend(Object.assign(document.createElement("p"), {className:"message error", textContent:error.message})); } }));
  bindCopyButtons(target);
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

function renderPublicRatings(ratings, status) {
  const target = document.getElementById("public-ratings");
  if (!target) return;
  const storefronts = ratings?.storefronts || [];
  if (!storefronts.length) {
    target.innerHTML = empty(status?.status === "error" ? "The last automatic Apple ratings check could not be read. It retries automatically; earlier values are never discarded." : "Apple Podcasts ratings are checked automatically every day across your listening markets.");
    return;
  }
  const items = storefronts.slice(0, 8);
  const max = Math.max(...items.map((item) => Number(item.count || 0)), 1);
  const remainder = storefronts.length - items.length;
  const gaps = ratings.unrated_audience_markets || [];
  const change = (value) => value == null || Number(value) === 0 ? "" : ` · ${Number(value) > 0 ? "+" : ""}${number(value)} in 30 days`;
  target.innerHTML = `<p class="metric-pairs"><span>Ratings<strong>${number(ratings.total_ratings)}</strong></span><span>Average<strong>${ratings.weighted_average == null ? "—" : `${percentage(ratings.weighted_average)} ★`}</strong></span><span>New in 30 days<strong>${ratings.new_ratings_30d == null ? "—" : number(ratings.new_ratings_30d)}</strong></span><span>Checked<strong class="freshness ${escapeHtml(ratings.freshness || "unknown")}">${escapeHtml(formatDate(ratings.period_end))}</strong></span></p><div class="insight-bars">${items.map((item) => `<div class="insight-bar"><div><strong>${escapeHtml(item.name)}</strong><span>${percentage(item.average)} ★ · ${number(item.count)} ${Number(item.count) === 1 ? "rating" : "ratings"}</span></div><div class="insight-bar-track"><span style="width:${Math.max(2, Number(item.count || 0) * 100 / max)}%"></span></div><small>Apple storefront${escapeHtml(change(item.change_30d))}</small></div>`).join("")}</div>${remainder > 0 ? `<p class="dimension-note">${remainder} more rated ${remainder === 1 ? "storefront is" : "storefronts are"} included in the totals.</p>` : ""}${gaps.length ? `<p class="dimension-note">Measured listeners in ${escapeHtml(gaps.join(", "))} have not left Apple ratings there yet. A localized rating request could close that gap.</p>` : ""}<p class="dimension-note">${escapeHtml(ratings.definition || "")}</p>`;
}

function renderEpisodePerformance(episodes, platformItems) {
  const target = document.getElementById("episode-performance");
  const platformRows = platformItems.map((item) => ({
    title:item.title || item.platform_content_id,
    platform_content_id:item.platform_content_id,
    period_start:item.period_start,
    activity:Number(item.metrics?.plays_downloads ?? item.metrics?.video_lifetime_views ?? item.metrics?.video_views ?? item.metrics?.web_player_play_starts ?? item.metrics?.web_player_completions ?? 0),
    metrics:{
      plays:item.metrics?.plays_downloads ?? item.metrics?.video_lifetime_views ?? item.metrics?.video_views ?? item.metrics?.web_player_play_starts,
      watch_time_hours:item.metrics?.video_lifetime_watch_time_hours ?? item.metrics?.video_watch_time_hours,
      average_view_duration_seconds:item.metrics?.video_lifetime_average_view_duration_seconds ?? item.metrics?.video_average_view_duration_seconds,
      consumption_depth_pct:item.metrics?.web_player_play_starts ? Number(item.metrics?.web_player_completions || 0) * 100 / Number(item.metrics.web_player_play_starts) : null,
    },
    providers:[item.provider],period_end:item.period_end,freshness:item.freshness || "unknown",
  }));
  const rows = [...episodes, ...platformRows].sort((left, right) => Number(right.activity || 0) - Number(left.activity || 0));
  if (!rows.length) { target.innerHTML = empty("Connected sources have not returned episode-level performance yet."); return; }
  const titleCounts = new Map();
  rows.forEach((item) => {
    const key = String(item.title || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
    titleCounts.set(key, (titleCounts.get(key) || 0) + 1);
  });
  target.innerHTML = `<div class="episode-table-wrap"><table class="episode-table"><thead><tr><th>Episode</th><th>Activity</th><th>Depth</th><th>Coverage</th></tr></thead><tbody>${rows.slice(0, 12).map((item) => {
    const metrics = item.metrics || {};
    const depth = metrics.consumption_depth_pct != null ? `${percentage(metrics.consumption_depth_pct)}% consumed` : metrics.average_view_duration_seconds != null ? duration(metrics.average_view_duration_seconds) : "Not provided";
    const providerText = (item.providers || []).map(providerLabel).join(", ");
    const titleKey = String(item.title || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
    const coverage = [providerText];
    if (titleCounts.get(titleKey) > 1) {
      if (item.episode_id != null) {
        coverage.push(`Episode record ${item.episode_id}`);
      } else {
        if (item.period_start) coverage.push(`period starts ${item.period_start}`);
        if (item.platform_content_id) coverage.push(item.platform_content_id);
      }
    }
    const identity = coverage.filter(Boolean).join(" · ");
    return `<tr><td><strong>${escapeHtml(item.title)}</strong><small>Lifetime through ${escapeHtml(item.period_end || "unknown")}</small></td><td><strong>${number(item.activity)}</strong><small>measured lifetime downloads, plays or views</small></td><td>${escapeHtml(depth)}</td><td><span class="freshness ${escapeHtml(item.freshness || "unknown")}">${escapeHtml(freshnessLabel(item.freshness))}</span><small>${escapeHtml(identity)}</small></td></tr>`;
  }).join("")}</tbody></table></div>`;
}

function renderPodcastAdvisory(advisory) {
  const target = document.getElementById("podcast-advisory");
  const category = advisory.release_planning?.category_benchmarks?.[0];
  const promotion = advisory.promotion_planning?.recommendations?.[0];
  const forecast = advisory.forecasting?.first_28_days || {};
  const exceptions = advisory.exception_management?.items || [];
  const cards = [
    ["Release planning", category ? `${category.name} is the strongest current comparison set` : "Building comparable episode groups", advisory.release_planning?.guidance || "Episode-linked evidence will populate this automatically."],
    ["Promotion planning", promotion?.action || "Building a source-backed promotion recommendation", promotion?.reason || "Platform and geography evidence remains visible without inventing missing data."],
    ["28-day forecast", forecast.expected_activity == null ? "Needs more comparable episodes" : `${number(forecast.expected_activity)} expected activity`, `${number(forecast.comparable_episodes || 0)} comparable episodes · median-based, advisory only.`],
    ["Exceptions", exceptions.length ? `${exceptions.length} meaningful change${exceptions.length === 1 ? "" : "s"} need attention` : "No unusual movement detected", exceptions[0]?.title || "Normal source refreshes stay out of the way."],
  ];
  target.innerHTML = cards.map(([label, title, detail]) => `<article class="advisory-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(title)}</strong><p>${escapeHtml(detail)}</p></article>`).join("");
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
  const platformMeasurement = payload.platform_measurement || {};
  const measuredSourcesCurrent = providers.length > 0 && providers.every((item) => item.freshness === "current");
  const rawSetupItems = release.blockers || [];
  const sourceSetupPending = rawSetupItems.some((item) => ["youtube_analytics_not_ready", "provider_collectors_not_ready"].includes(item.code));
  const visibleSetupItems = rawSetupItems.filter((item) => item.code !== "analytics_evidence_incomplete" || !sourceSetupPending);
  document.getElementById("insights-quality").innerHTML = `<div class="overview-status"><span class="coverage-pill ${measuredSourcesCurrent ? "covered" : "building"}">${measuredSourcesCurrent ? "Live data" : "Connecting data"}</span><div><strong>${number(platformMeasurement.covered_count)} of ${number(platformMeasurement.available_count)} confirmed destinations measured</strong><p>${escapeHtml(platformMeasurement.note || (measuredSourcesCurrent ? "All contributing analytics sources are current." : "Automatic collection is active; unavailable source details are never estimated."))}</p></div></div><div><strong>Latest audience data</strong><p>${escapeHtml(quality.latest_period_end || "Automatic collection is starting")}</p></div><button id="refresh-podcast-reach" class="primary-button" type="button">Refresh now</button>`;
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
  const activityComponents = [
    topline.open_rss_downloads ? `${number(topline.open_rss_downloads)} open-RSS downloads` : "",
    topline.spotify_native_plays ? `${number(topline.spotify_native_plays)} Spotify-native plays` : "",
    topline.video_views ? `${number(topline.video_views)} YouTube views` : "",
  ].filter(Boolean).join(" + ");
  const relationshipDetail = [
    relationshipBreakdown.subscribers ? `${number(relationshipBreakdown.subscribers)} subscriptions` : "",
    relationshipBreakdown.followers ? `${number(relationshipBreakdown.followers)} followers` : "",
  ].filter(Boolean).join(" · ");
  const periodAudience = (topline.audience_relationship_by_platform || [])
    .filter((item) => ["unique_listeners", "unique_viewers", "listeners"].includes(item.metric))
    .map((item) => `${providerLabel(item.provider)}: ${number(item.value)} ${metricLabel(item.metric).toLowerCase()} in its latest reported period through ${item.period_end || "unknown"}`)
    .join(" · ");
  document.getElementById("insights-summary").innerHTML = [
    ["Downloads & plays", topline.downloads_plays == null ? "—" : number(topline.downloads_plays), topline.downloads_plays == null ? "Lifetime totals are still being collected from connected sources" : `${lifetimeRange} · ${activityComponents || topline.activity_coverage_note || "source-backed activity"}`, "global"],
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
    ["Places to listen", `${number(summary.verified_platforms)} confirmed destinations`, (summary.unconfirmed_destinations || []).length ? `${number(summary.distribution_coverage_pct)}% of expected destinations confirmed · checking ${summary.unconfirmed_destinations.join(", ")}` : "Every expected destination is confirmed."],
    ["How people watch", youtubeMobileShare == null ? "Connect YouTube for device mix" : `${youtubeMobileShare}% watch on mobile`, youtubeMobileShare == null ? "One connection unlocks mobile, TV, desktop, and tablet viewing." : `${number(youtubeMobileValue)} recent views came from mobile devices.`],
    ["How long they stay", hasViewDuration ? duration(weightedDuration) : "Watch-time detail unavailable", hasViewDuration ? "Average viewing time across connected channels." : "The connected source has not returned average viewing duration yet."],
  ].map(([label,value,detail]) => `<article class="highlight-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><p>${escapeHtml(detail)}</p></article>`).join("");
  renderOverallPerformance(dailyAudio);
  renderPlatformPerformance(global, payload.monthly_trends || {}, payload.listening_apps || [], audio, platformMeasurement);
  renderDecisionIntelligence(payload.decision_intelligence || {});
  renderPodcastAdvisory(payload.advisory || {});
  const coverage = payload.source_coverage || {}; const publicSources = coverage.public || []; const privateSources = coverage.private || [];
  renderConnections(payload.analytics_connectors || {});
  const automated = privateSources.filter((source) => source.connection_mode === "automated"); const limited = privateSources.filter((source) => source.connection_mode === "provider_limited");
  const sourceRow = (source) => { const metrics = source.metrics_present?.length ? source.metrics_present : source.metrics || []; const shown = metrics.slice(0, 5); const active = source.status === "data_present"; const playerSetup = source.key === "website_analytics" ? `<div class="connection-actions"><button class="ghost-button" type="button" data-copy-command="${escapeHtml(`<script defer src="${window.location.origin}/static/web-player-analytics.js?v=20261127.1"></script>`)}">Copy player tracking snippet</button></div>` : ""; return `<article class="source-row"><div><strong>${escapeHtml(source.name)}</strong><span class="source-status ${active ? "data_present" : "provider_access_required"}">${active ? "Current" : "Connecting"}</span></div><small>${active ? `${Number(source.observation_count || 0)} data points · through ${escapeHtml(source.latest_period_end || "unknown")}` : "The automatic collector is waiting for owner-approved provider access."}</small><p>${source.metrics_present?.length ? "Available" : "Expected"}: ${shown.map(metricLabel).map(escapeHtml).join(", ")}${metrics.length > shown.length ? ` +${metrics.length - shown.length} more` : ""}</p>${playerSetup}</article>`; };
  document.getElementById("source-coverage").innerHTML = `<div class="source-column"><h3>Public availability <span>${Number(coverage.public_available || 0)}/${Number(coverage.public_expected || 0)}</span></h3>${publicSources.length ? publicSources.map((source) => { const retrying = source.status === "retrying"; const available = source.status === "available"; return `<article class="source-row"><div><strong>${escapeHtml(source.source_name)}</strong><span class="source-status ${available ? "data_present" : retrying ? "refreshing" : "unavailable"}">${available ? "Verified" : retrying ? "Verified · retrying check" : "Temporarily unavailable"}</span></div><small>${escapeHtml(retrying && source.last_success_at ? `Verified ${formatTimestamp(source.last_success_at)} · retry attempted ${formatTimestamp(source.checked_at)}` : formatTimestamp(source.checked_at))}</small></article>`; }).join("") : empty("The first availability check will run automatically.")}</div><div class="source-column"><h3>Connected sources <span>${Number(coverage.automated_connected || 0)}/${Number(coverage.automated_expected || 0)}</span></h3>${automated.map(sourceRow).join("")}</div><div class="source-column"><h3>Private analytics <span>${limited.filter((source) => source.status === "data_present").length}/${limited.length}</span></h3>${limited.map(sourceRow).join("")}</div>`;
  bindCopyButtons(document.getElementById("source-coverage"));
  const platformCoverageByKey = Object.fromEntries((platformMeasurement.platforms || []).map((item) => [item.key, item]));
  document.getElementById("platform-grid").innerHTML = (payload.platforms || []).map((platform) => {
    const status = platform.availability === "available" ? "Confirmed" : platform.distribution_mode === "expected_missing" ? "Not listed" : "Being checked";
    const mode = {direct_listing:"Official listing",direct_video:"Video channel",catalog_listing:"Podcast directory",rss_subscription:"Opens with RSS",expected_missing:"Optional destination"}[platform.distribution_mode] || "Podcast destination";
    const checked = platform.verified_on ? `Checked ${String(platform.verified_on).slice(0, 10)}` : "Automatic check scheduled";
    const measurement = platformCoverageByKey[platform.key];
    return `<a class="platform-card" href="${escapeHtml(safeUrl(platform.url))}" target="_blank" rel="noopener noreferrer"><span>${escapeHtml(mode)}</span><strong>${escapeHtml(platform.name)}</strong><small>${escapeHtml(status)} · ${escapeHtml(checked)}</small>${measurement ? `<small>${escapeHtml(measurement.detail)}</small>` : ""}</a>`;
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
  renderPublicRatings(payload.public_ratings, payload.analytics_connectors?.public_ratings);
  renderEpisodePerformance(payload.episode_performance || [], payload.top_platform_content || []);
  renderMonthlyTrends(payload.monthly_trends || {});
  const coverageItems = payload.measurement_coverage || [];
  document.getElementById("measurement-coverage").innerHTML = coverageItems.length ? `<div class="coverage-heading"><div><span class="eyebrow">Measurement coverage</span><h3>${coverageItems.filter((item) => item.available).length}/${coverageItems.length} insight groups available</h3></div><p>Unavailable provider metrics remain blank—not zero.</p></div><div class="coverage-grid">${coverageItems.map((item) => `<article><span class="coverage-dot ${item.available ? "available" : "missing"}"></span><div><strong>${escapeHtml(item.label)}</strong><small>${item.available ? escapeHtml((item.providers || []).map(providerLabel).join(", ") || "Connected source") : item.label === "Web-player engagement" ? "Website connected · awaiting player events and tracking verification" : "Not exposed by connected sources"}</small></div></article>`).join("")}</div>` : "";
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
