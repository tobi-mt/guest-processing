"""Local-only browser collector for provider-limited podcast analytics.

Provider credentials and browser cookies remain in a dedicated local browser profile.
Only downloaded CSV contents are sent to the configured Mirror Talk server.
"""

from __future__ import annotations

import argparse
import getpass
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

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


def login(provider: str, *, profile_root: Path, url: str) -> None:
    """Open a dedicated local browser for a user-controlled login and MFA ceremony."""
    profile = _profile_path(profile_root, provider)
    native_chrome = _native_chrome_executable()
    if native_chrome:
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
    provider: str, *, server: str, token: str, profile_root: Path, url: str, headed: bool = False
) -> dict:
    """Download one explicitly labelled provider CSV and upload it through the safe ingestion boundary."""
    sync_playwright = _playwright()
    try:
        with sync_playwright() as playwright, tempfile.TemporaryDirectory(prefix="mirror-talk-analytics-") as temp_dir:
            context = _launch_browser_context(
                playwright,
                profile_path=_profile_path(profile_root, provider),
                headless=not headed,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            if page.locator('input[type="password"]').count() or re.search(r"login|signin|auth", page.url, re.I):
                context.close()
                _status(server, token, provider, "reauth_required", "provider_login_required")
                raise LocalCollectorError("Provider login or MFA is required. Run the collector login command again.")
            export_control = page.get_by_role(
                "button", name=re.compile(r"^(Export|Download CSV)$", re.I)
            ).or_(page.get_by_role("link", name=re.compile(r"^(Export|Download CSV)$", re.I)))
            visible = [export_control.nth(index) for index in range(export_control.count())
                       if export_control.nth(index).is_visible()]
            if len(visible) != 1:
                context.close()
                _status(server, token, provider, "error", "export_control_changed")
                raise LocalCollectorError(
                    "The provider export control was missing or ambiguous; no control was clicked. "
                    "Run a headed sync to review the provider page."
                )
            with page.expect_download(timeout=90_000) as download_info:
                visible[0].click()
            download = download_info.value
            filename = Path(download.suggested_filename).name
            destination = Path(temp_dir) / filename
            download.save_as(destination)
            csv_text = destination.read_text(encoding="utf-8-sig")
            context.close()
        return _post(server, token, "/api/analytics-connectors/local/ingest", {
            "provider": provider,
            "source_reference": filename,
            "csv_text": csv_text,
        })
    except LocalCollectorError:
        raise
    except Exception as exc:
        try:
            _status(server, token, provider, "error", "collector_run_failed")
        except LocalCollectorError:
            pass
        raise LocalCollectorError("The local provider collection run failed safely.") from exc


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
            "sync", provider,
            "--server", server,
            "--profile-root", str(profile_root.expanduser().resolve()),
        ],
        "RunAtLoad": True,
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "ProcessType": "Background",
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
        choices=("setup", "save-token", "login", "sync", "install-schedule", "uninstall-schedule"),
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
        result = sync_once(
            args.provider,
            server=args.server,
            token=_collector_token(),
            profile_root=args.profile_root,
            url=url,
            headed=args.headed,
        )
        print(f"{args.provider} synchronization completed: {result.get('inserted', 0)} inserted, "
              f"{result.get('duplicates', 0)} duplicates.")
    except LocalCollectorError as exc:
        print(f"Collector stopped: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
