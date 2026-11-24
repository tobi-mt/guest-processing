# Podcast Reach implementation and execution plan

## Mission

Build an automated, auditable measurement system that reports every podcast distribution and analytics source that is technically and contractually accessible, never invents unavailable data, and makes missing or stale coverage explicit.

“100% coverage” means all of the following:

1. Every known listing has a persisted evidence record and a current verification state.
2. Every supported private analytics source is connected, intentionally waived, or visibly blocked by provider access.
3. Every collected number has provider, metric definition, time grain, dimensional grain, source class, import batch, and revision provenance.
4. Every scheduled source has freshness, retry, failure, and schema-drift monitoring.
5. Inaccessible private platform data is reported as unavailable, never estimated or silently treated as zero.

It cannot mean identifying every application that may privately copy a public RSS feed or obtaining private metrics that a platform does not expose.

## Measurement contract

### Distribution

- `verified`: the exact listing or canonical feed was successfully checked and matched.
- `catalog_inferred`: a catalog is known to syndicate to another application, but the exact listing was not independently verified.
- `configured`: an operator supplied a listing that has not yet completed verification.
- `unavailable`: the last verification failed; the previous evidence remains in history.

### Reach and engagement

- Open-RSS downloads come from the hosting/CDN delivery source.
- Spotify plays, Apple plays, YouTube views, and RSS downloads remain distinct measures.
- A mixed `plays_and_downloads` measure is allowed only with that exact label and provider definition.
- Unique listeners are never summed across providers.
- Demographics are accepted only from provider-reported aggregate data. They are never inferred.
- Geography from delivery logs is labeled approximate; provider-native geography retains its provider definition.

### Source authority

For the same `overlap_group`, reporting selects one source family in this order:

1. Host/CDN delivery evidence for open-RSS downloads
2. Direct provider-native analytics
3. Host-provided cross-platform aggregate
4. Website analytics
5. Aggregator copies

All copies remain immutable and auditable even when they are not selected for a headline metric.

## Architecture

### Collection plane

- Daily public listing and RSS verification
- Read-only Google OAuth for YouTube Analytics, YouTube Data API, and GA4
- Spotify for Creators official CSV exports collected by the local authorized collector
- Apple Podcasts Connect official exports collected by the local authorized collector
- Optional server-side analytics aggregation API, treated as secondary evidence
- Manual import remains a supervised recovery path for provider UI or collector failures

### Evidence plane

- Immutable observations
- Append-only revisions with `supersedes_id`
- A current-observation projection for dashboards
- First-class country, city, device, app, age, gender, traffic-source, and platform-content dimensions
- Explicit source class and overlap group
- Correlation IDs, actors, source references, payload-derived hashes, and import timestamps

### Intelligence plane

- Equal-age D7, D30, and D90 episode comparisons
- Median and percentile baselines by content format and editorial pillar
- Change-point and anomaly detection after data-quality checks pass
- Geography, device, traffic-source, and demographic shifts
- Forecasts with prediction intervals and a minimum-data threshold
- Recommendations in advisory/shadow mode until an operator approves promotion

AI never fills missing provider measurements. It may explain, forecast, or recommend only from source-backed observations.

## Execution workstreams

### Workstream A — Evidence correctness

Status: implemented in migrations 44–46 and the analytics service.

- Version corrected provider values instead of silently discarding them.
- Preserve immutable historical observations.
- Read dashboards from the current revision projection.
- Hash observation content, not only a source filename.
- Store structured dimensions and platform content identity.
- Select authoritative evidence for explicit overlap groups.
- Preserve show-versus-episode grain safeguards.

Acceptance:

- Reimporting an identical value is idempotent.
- Reimporting a corrected value creates exactly one revision.
- Historical and current values are independently queryable.
- Direct and aggregated copies cannot inflate headline totals.

### Workstream B — Distribution registry and discovery

Status: persistent registry, first-party listening-directory discovery, Podnews catalog discovery, and daily verification implemented.

- Persist platform identity, listing URL, discovery method, evidence level, status, and verification timestamps.
- Seed the canonical feed plus owned Spotify, Apple, YouTube, Amazon Music, and iHeartRadio listings.
- Update registry evidence from daily source checks.
- Reconcile the first-party listening directory and Podnews catalog every day.
- Add an operator review queue for uncertain title-only matches.
- Never auto-merge listings by title or episode number.

Acceptance:

- The dashboard count comes from the registry rather than a constant.
- Failed checks make the listing stale/unavailable without deleting previous evidence.
- Candidate matches require canonical feed, podcast GUID, or owner-confirmed platform ID evidence.

Current registry coverage comprises direct/owned listings, catalog listings, RSS-subscription targets, and explicitly known missing directories. It includes Spotify, Apple Podcasts, YouTube, Amazon Music, iHeartRadio, Deezer, Goodpods, Castbox, Castamatic, iVoox, Listen Notes, Metacast, Moon FM, Overcast, Pocket Casts, Podbean, Podcast Addict, Podcast Guru, Podcast Republic, Podchaser, Podcast Index, PodLP, Podverse, AntennaPod, Anytime Player, Castro, Curiocaster, Great Pods, Player FM, Steno.fm, Subscribe on Android, Subscribe by Email, YouTube Music RSS, the Mirror Talk web player, and Podnews. Truefans and Luminary are tracked as known missing destinations rather than falsely counted as available.

### Workstream C — Automated private analytics

Status: Google is scheduled; configured aggregation sync is now scheduled with a 20-hour freshness guard; local collectors exist.

