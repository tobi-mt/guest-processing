"""Deterministic visual, responsive, contrast, and keyboard regression checks."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = {
    "interface-states": ROOT / "tests" / "visual_fixtures" / "interface_states.html",
    "booking-states": ROOT / "tests" / "visual_fixtures" / "booking_states.html",
    "intake-states": ROOT / "tests" / "visual_fixtures" / "intake_states.html",
}
BASELINES = ROOT / "tests" / "visual_baselines"
VIEWPORTS = {"mobile": (390, 844), "tablet": (820, 1000), "desktop": (1280, 900)}
PRIMARY_ROUTES = ("/dashboard", "/operations", "/planning", "/insights", "/availability", "/partners", "/accounts", "/account-settings", "/book", "/intake")


@pytest.fixture(scope="module")
def visual_server(tmp_path_factory):
    work = tmp_path_factory.mktemp("visual-web")
    database = work / "guest_database.db"
    shutil.copy2(ROOT / "guest_database.db", database)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(ROOT / "src"),
        "MIRROR_TALK_DASHBOARD_USERNAME": "visual-qa",
        "MIRROR_TALK_DASHBOARD_PASSWORD": "local-only",
        "MIRROR_TALK_DASHBOARD_SESSION_SECRET": "visual-regression-secret",
        "MIRROR_TALK_DASHBOARD_ROLE": "super_admin",
    })
    process = subprocess.Popen(
        [sys.executable, "-c", (
            "from guest_database_manager.web_interface import run_web_interface; "
            f"run_web_interface(port={port}, db_path={str(database)!r}, open_browser=False)"
        )], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            urllib.request.urlopen(f"{base}/healthz", timeout=.25)
            break
        except Exception:
            if process.poll() is not None:
                raise RuntimeError("Visual regression web server exited during startup")
            time.sleep(.05)
    else:
        process.terminate()
        raise RuntimeError("Visual regression web server did not become ready")
    yield base
    process.terminate()
    process.wait(timeout=5)


def _difference_ratio(expected: Path, actual: Path) -> float:
    with Image.open(expected).convert("RGB") as left, Image.open(actual).convert("RGB") as right:
        assert left.size == right.size
        stat = ImageStat.Stat(ImageChops.difference(left, right))
        return sum(stat.mean) / (255 * 3)


@pytest.mark.parametrize(("fixture_name", "fixture"), FIXTURES.items())
@pytest.mark.parametrize(("name", "size"), VIEWPORTS.items())
def test_interface_state_gallery_matches_visual_baseline(fixture_name, fixture, name, size, tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    expected = BASELINES / f"{fixture_name}-{name}.png"
    actual = tmp_path / expected.name
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": size[0], "height": size[1]}, device_scale_factor=1)
        page.goto(fixture.as_uri(), wait_until="load")
        page.screenshot(path=str(actual), full_page=True, animations="disabled")
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") == 0
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement !== document.body")
        browser.close()

    if os.getenv("UPDATE_VISUAL_BASELINES") == "1" or not expected.exists():
        BASELINES.mkdir(exist_ok=True)
        expected.write_bytes(actual.read_bytes())
    assert _difference_ratio(expected, actual) <= 0.002


@pytest.mark.parametrize("fixture", FIXTURES.values(), ids=FIXTURES.keys())
def test_state_gallery_text_contrast_meets_wcag_aa(fixture):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(fixture.as_uri(), wait_until="load")
        failures = page.evaluate("""
          () => {
            const channel = value => { value /= 255; return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4; };
            const luminance = rgb => .2126 * channel(rgb[0]) + .7152 * channel(rgb[1]) + .0722 * channel(rgb[2]);
            const parse = value => (value.match(/[\\d.]+/g) || []).slice(0, 3).map(Number);
            const opaqueBackground = element => {
              for (let node = element; node; node = node.parentElement) {
                const color = getComputedStyle(node).backgroundColor;
                const parts = color.match(/[\\d.]+/g)?.map(Number) || [];
                if (parts.length >= 3 && (parts[3] ?? 1) >= .9) return parts.slice(0, 3);
              }
              return [13, 11, 17];
            };
            return [...document.querySelectorAll('body *')].filter(el => {
              if (!el.childNodes.length || ![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return false;
              const style = getComputedStyle(el); if (style.display === 'none' || style.visibility === 'hidden') return false;
              const fg = parse(style.color), bg = opaqueBackground(el); if (fg.length < 3) return false;
              const [hi, lo] = [luminance(fg), luminance(bg)].sort((a,b) => b-a);
              const ratio = (hi + .05) / (lo + .05);
              const large = parseFloat(style.fontSize) >= 24 || (parseFloat(style.fontSize) >= 18.66 && Number(style.fontWeight) >= 700);
              el.dataset.contrastRatio = ratio.toFixed(2);
              return ratio < (large ? 3 : 4.5);
            }).map(el => ({text: el.textContent.trim().slice(0, 80), ratio: el.dataset.contrastRatio, className: el.className}));
          }
        """)
        browser.close()
    assert failures == []


def test_button_labels_never_resolve_to_invisible_text():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(FIXTURES["interface-states"].as_uri(), wait_until="load")
        failures = page.evaluate("""() => [...document.querySelectorAll('button')].flatMap(button => {
          if (!button.textContent.trim() || getComputedStyle(button).display === 'none') return [];
          const style = getComputedStyle(button);
          const invisible = style.color === style.backgroundColor || style.color === 'transparent' ||
            style.webkitTextFillColor === 'transparent' || Number(style.opacity) === 0;
          return invisible ? [{text: button.textContent.trim(), color: style.color,
            background: style.backgroundColor, fill: style.webkitTextFillColor}] : [];
        })""")
        browser.close()
    assert failures == []


def test_primary_page_workflows_fit_mobile_tablet_and_desktop(visual_server):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        console_errors = []
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        page.goto(f"{visual_server}/dashboard-login")
        page.get_by_label("Username").fill("visual-qa")
        page.get_by_label("Password").fill("local-only")
        page.get_by_role("button", name="Sign In").click()
        page.wait_for_url(f"{visual_server}/dashboard")

        failures = []
        for viewport_name, (width, height) in VIEWPORTS.items():
            page.set_viewport_size({"width": width, "height": height})
            for route in PRIMARY_ROUTES:
                page.goto(f"{visual_server}{route}", wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => !document.body.classList.contains('page-loading') && "
                    "!document.body.classList.contains('booking-loading')",
                    timeout=5000,
                )
                overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
                if overflow > 0:
                    failures.append(f"{viewport_name} {route}: {overflow}px horizontal overflow")
                utility_overlap = page.evaluate("""() => {
                  const utility = document.querySelector('.workspace-utility-bar');
                  const content = document.querySelector('.page-shell')?.firstElementChild;
                  if (!utility || !content || getComputedStyle(utility).display === 'none') return false;
                  const a = utility.getBoundingClientRect(), b = content.getBoundingClientRect();
                  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
                }""")
                if utility_overlap:
                    failures.append(f"{viewport_name} {route}: workspace tools overlap page content")
                mobile_nav_height = page.evaluate("""() => {
                  const nav = document.querySelector('.mobile-workspace-nav');
                  return !nav || getComputedStyle(nav).display === 'none' ? 0 : nav.getBoundingClientRect().height;
                }""")
                if mobile_nav_height > 64:
                    failures.append(f"{viewport_name} {route}: mobile navigation wrapped to {mobile_nav_height:.0f}px")
                if viewport_name == "mobile" and route in ("dashboard", "operations", "planning"):
                    queue_items = page.locator("#workspace-action-queue .action-queue-item").count()
                    if queue_items > 3:
                        failures.append(f"{viewport_name} {route}: action queue shows {queue_items} items before expansion")
                    first_is_hero = page.evaluate(
                        "document.querySelector('.page-shell')?.firstElementChild?.classList.contains('hero')"
                    )
                    if not first_is_hero:
                        failures.append(f"{viewport_name} {route}: workspace identity is not first")
                timing = page.evaluate("""() => {
                  const nav = performance.getEntriesByType('navigation')[0];
                  return {dom: nav.domContentLoadedEventEnd, load: nav.loadEventEnd};
                }""")
                if timing["dom"] > 2000 or timing["load"] > 3000:
                    failures.append(
                        f"{viewport_name} {route}: slow local navigation "
                        f"({timing['dom']:.0f}ms DOM, {timing['load']:.0f}ms load)"
                    )
                page.keyboard.press("Tab")
                focused = page.evaluate("document.activeElement !== document.body")
                if not focused:
                    failures.append(f"{viewport_name} {route}: keyboard focus did not enter the page")
                invisible_buttons = page.evaluate("""() => [...document.querySelectorAll('button')].flatMap(button => {
                  const style = getComputedStyle(button);
                  if (!button.textContent.trim() || style.display === 'none') return [];
                  return style.color === style.backgroundColor || style.color === 'transparent' ||
                    style.webkitTextFillColor === 'transparent' || Number(style.opacity) === 0
                    ? [button.textContent.trim()] : [];
                })""")
                if invisible_buttons:
                    failures.append(f"{viewport_name} {route}: invisible button labels {invisible_buttons}")
        browser.close()
    failures.extend(f"browser console: {error}" for error in console_errors)
    assert failures == []


def test_public_account_entry_pages_are_responsive_and_keyboard_accessible(visual_server):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page()
        failures = []
        for viewport_name, (width, height) in VIEWPORTS.items():
            page.set_viewport_size({"width": width, "height": height})
            for route in ("/dashboard-login", "/account-recovery?token=visual-fixture"):
                page.goto(f"{visual_server}{route}", wait_until="load")
                overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
                if overflow > 0:
                    failures.append(f"{viewport_name} {route}: {overflow}px horizontal overflow")
                page.keyboard.press("Tab")
                if not page.evaluate("document.activeElement !== document.body"):
                    failures.append(f"{viewport_name} {route}: keyboard focus did not enter the page")
        browser.close()
    assert failures == []


def test_reach_keeps_expanded_chart_and_episode_table_inside_a_narrow_viewport(visual_server):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 320, "height": 844})
        page.route("**/api/podcast-insights", lambda route: route.fulfill(json={
            "provider_strength": [{"provider": "spotify", "freshness": "current",
                                   "period_start": "2026-11-25", "period_end": "2026-11-26"}],
            "analytics_connectors": {
                "local_collectors": {"connections": {"spotify": {"enabled": True, "status": "error"}}},
                "openpodcast": {"status": "error", "last_error_code": "endpoint_failed:episodesDailyMetrics"},
                "public_ratings": {"status": "waiting", "last_run_at": None},
            },
            "daily_trends": {"spotify": [
                {"period": "2026-10-31", "downloads": 5, "plays": 7},
                {"period": "2026-11-01", "downloads": 6, "plays": 8},
            ]},
            "top_platform_content": [{
                "provider": "spotify", "title": "QA episode", "period_end": "2026-10-01",
                "metrics": {"plays_downloads": 10}, "freshness": "stale",
            }],
        }))
        page.goto(f"{visual_server}/insights")
        page.get_by_label("Username").fill("visual-qa")
        page.get_by_label("Password").fill("local-only")
        page.get_by_role("button", name="Sign In").click()
        page.wait_for_url(f"{visual_server}/insights")

        trend = page.locator("#overall-performance-trend")
        trend.get_by_text("View exact values").click()
        assert trend.locator("table").is_visible()
        page.get_by_text("Explore performance", exact=True).click()
        assert page.locator("#insights-quality").get_by_text("Collection incomplete").is_visible()
        assert "OpenPodcast: sync failed" in page.locator("#insights-quality").inner_text()
        assert page.locator("#provider-strength").get_by_text("Sync failed").is_visible()
        assert page.locator("#public-ratings").get_by_text("Awaiting first ratings check").is_visible()
        badge = page.get_by_text("Refresh needed", exact=True)
        assert badge.is_visible()
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") == 0
        assert badge.evaluate("el => el.getClientRects().length") == 1
        browser.close()
