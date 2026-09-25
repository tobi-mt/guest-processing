"""Local-only browser collector for provider-limited podcast analytics.

Provider credentials and browser cookies remain in a dedicated local browser profile.
Only downloaded CSV contents are sent to the configured Mirror Talk server.
"""

from __future__ import annotations

import argparse
import os
import re
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


def login(provider: str, *, profile_root: Path, url: str) -> None:
    """Open a dedicated local browser for a user-controlled login and MFA ceremony."""
    sync_playwright = _playwright()
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(_profile_path(profile_root, provider)), headless=False, accept_downloads=True
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
            context = playwright.chromium.launch_persistent_context(
                str(_profile_path(profile_root, provider)), headless=not headed, accept_downloads=True
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


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mirror Talk local private-analytics collector")
    parser.add_argument("command", choices=("login", "sync"))
    parser.add_argument("provider", choices=tuple(DEFAULT_URLS))
    parser.add_argument("--server", default=os.environ.get("MIRROR_TALK_PUBLIC_URL", ""))
    parser.add_argument("--url", default="")
    parser.add_argument(
        "--profile-root", type=Path,
        default=Path.home() / "Library" / "Application Support" / "MirrorTalkAnalyticsCollector",
    )
    parser.add_argument("--headed", action="store_true", help="Show the provider page during synchronization")
    return parser


def main() -> None:
    args = create_parser().parse_args()
    url = args.url or DEFAULT_URLS[args.provider]
    try:
        if args.command == "login":
            login(args.provider, profile_root=args.profile_root, url=url)
            print(f"Local {args.provider} browser session retained; no password was stored by Mirror Talk.")
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
