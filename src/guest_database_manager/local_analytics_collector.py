"""Local-only browser collector for provider-limited podcast analytics.

Provider credentials and browser cookies remain in a dedicated local browser profile.
Only downloaded CSV contents are sent to the configured Mirror Talk server.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import getpass
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests


COLLECTOR_TOKEN_ENV = "MIRROR_TALK_ANALYTICS_COLLECTOR_TOKEN"
KEYCHAIN_SERVICE = "MirrorTalkAnalyticsCollector"
DEFAULT_URLS = {
    "spotify": "https://creators.spotify.com/analytics",
    "apple_podcasts": "https://podcastsconnect.apple.com/analytics",
}
LAUNCH_AGENT_PREFIX = "com.mirrortalk.analytics"
BROWSER_CHANNEL_ENV = "MIRROR_TALK_ANALYTICS_BROWSER_CHANNEL"


class LocalCollectorError(RuntimeError):
    """A safe collector failure that never contains session material."""


class ReauthenticationRequired(LocalCollectorError):
    """The provider requires a one-time owner authentication ceremony."""


def _collector_token() -> str:
    token = os.environ.get(COLLECTOR_TOKEN_ENV, "").strip()
    if token:
        return token
    if sys.platform == "darwin":
        result = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", KEYCHAIN_SERVICE],
            check=False, capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    return ""


def save_collector_token() -> None:
    """Store the Railway ingestion token in the current macOS user's Keychain."""
    if sys.platform != "darwin":
        raise LocalCollectorError("Secure token setup is currently supported on macOS only.")
    token = getpass.getpass("Railway analytics collector token: ").strip()
    if len(token) < 32:
        raise LocalCollectorError("The collector token must contain at least 32 characters.")
    result = subprocess.run(
        [
            "security", "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE,
            "-a", getpass.getuser(), "-w", token,
        ],
        check=False, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise LocalCollectorError("The collector token could not be saved in macOS Keychain.")


def _server_url(value: str) -> str:
    url = str(value or "").strip().rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme == "https" and parsed.netloc:
        return url
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return url
    raise LocalCollectorError("The collector server must use HTTPS (localhost is allowed for testing).")


def _profile_path(root: Path, provider: str) -> Path:
    path = root.expanduser().resolve() / provider
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def _post(server: str, token: str, path: str, payload: dict) -> dict:
    if len(token) < 32:
        raise LocalCollectorError(f"Set {COLLECTOR_TOKEN_ENV} to the Railway collector secret.")
    response = requests.post(
        f"{_server_url(server)}{path}",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=90,
    )
    try:
        body = response.json()
    except ValueError as exc:
        raise LocalCollectorError("The dashboard returned an unreadable collector response.") from exc
    if not response.ok:
        raise LocalCollectorError(str(body.get("error") or "The dashboard rejected the collector request."))
    return body


def _status(server: str, token: str, provider: str, status: str, error_code: str = "") -> None:
    _post(server, token, "/api/analytics-connectors/local/status", {
        "provider": provider, "status": status, "error_code": error_code,
    })


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise LocalCollectorError(
            "Install the local collector with `python -m pip install -e '.[collector]'`, "
            "then run `playwright install chromium`."
        ) from exc
    return sync_playwright


def _browser_channel() -> str | None:
    """Prefer the installed Chrome release for owner-controlled provider sessions."""
    configured = os.environ.get(BROWSER_CHANNEL_ENV, "").strip()
    if configured:
        return None if configured.casefold() in {"bundled", "chromium"} else configured
    if sys.platform == "darwin" and Path("/Applications/Google Chrome.app").is_dir():
        return "chrome"
    if sys.platform.startswith("win") and any(
        (Path(root) / "Google/Chrome/Application/chrome.exe").is_file()
        for root in filter(None, (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)")))
    ):
        return "chrome"
    if shutil.which("google-chrome") or shutil.which("google-chrome-stable"):
        return "chrome"
    return None


def _native_chrome_executable() -> str | None:
    if sys.platform == "darwin":
        candidate = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        return str(candidate) if candidate.is_file() else None
    if sys.platform.startswith("win"):
        for root in filter(None, (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"))):
            candidate = Path(root) / "Google/Chrome/Application/chrome.exe"
            if candidate.is_file():
                return str(candidate)
        return None
    return shutil.which("google-chrome") or shutil.which("google-chrome-stable")


def _launch_browser_context(playwright, *, profile_path: Path, headless: bool):
    options = {
        "headless": headless,
        "accept_downloads": True,
    }
    channel = _browser_channel()
    if channel:
        options["channel"] = channel
    return playwright.chromium.launch_persistent_context(str(profile_path), **options)


@contextmanager
def _sync_browser_context(
    playwright, *, profile_path: Path, headless: bool, quiet_window: bool = False,
):
    """Reuse the owner's native Chrome session without a Playwright-owned launch.

    Some provider identity systems accept the dedicated profile in normal Chrome but
    invalidate the same session when Playwright launches the browser itself. Starting
    Chrome normally and attaching over its supported DevTools endpoint preserves the
    one-time owner login while keeping credentials and cookies on this computer.
    """
    native_chrome = _native_chrome_executable()
    if not native_chrome:
        context = _launch_browser_context(
            playwright, profile_path=profile_path, headless=headless,
        )
        try:
            yield context
        finally:
            context.close()
        return

    active_port_path = profile_path / "DevToolsActivePort"
    try:
        resident_port = int(active_port_path.read_text(encoding="utf-8").splitlines()[0])
    except (FileNotFoundError, IndexError, ValueError):
        resident_port = 0
    if 1 <= resident_port <= 65535:
        try:
            resident_browser = playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{resident_port}", timeout=5_000,
            )
        except Exception:
            resident_browser = None
        if resident_browser is not None and resident_browser.contexts:
            # Do not call browser.close(): Apple authentication is session-only, so
            # this owner-started browser intentionally remains available to later runs.
            yield resident_browser.contexts[0]
            return

    active_port_path.unlink(missing_ok=True)
    arguments = [
        native_chrome,
        f"--user-data-dir={profile_path}",
        "--no-first-run",
        "--remote-debugging-port=0",
    ]
    if headless:
        arguments.append("--headless=new")
    elif quiet_window:
        # Native headed Chrome is required by the provider portals, but a scheduled
        # collection should not steal focus or cover the owner's work.
        arguments.extend(["--window-position=-32000,-32000", "--window-size=800,600"])
    arguments.append("about:blank")
    process = subprocess.Popen(
        arguments, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    browser = None
    try:
        deadline = time.monotonic() + 20
        port = 0
        while time.monotonic() < deadline and process.poll() is None:
            try:
                port = int(active_port_path.read_text(encoding="utf-8").splitlines()[0])
            except (FileNotFoundError, IndexError, ValueError):
                time.sleep(0.1)
                continue
            if 1 <= port <= 65535:
                break
            port = 0
        if not port:
            raise LocalCollectorError("The dedicated Chrome analytics session could not start.")
        browser = playwright.chromium.connect_over_cdp(
            f"http://127.0.0.1:{port}", timeout=20_000,
        )
        if not browser.contexts:
            raise LocalCollectorError("The dedicated Chrome analytics session was unavailable.")
        yield browser.contexts[0]
    finally:
        if browser is not None:
            browser.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _annotate_apple_export(csv_text: str, *, range_days: int, today: date | None = None) -> str:
    """Make Apple’s otherwise implicit analytics window explicit in every row."""
    if not 1 <= range_days <= 366:
        raise LocalCollectorError("Apple Podcasts returned an unsupported analytics date range.")
    reader = csv.DictReader(StringIO(csv_text.lstrip("\ufeff")))
    headers = list(reader.fieldnames or [])
    if not headers:
        raise LocalCollectorError("Apple Podcasts returned an unreadable analytics report.")
    rows = list(reader)
    end = today or date.today()
    start = end - timedelta(days=range_days - 1)
    period_headers = ["Analytics Period Start", "Analytics Period End"]
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=[*headers, *period_headers], lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({
            **row,
            "Analytics Period Start": start.isoformat(),
            "Analytics Period End": end.isoformat(),
        })
    return output.getvalue()


def _spotify_reporting_window(csv_text: str) -> tuple[date, date]:
    reader = csv.DictReader(StringIO(csv_text.lstrip("\ufeff")))
    dates = []
    for row in reader:
        value = str(row.get("Date") or "").strip()
        for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                dates.append(datetime.strptime(value, date_format).date())
                break
            except ValueError:
                continue
    if not dates:
        raise LocalCollectorError("Spotify returned an analytics report without a valid reporting window.")
    return min(dates), max(dates)


def _annotate_analytics_window(csv_text: str, *, start: date, end: date) -> str:
    reader = csv.DictReader(StringIO(csv_text.lstrip("\ufeff")))
    headers = list(reader.fieldnames or [])
    if not headers:
        raise LocalCollectorError("The provider returned an unreadable analytics report.")
    output = StringIO()
    period_headers = ["Analytics Period Start", "Analytics Period End"]
    writer = csv.DictWriter(output, fieldnames=[*headers, *period_headers], lineterminator="\n")
    writer.writeheader()
    for row in reader:
        writer.writerow({
            **row,
            "Analytics Period Start": start.isoformat(),
            "Analytics Period End": end.isoformat(),
        })
    return output.getvalue()


def _spotify_dimension_schema(csv_text: str) -> str | None:
    headers = set(csv.DictReader(StringIO(csv_text.lstrip("\ufeff"))).fieldnames or [])
    for name, required in (
        ("audience", {"Date", "Total", "Returning", "New"}),
        ("gender", {"Gender", "Percentage"}),
        ("age", {"Age", "Total percentage"}),
        ("geography", {"Geo", "Percentage"}),
        ("apps", {"App", "Percentage"}),
    ):
        if required.issubset(headers):
            return name
    return None


def _visible_counter(page, label: str) -> int | None:
    """Read a labelled provider counter without depending on presentation markup."""
    text = page.locator("body").inner_text()
    number = r"([0-9][0-9,.]*[KkMm]?)"
    escaped = re.escape(label)
    for pattern in (
        rf"(?im)^\s*{escaped}\s*\n\s*{number}\s*$",
        rf"(?im)^\s*{number}\s*\n\s*{escaped}\s*$",
        rf"(?im)^\s*{escaped}\s+{number}\s*$",
        rf"(?im)^\s*{number}\s+{escaped}\s*$",
    ):
        match = re.search(pattern, text)
        if match:
            raw = match.group(1).replace(",", "")
            multiplier = 1
            if raw[-1:].casefold() == "k":
                multiplier, raw = 1_000, raw[:-1]
            elif raw[-1:].casefold() == "m":
                multiplier, raw = 1_000_000, raw[:-1]
            return round(float(raw) * multiplier)
    return None


def _audience_snapshot_csv(*, snapshot_date: date, followers: int | None, listeners: int | None) -> str | None:
    if followers is None and listeners is None:
        return None
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=["Snapshot Date", "Followers", "Listeners"], lineterminator="\n")
    writer.writeheader()
    writer.writerow({
        "Snapshot Date": snapshot_date.isoformat(),
        "Followers": "" if followers is None else followers,
        "Listeners": "" if listeners is None else listeners,
    })
    return output.getvalue()


def _spotify_home_url(analytics_url: str) -> str | None:
    match = re.search(r"/analytics/show/([^/?#]+)", analytics_url)
    if not match:
        return None
    return urljoin(analytics_url, f"/home/show/{match.group(1)}")


def _select_spotify_all_time(page) -> None:
    """Select Spotify's lifetime performance window before exporting."""
    semantic_trigger = page.get_by_role(
        "button", name=re.compile(r"^Select date range$", re.I),
    )
    visible_semantic_triggers = [
        semantic_trigger.nth(index)
        for index in range(semantic_trigger.count())
        if semantic_trigger.nth(index).is_visible()
    ]
    if len(visible_semantic_triggers) == 1:
        trigger = visible_semantic_triggers[0]
    elif len(visible_semantic_triggers) > 1:
        raise LocalCollectorError("Spotify exposed multiple performance range controls.")
    else:
        trigger = None
    labels = page.get_by_text("Last 30 days", exact=True)
    if trigger is None:
        for index in range(labels.count()):
            parent = labels.nth(index).locator("xpath=..")
            if parent.evaluate("(node) => node.tagName") == "BUTTON" and parent.is_visible():
                trigger = parent
                break
    if trigger is None:
        selected = page.get_by_text("All time", exact=True)
        for index in range(selected.count()):
            parent = selected.nth(index).locator("xpath=..")
            if parent.evaluate("(node) => node.tagName") == "BUTTON" and parent.is_visible():
                return
        raise LocalCollectorError("Spotify's performance range control was unavailable.")
    trigger.click()
    option = page.get_by_text("All time", exact=True)
    visible = [option.nth(index) for index in range(option.count()) if option.nth(index).is_visible()]
    if len(visible) != 1:
        raise LocalCollectorError("Spotify's all-time performance option was unavailable or ambiguous.")
    visible[0].click()
    page.wait_for_timeout(3_000)


def _download_csv(page, control, directory: Path, *, prefix: str = "") -> tuple[str, str]:
    with page.expect_download(timeout=90_000) as download_info:
        control.click()
    download = download_info.value
    filename = Path(download.suggested_filename).name
    destination = directory / f"{prefix}{filename}"
    download.save_as(destination)
    return filename, destination.read_text(encoding="utf-8-sig")


def _validate_provider_export(provider: str, csv_text: str) -> None:
    """Fail closed before uploading a provider file whose schema changed."""
    try:
        headers = set(csv.DictReader(StringIO(csv_text.lstrip("\ufeff"))).fieldnames or [])
    except csv.Error as exc:
        raise LocalCollectorError("The provider download was not valid CSV.") from exc
    if provider == "spotify":
        required = {
            "Date", "Plays & downloads", "Plays (on Spotify)",
            "Downloads (everywhere else)", "Audience",
        }
        if not required.issubset(headers):
            raise LocalCollectorError(
                "Spotify returned a different analytics report; nothing was uploaded."
            )
    elif provider == "apple_podcasts":
        legacy = {"Show ID", "Date"}.issubset(headers)
        current = {
            "Show Name", "Episode ID", "Episode Title", "Release Date",
            "Unique Listeners", "Unique Engaged Listeners", "Plays",
            "Average Consumption", "Analytics Period Start", "Analytics Period End",
        }.issubset(headers)
        if not legacy and not current:
            raise LocalCollectorError(
                "Apple Podcasts returned a different analytics report; nothing was uploaded."
            )


def login(provider: str, *, profile_root: Path, url: str) -> None:
    """Open a dedicated local browser for a user-controlled login and MFA ceremony."""
    profile = _profile_path(profile_root, provider)
    native_chrome = _native_chrome_executable()
    if native_chrome:
        if sys.platform == "darwin":
            if provider == "apple_podcasts":
                subprocess.Popen(
                    [
                        native_chrome, f"--user-data-dir={profile}", "--no-first-run",
                        "--remote-debugging-port=0", url,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                input(
                    "Complete Apple login and MFA in the dedicated Chrome window, "
                    "leave that window open for automatic sync, then press Enter here: "
                )
                return
            subprocess.Popen(
                [
                    "/usr/bin/open", "-na", "Google Chrome", "--args",
                    f"--user-data-dir={profile}", "--no-first-run", url,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            input(
                "Complete provider login and MFA in the separate Chrome window, "
                "close that window, then press Enter here: "
            )
            return
        process = subprocess.Popen(
            [native_chrome, f"--user-data-dir={profile}", "--no-first-run", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            input("Complete provider login and MFA in Chrome, then press Enter here to retain the local session: ")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        return

    sync_playwright = _playwright()
    with sync_playwright() as playwright:
        context = _launch_browser_context(
            playwright,
            profile_path=profile,
            headless=False,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        input("Complete provider login and MFA in the browser, then press Enter here to retain the local session: ")
        context.close()


def sync_once(
    provider: str, *, server: str, token: str, profile_root: Path, url: str,
    headed: bool = False, quiet_window: bool = False,
) -> dict:
    """Download one explicitly labelled provider CSV and upload it through the safe ingestion boundary."""
    sync_playwright = _playwright()
    try:
        uploads: list[tuple[str, str]] = []
        with sync_playwright() as playwright, tempfile.TemporaryDirectory(prefix="mirror-talk-analytics-") as temp_dir:
            with _sync_browser_context(
                playwright,
                profile_path=_profile_path(profile_root, provider),
                headless=not headed,
                quiet_window=quiet_window,
            ) as context:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=90_000)
                page.wait_for_timeout(3_000)
                password_fields = page.locator('input[type="password"]')
                visible_password = any(
                    password_fields.nth(index).is_visible()
                    for index in range(password_fields.count())
                )
                if visible_password or re.search(r"/(?:login|signin|auth)(?:/|\?|$)", page.url, re.I):
                    login_path = urlsplit(page.url).path[:160]
                    _status(server, token, provider, "reauth_required", "provider_login_required")
                    raise ReauthenticationRequired(
                        f"Provider login or MFA is required at {login_path or '/'}. "
                        "Run the collector login command again."
                    )
                if provider == "spotify":
                    analytics_url = page.url
                    home_url = _spotify_home_url(analytics_url)
                    if home_url:
                        page.goto(home_url, wait_until="networkidle", timeout=90_000)
                        spotify_snapshot = _audience_snapshot_csv(
                            snapshot_date=date.today(),
                            followers=_visible_counter(page, "Followers"),
                            listeners=None,
                        )
                        if spotify_snapshot:
                            uploads.append(("spotify-audience-snapshot.csv", spotify_snapshot))
                        page.goto(analytics_url, wait_until="networkidle", timeout=90_000)
                    _select_spotify_all_time(page)
                    performance_heading = page.get_by_role(
                        "heading", name="Performance", exact=True,
                    )
                    performance_heading.wait_for(state="visible", timeout=30_000)
                    performance_section = performance_heading.locator(
                        "xpath=ancestor::*[.//button[normalize-space()='Export']][1]"
                    )
                    export_control = performance_section.get_by_role(
                        "button", name="Export", exact=True,
                    )
                    apple_range_days = 0
                elif provider == "apple_podcasts":
                    show_link = page.locator(
                        'a[href*="/analytics/show/"][href$="/overview"]'
                    ).first
                    show_link.wait_for(state="visible", timeout=30_000)
                    show_href = show_link.get_attribute("href") or ""
                    if not show_href:
                        raise LocalCollectorError(
                            "The Apple Podcasts show analytics link was unavailable."
                        )
                    show_url = urljoin(page.url, show_href)
                    page.goto(show_url, wait_until="networkidle", timeout=90_000)
                    apple_snapshot = _audience_snapshot_csv(
                        snapshot_date=date.today(),
                        followers=_visible_counter(page, "Followers"),
                        listeners=_visible_counter(page, "Listeners"),
                    )
                    if apple_snapshot:
                        uploads.append(("apple-audience-snapshot.csv", apple_snapshot))
                    episodes_url = show_url.removesuffix("/overview") + "/episodes"
                    page.goto(episodes_url, wait_until="networkidle", timeout=90_000)
                    date_range = page.get_by_role("button", name="Choose a date range")
                    range_match = re.search(r"(\d+)\s+Days", date_range.inner_text(), re.I)
                    if not range_match:
                        raise LocalCollectorError(
                            "The Apple Podcasts analytics date range could not be verified."
                        )
                    apple_range_days = int(range_match.group(1))
                    export_control = page.locator('a[href^="blob:"]').first
                    export_control.wait_for(state="visible", timeout=30_000)
                else:
                    apple_range_days = 0
                    export_control = page.get_by_role(
                        "button", name=re.compile(r"^(Export|Download CSV)$", re.I)
                    ).or_(page.get_by_role("link", name=re.compile(r"^(Export|Download CSV)$", re.I)))
                visible = [export_control.nth(index) for index in range(export_control.count())
                           if export_control.nth(index).is_visible()]
                if not visible:
                    _status(server, token, provider, "error", "export_control_changed")
                    raise LocalCollectorError(
                        "The provider export control was not found; no control was clicked. "
                        "Run a headed sync to review the provider page."
                    )
                if len(visible) > 1 and provider != "spotify":
                    _status(server, token, provider, "error", "multiple_export_controls")
                    raise LocalCollectorError(
                        f"The provider page exposed {len(visible)} export controls; no control was clicked. "
                        "The collector needs a more specific provider selector."
                    )
                # Spotify currently exposes a show-performance export followed by an episode-table
                # export. The first control is the supported daily show-level report.
                export_target = visible[0]
                filename, csv_text = _download_csv(page, export_target, Path(temp_dir))
                if provider == "apple_podcasts":
                    csv_text = _annotate_apple_export(
                        csv_text, range_days=apple_range_days,
                    )
                _validate_provider_export(provider, csv_text)
                uploads.append((filename, csv_text))
                if provider == "spotify":
                    window_start, window_end = _spotify_reporting_window(csv_text)
                    page.get_by_role("tab", name="Audience", exact=True).click()
                    page.get_by_text("Audience breakdowns", exact=True).wait_for(
                        state="visible", timeout=30_000,
                    )
                    # The old tab panel remains briefly in the DOM while Spotify
                    # hydrates the five audience export controls.
                    page.wait_for_timeout(2_500)
                    # Spotify's audience exports are native buttons, but Chromium's
                    # CDP accessibility tree does not consistently expose their role.
                    audience_exports = page.locator("button").filter(
                        has_text=re.compile(r"^Export$")
                    )
                    raw_audience_exports: dict[str, tuple[str, str]] = {}
                    for index in range(audience_exports.count()):
                        control = audience_exports.nth(index)
                        if not control.is_visible():
                            continue
                        export_name, export_csv = _download_csv(
                            page, control, Path(temp_dir), prefix=f"audience-{index}-",
                        )
                        schema = _spotify_dimension_schema(export_csv)
                        if schema:
                            raw_audience_exports[schema] = (export_name, export_csv)
                    expected_exports = {"audience", "gender", "age", "geography", "apps"}
                    if set(raw_audience_exports) != expected_exports:
                        raise LocalCollectorError(
                            "Spotify did not expose every supported audience export; no partial dimension set was uploaded."
                        )
                    recent_start, recent_end = _spotify_reporting_window(
                        raw_audience_exports["audience"][1]
                    )
                    dimension_exports = {}
                    for name in ("gender", "age", "geography", "apps"):
                        export_name, export_csv = raw_audience_exports[name]
                        start, end = (
                            (recent_start, recent_end)
                            if name in {"gender", "age"}
                            else (window_start, window_end)
                        )
                        dimension_exports[name] = (
                            export_name,
                            _annotate_analytics_window(export_csv, start=start, end=end),
                        )
                    uploads.extend(dimension_exports[name] for name in sorted(dimension_exports))
        totals = {"inserted": 0, "duplicates": 0, "submitted": 0}
        for upload_name, upload_csv in uploads:
            result = _post(server, token, "/api/analytics-connectors/local/ingest", {
                "provider": provider,
                "source_reference": upload_name,
                "csv_text": upload_csv,
            })
            for key in totals:
                totals[key] += int(result.get(key) or 0)
        return {"status": "completed", **totals}
    except LocalCollectorError:
        raise
    except Exception as exc:
        try:
            _status(server, token, provider, "error", "collector_run_failed")
        except LocalCollectorError:
            pass
        raise LocalCollectorError("The local provider collection run failed safely.") from exc


def scheduled_sync(
    provider: str, *, server: str, token: str, profile_root: Path, url: str,
    attempts: int = 3, retry_delays: tuple[float, ...] = (20, 90),
) -> dict:
    """Run one quiet, non-overlapping scheduled collection with bounded retries."""
    if attempts < 1:
        raise LocalCollectorError("The scheduled collector requires at least one attempt.")
    lock_dir = profile_root.expanduser().resolve() / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = lock_dir / f"{provider}.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "already_running", "inserted": 0, "duplicates": 0}
        last_error: LocalCollectorError | None = None
        for attempt in range(attempts):
            try:
                return sync_once(
                    provider, server=server, token=token, profile_root=profile_root,
                    url=url, headed=True, quiet_window=True,
                )
            except ReauthenticationRequired:
                # MFA and login are owner actions. Repeating them in the background
                # only creates noise and can trigger provider security controls.
                raise
            except LocalCollectorError as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                delay = retry_delays[min(attempt, len(retry_delays) - 1)] if retry_delays else 0
                time.sleep(max(0, delay))
        raise last_error or LocalCollectorError("The scheduled collector did not complete.")


def _launch_agent_payload(
    provider: str, *, server: str, profile_root: Path, hour: int = 6, minute: int = 15,
    python_executable: str | None = None, logs_dir: Path | None = None,
) -> dict:
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise LocalCollectorError("Schedule hour and minute must form a valid local time.")
    server = _server_url(server)
    logs = (logs_dir or (Path.home() / "Library" / "Logs" / "MirrorTalkAnalyticsCollector")).expanduser()
    label = f"{LAUNCH_AGENT_PREFIX}.{provider}"
    return {
        "Label": label,
        "ProgramArguments": [
            python_executable or sys.executable,
            "-m", "guest_database_manager.local_analytics_collector",
            "scheduled-sync", provider,
            # Provider analytics portals deliberately vary or suppress export controls
            # in headless Chrome. A normal, owner-visible Chrome session also reuses
            # the authentication ceremony that the collector is designed to retain.
            "--headed",
            "--server", server,
            "--profile-root", str(profile_root.expanduser().resolve()),
        ],
        "RunAtLoad": True,
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        # The collector drives an owner-visible provider portal. Marking it as a
        # background process causes macOS to background-throttle Chrome and some
        # portals omit their authenticated export UI under that launch context.
        "ProcessType": "Interactive",
        "LowPriorityIO": True,
        "Nice": 10,
        "ThrottleInterval": 300,
        "StandardOutPath": str(logs / f"{provider}.log"),
        "StandardErrorPath": str(logs / f"{provider}.error.log"),
    }


def install_schedule(
    provider: str, *, server: str, profile_root: Path, hour: int = 6, minute: int = 15,
    launch_agent_dir: Path | None = None, logs_dir: Path | None = None,
    load: bool = True,
) -> Path:
    """Install a daily, user-scoped macOS LaunchAgent for one provider."""
    if sys.platform != "darwin" and load:
        raise LocalCollectorError("Automatic local collector scheduling is currently supported on macOS only.")
    if load and len(_collector_token()) < 32:
        raise LocalCollectorError("Save the Railway collector token in macOS Keychain first.")
    agent_dir = (launch_agent_dir or (Path.home() / "Library" / "LaunchAgents")).expanduser()
    logs = (logs_dir or (Path.home() / "Library" / "Logs" / "MirrorTalkAnalyticsCollector")).expanduser()
    agent_dir.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    path = agent_dir / f"{LAUNCH_AGENT_PREFIX}.{provider}.plist"
    payload = _launch_agent_payload(
        provider, server=server, profile_root=profile_root, hour=hour, minute=minute,
        logs_dir=logs,
    )
    with path.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    path.chmod(0o600)
    if load:
        domain = f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", domain, str(path)], check=False, capture_output=True)
        result = subprocess.run(
            ["launchctl", "bootstrap", domain, str(path)], check=False, capture_output=True, text=True
        )
        if result.returncode != 0:
            raise LocalCollectorError("The daily collector schedule could not be loaded by macOS.")
    return path


def uninstall_schedule(
    provider: str, *, launch_agent_dir: Path | None = None, unload: bool = True,
) -> bool:
    if sys.platform != "darwin" and unload:
        raise LocalCollectorError("Automatic local collector scheduling is currently supported on macOS only.")
    path = (launch_agent_dir or (Path.home() / "Library" / "LaunchAgents")).expanduser() / (
        f"{LAUNCH_AGENT_PREFIX}.{provider}.plist"
    )
    if unload and path.exists():
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}", str(path)],
            check=False, capture_output=True,
        )
    if path.exists():
        path.unlink()
        return True
    return False


def setup_automation(*, server: str, profile_root: Path) -> list[Path]:
    """Perform the one-time owner ceremony and install both daily collectors."""
    if sys.platform != "darwin":
        raise LocalCollectorError("One-command analytics setup is currently supported on macOS only.")
    if len(_collector_token()) < 32:
        save_collector_token()
    token = _collector_token()
    if len(token) < 32:
        raise LocalCollectorError("The collector token was not available after secure setup.")

    paths: list[Path] = []
    for index, (provider, url) in enumerate(DEFAULT_URLS.items()):
        _post(server, token, "/api/analytics-connectors/local/register", {"provider": provider})
        login(provider, profile_root=profile_root, url=url)
        paths.append(install_schedule(
            provider,
            server=server,
            profile_root=profile_root,
            hour=6,
            minute=15 + index * 15,
        ))
    return paths


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mirror Talk local private-analytics collector")
    parser.add_argument(
        "command",
        choices=("setup", "save-token", "login", "sync", "scheduled-sync", "install-schedule", "uninstall-schedule"),
    )
    parser.add_argument("provider", nargs="?", choices=tuple(DEFAULT_URLS))
    parser.add_argument("--server", default=os.environ.get("MIRROR_TALK_PUBLIC_URL", ""))
    parser.add_argument("--url", default="")
    parser.add_argument(
        "--profile-root", type=Path,
        default=Path.home() / "Library" / "Application Support" / "MirrorTalkAnalyticsCollector",
    )
    parser.add_argument("--headed", action="store_true", help="Show the provider page during synchronization")
    parser.add_argument("--hour", type=int, default=6, help="Local hour for the daily scheduled sync")
    parser.add_argument("--minute", type=int, default=15, help="Local minute for the daily scheduled sync")
    return parser


def main() -> None:
    args = create_parser().parse_args()
    if args.command == "setup":
        try:
            paths = setup_automation(server=args.server, profile_root=args.profile_root)
            print(f"Podcast analytics automation is active for {len(paths)} providers.")
        except LocalCollectorError as exc:
            print(f"Collector stopped: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        return
    if args.command == "save-token":
        try:
            save_collector_token()
            print("Collector token saved in macOS Keychain.")
        except LocalCollectorError as exc:
            print(f"Collector stopped: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        return
    if not args.provider:
        raise SystemExit("A provider is required for this command.")
    url = args.url or DEFAULT_URLS[args.provider]
    try:
        if args.command == "login":
            login(args.provider, profile_root=args.profile_root, url=url)
            print(f"Local {args.provider} browser session retained; no password was stored by Mirror Talk.")
            return
        if args.command == "install-schedule":
            path = install_schedule(
                args.provider, server=args.server, profile_root=args.profile_root,
                hour=args.hour, minute=args.minute,
            )
            print(f"Daily {args.provider} synchronization installed: {path}")
            return
        if args.command == "uninstall-schedule":
            removed = uninstall_schedule(args.provider)
            print(f"Daily {args.provider} synchronization {'removed' if removed else 'was not installed'}.")
            return
        runner = scheduled_sync if args.command == "scheduled-sync" else sync_once
        run_options = {
            "server": args.server, "token": _collector_token(),
            "profile_root": args.profile_root, "url": url,
        }
        if runner is sync_once:
            run_options["headed"] = args.headed
        result = runner(args.provider, **run_options)
        if result.get("status") == "already_running":
            print(f"{args.provider} synchronization is already running; this invocation exited quietly.")
            return
        print(f"{args.provider} synchronization completed: {result.get('inserted', 0)} inserted, "
              f"{result.get('duplicates', 0)} duplicates.")
    except LocalCollectorError as exc:
        print(f"Collector stopped: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