- Backfill Google/YouTube in bounded windows, then collect daily with overlap for provider corrections.
- Collect YouTube totals, devices, countries, demographics, traffic sources, average view percentage, and video-level performance.
- Run Spotify and Apple collectors on an owned machine with local browser profiles and MFA reauthorization alerts.
- Keep provider sessions and passwords out of Railway.
- Quarantine unknown export schemas and require a reviewed parser update.
- Treat the aggregation connector as secondary evidence until provenance and commercial access are verified.

Acceptance:

- At least 99% of scheduled daily runs complete within 24 hours over a rolling 30-day window.
- A source becomes `stale` after two missed expected runs.
- Authorization failures become `reauth_required`; no credentials appear in logs or API responses.
- Provider corrections are visible as revisions.

### Workstream D — Episode identity

Status: RSS reconciliation exists; platform-content IDs are now retained. Cross-platform content mapping remains rollout work.

- Canonical identity order: RSS GUID, enclosure identity, provider episode/video ID, then reviewable metadata evidence.
- Add a platform-content mapping table with confidence, method, reviewer, and timestamps.
- Match exact GUID or explicit provider link automatically.
- Keep title/date/duration matches in review unless the evidence is uniquely strong.
- Never identify an episode by episode number alone.

Acceptance:

- No platform metric is attached to an internal episode through episode number alone.
- Ambiguous matches remain unlinked and visible.
- Mapping changes are audited and do not rewrite raw observations.

### Workstream E — Dashboard and quality scorecard

Status: registry states and expanded YouTube intelligence are displayed.

- Show known, verified, pending, unavailable, analytics-connected, stale, and inaccessible counts separately.
- Show source freshness and most recent successful reporting period.
- Present open-RSS downloads separately from native plays/views.
- Add D7/D30/D90 episode cohorts and correction indicators.
- Display demographics only when privacy thresholds return provider data.
- Add warnings for missing periods, mixed grain, revisions, overlap conflicts, and schema drift.

Acceptance:

- Missing, zero, stale, and unavailable are visually and semantically distinct.
- Every headline metric exposes its definition, period, source, and freshness.
- Keyboard, responsive, no-overflow, and representative-data visual checks pass.

### Workstream F — Reliability and operations

Status: database-backed single-leader analytics lease implemented; operational alert delivery remains rollout work.

- Run analytics scheduling through a database-backed single-leader lease across web replicas.
- Use per-source watermarks, bounded backfills, exponential retry, and dead-letter/review states.
- Recollect recent periods to capture late provider corrections.
- Add readiness signals for required connector configuration and migration state.
- Alert only on actionable changes: stale source, schema drift, revoked authorization, repeated failure, or reconciliation mismatch.
- Retain aggregate analytics in SQLite at current scale. Raw event/log ingestion requires the separately governed PostgreSQL/object-storage scaling decision.

Service objectives:

- Public listing verification: daily, 99.5% monthly success
- YouTube/GA4: daily, data no older than 48 hours
- Spotify/Apple exports: daily where provider sessions remain authorized; otherwise explicit stale/reauth state
- Dashboard availability: existing application SLO
- Duplicate inflation: zero known overlap groups
- Silent data loss: zero; rejected and quarantined records are counted and auditable

## Rollout sequence

### Release 1 — Correctness foundation

- Apply migrations 44–46 on empty, current-copy, and representative legacy databases.
- Deploy revision-aware ingestion and current-view reads.
- Deploy dynamic registry-backed platform cards.
- Enable overlap groups on provider adapters.
- Verify backup and restore before production migration.

### Release 2 — Connector completion

- Configure Google OAuth, token encryption, GA4 property, and each owned YouTube channel.
- Configure and validate the aggregation connector if retained.
- Install the local collector on the authorized operations machine.
- Run supervised Spotify and Apple logins and an initial historical export.
- Add OS-level schedules and heartbeat monitoring for local collection.

### Release 3 — Backfill and reconciliation

- Backfill at least 12 months in bounded batches.
- Compare monthly totals with each provider UI/export.
- Record accepted tolerances and metric-definition differences.
- Resolve episode mappings through GUID/provider IDs or review.
- Do not enable executive totals until reconciliation passes.

### Release 4 — Intelligence

- Establish D7/D30/D90 baselines.
- Enable anomaly detection with minimum sample sizes.
- Run recommendations in shadow mode for at least four publishing cycles.
- Measure recommendation calibration and operator acceptance before promotion.

## Deployment checklist

- `guest-manager podcast-release-readiness --db /path/to/guest_database.db` exits zero
- Backup created and restore tested
- Migration integrity check passes
- Row counts and current-revision counts reconciled
- Connector secrets present only in the deployment environment
- OAuth callback and least-privilege scopes verified
- No provider sessions stored in the cloud service
- Source monitors and scheduled jobs have a single active leader
- Representative UI checked at desktop, tablet, and mobile widths
- Alerts tested with simulated stale, revoked, schema-change, and upstream-failure states
- Rollback keeps migration data readable and does not delete collected evidence

## External dependencies and unavoidable limits

- Spotify and Apple creator analytics do not expose equivalent supported public APIs; official exports and authorized collection are required.
- Public RSS feeds can be copied or manually added to applications without notifying the publisher. Exact universal distribution discovery is therefore impossible.
- Cross-platform people cannot be deduplicated without compatible identity-level reporting, which providers do not supply.
- Privacy thresholds can suppress demographics and geography. Suppression is a valid unavailable state, not a collection failure.
- Independent IAB-compliant measurement may require a host-supported measurement prefix or certified vendor and applies prospectively, not retroactively.

