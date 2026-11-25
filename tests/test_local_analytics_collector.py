from pathlib import Path
from datetime import date

import pytest

import guest_database_manager.local_analytics_collector as collector

from guest_database_manager.local_analytics_collector import (
    BROWSER_CHANNEL_ENV,
    LocalCollectorError,
    _browser_channel,
    _collector_token,
    _launch_agent_payload,
    _profile_path,
    _server_url,
    install_schedule,
    uninstall_schedule,
)


def test_collector_requires_https_except_loopback() -> None:
    assert _server_url("https://guest-processing.example/") == "https://guest-processing.example"
    assert _server_url("http://127.0.0.1:8768") == "http://127.0.0.1:8768"
    with pytest.raises(LocalCollectorError, match="must use HTTPS"):
        _server_url("http://public.example")


def test_collector_profile_is_provider_scoped_and_owner_only(tmp_path: Path) -> None:
    path = _profile_path(tmp_path, "spotify")

    assert path == (tmp_path / "spotify").resolve()
    assert path.stat().st_mode & 0o777 == 0o700


def test_collector_prefers_environment_token(monkeypatch) -> None:
    monkeypatch.setenv("MIRROR_TALK_ANALYTICS_COLLECTOR_TOKEN", "environment-secret")
    assert _collector_token() == "environment-secret"


def test_collector_browser_channel_can_use_installed_chrome_or_explicit_bundled_browser(
    monkeypatch,
) -> None:
    monkeypatch.setenv(BROWSER_CHANNEL_ENV, "chrome-beta")
    assert _browser_channel() == "chrome-beta"
    monkeypatch.setenv(BROWSER_CHANNEL_ENV, "bundled")
    assert _browser_channel() is None


def test_login_uses_native_chrome_without_playwright_automation(tmp_path: Path, monkeypatch) -> None:
    calls = []

    class Process:
        def poll(self):
            return None

        def terminate(self):
            calls.append("terminate")

        def wait(self, timeout):
            calls.append(("wait", timeout))

    monkeypatch.setattr(collector, "_native_chrome_executable", lambda: "/Applications/Chrome")
    monkeypatch.setattr(collector.sys, "platform", "linux")
    monkeypatch.setattr(
        collector.subprocess, "Popen",
        lambda arguments, **kwargs: calls.append(arguments) or Process(),
    )
    monkeypatch.setattr("builtins.input", lambda prompt: calls.append(prompt) or "")

    collector.login("spotify", profile_root=tmp_path, url="https://creators.spotify.com/analytics")

    assert calls[0][0] == "/Applications/Chrome"
    assert f"--user-data-dir={(tmp_path / 'spotify').resolve()}" in calls[0]
    assert "terminate" in calls


def test_macos_spotify_login_forces_a_separate_chrome_instance(tmp_path: Path, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(collector.sys, "platform", "darwin")
    monkeypatch.setattr(collector, "_native_chrome_executable", lambda: "/Applications/Chrome")
    monkeypatch.setattr(
        collector.subprocess, "Popen",
        lambda arguments, **kwargs: calls.append(arguments) or object(),
    )
    monkeypatch.setattr("builtins.input", lambda prompt: calls.append(prompt) or "")

    collector.login(
        "spotify", profile_root=tmp_path,
        url="https://creators.spotify.com/analytics",
    )

    assert calls[0][:4] == ["/usr/bin/open", "-na", "Google Chrome", "--args"]
    assert f"--user-data-dir={(tmp_path / 'spotify').resolve()}" in calls[0]
    assert "close that window" in calls[1]


def test_macos_apple_login_keeps_session_browser_resident(tmp_path: Path, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(collector.sys, "platform", "darwin")
    monkeypatch.setattr(collector, "_native_chrome_executable", lambda: "/Applications/Chrome")
    monkeypatch.setattr(
        collector.subprocess, "Popen",
        lambda arguments, **kwargs: calls.append(arguments) or object(),
    )
    monkeypatch.setattr("builtins.input", lambda prompt: calls.append(prompt) or "")

    collector.login(
        "apple_podcasts", profile_root=tmp_path,
        url="https://podcastsconnect.apple.com/analytics",
    )

    assert calls[0][0] == "/Applications/Chrome"
    assert f"--user-data-dir={(tmp_path / 'apple_podcasts').resolve()}" in calls[0]
    assert "--remote-debugging-port=0" in calls[0]
    assert "leave that window open" in calls[1]


def test_sync_attaches_to_native_chrome_profile_over_cdp(tmp_path: Path, monkeypatch) -> None:
    calls = []
    profile = tmp_path / "spotify"
    profile.mkdir()

    class Process:
        def __init__(self):
            (profile / "DevToolsActivePort").write_text("49152\n/browser-id\n", encoding="utf-8")
            self.running = True

        def poll(self):
            return None if self.running else 0

        def terminate(self):
            calls.append("terminate")
            self.running = False

        def wait(self, timeout):
            calls.append(("wait", timeout))
            return 0

    context = object()

    class Browser:
        contexts = [context]

        def close(self):
            calls.append("browser.close")

    class Chromium:
        def connect_over_cdp(self, endpoint, timeout):
            calls.append((endpoint, timeout))
            return Browser()

    class Playwright:
        chromium = Chromium()

    monkeypatch.setattr(collector, "_native_chrome_executable", lambda: "/Applications/Chrome")
    monkeypatch.setattr(
        collector.subprocess, "Popen",
        lambda arguments, **kwargs: calls.append(arguments) or Process(),
    )

    with collector._sync_browser_context(
        Playwright(), profile_path=profile, headless=True,
    ) as opened_context:
        assert opened_context is context

    assert calls[0][0] == "/Applications/Chrome"
    assert f"--user-data-dir={profile}" in calls[0]
    assert "--headless=new" in calls[0]
    assert ("http://127.0.0.1:49152", 20_000) in calls
    assert "browser.close" in calls
    assert "terminate" in calls


def test_sync_reuses_resident_browser_without_closing_it(tmp_path: Path, monkeypatch) -> None:
    profile = tmp_path / "apple_podcasts"
    profile.mkdir()
    (profile / "DevToolsActivePort").write_text("49153\n/browser-id\n", encoding="utf-8")
    calls = []
    context = object()

    class Browser:
        contexts = [context]

        def close(self):
            calls.append("browser.close")

    class Chromium:
        def connect_over_cdp(self, endpoint, timeout):
            calls.append((endpoint, timeout))
            return Browser()

    class Playwright:
        chromium = Chromium()

    monkeypatch.setattr(collector, "_native_chrome_executable", lambda: "/Applications/Chrome")
    monkeypatch.setattr(
        collector.subprocess, "Popen",
        lambda *args, **kwargs: pytest.fail("resident sessions must not launch another browser"),
    )

    with collector._sync_browser_context(
        Playwright(), profile_path=profile, headless=True,
    ) as opened_context:
        assert opened_context is context

    assert calls == [("http://127.0.0.1:49153", 5_000)]


def test_provider_export_validation_rejects_the_wrong_spotify_report() -> None:
    collector._validate_provider_export(
        "spotify",
        "Date,Plays & downloads,Plays (on Spotify),Downloads (everywhere else),Audience\n"
        "11/25/2026,10,5,5,8\n",
    )

    with pytest.raises(LocalCollectorError, match="different analytics report"):
        collector._validate_provider_export(
            "spotify",
            "Episode name,Publish date,Performance,Plays & downloads\nEpisode,11/25/2026,1,2\n",
        )


def test_apple_export_annotation_makes_the_implicit_window_explicit() -> None:
    raw = (
        "Show Name,Episode ID,Episode Title,Release Date,Unique Listeners,"
        "Unique Engaged Listeners,Plays,Average Consumption\n"
        "Mirror Talk,1001,Episode,2026-11-24,2,1,3,75%\n"
    )

    annotated = collector._annotate_apple_export(
        raw, range_days=60, today=date(2026, 11, 25),
    )

    assert "Analytics Period Start,Analytics Period End" in annotated
    assert "2026-09-27,2026-11-25" in annotated
    collector._validate_provider_export("apple_podcasts", annotated)


def test_spotify_dimension_exports_receive_the_verified_performance_window() -> None:
    performance = (
        "Date,Plays & downloads,Plays (on Spotify),Downloads (everywhere else),Audience\n"
        "10/27/2026,10,2,8,6\n11/25/2026,20,4,16,9\n"
    )
    start, end = collector._spotify_reporting_window(performance)
    annotated = collector._annotate_analytics_window(
        "App,Percentage\nApple Podcasts,8.7\nSpotify,24.2\n",
        start=start, end=end,
    )

    assert (start, end) == (date(2026, 10, 27), date(2026, 11, 25))
    assert collector._spotify_dimension_schema(annotated) == "apps"
    assert "2026-10-27,2026-11-25" in annotated


@pytest.mark.parametrize(
    ("csv_text", "schema"),
    [
        ("Gender,Percentage\nFemale,12.9\n", "gender"),
        ("Age,Total percentage\n28-34,68.8\n", "age"),
        ("Geo,Percentage\nGermany,8\n", "geography"),
        ("App,Percentage\nAudible,3.5\n", "apps"),
    ],
)
def test_spotify_dimension_exports_are_classified_by_schema(csv_text: str, schema: str) -> None:
    assert collector._spotify_dimension_schema(csv_text) == schema


def test_launch_agent_runs_daily_sync_without_embedding_the_secret(tmp_path: Path) -> None:
    payload = _launch_agent_payload(
        "spotify", server="https://guest-processing.example",
        profile_root=tmp_path / "profiles", hour=7, minute=30,
        python_executable="/opt/mirror-talk/bin/python", logs_dir=tmp_path / "logs",
    )

    assert payload["StartCalendarInterval"] == {"Hour": 7, "Minute": 30}
    assert payload["ProgramArguments"][:4] == [
        "/opt/mirror-talk/bin/python", "-m",
        "guest_database_manager.local_analytics_collector", "sync",
    ]
    assert "--headed" in payload["ProgramArguments"]
    assert payload["ProcessType"] == "Interactive"
    assert "environment-secret" not in repr(payload)
    assert payload["RunAtLoad"] is True


def test_schedule_install_and_remove_are_user_scoped_and_reversible(tmp_path: Path) -> None:
    launch_agents = tmp_path / "LaunchAgents"
    path = install_schedule(
        "apple_podcasts", server="https://guest-processing.example",
        profile_root=tmp_path / "profiles", launch_agent_dir=launch_agents,
        logs_dir=tmp_path / "logs", load=False,
    )

    assert path.parent == launch_agents
    assert path.stat().st_mode & 0o777 == 0o600
    assert uninstall_schedule("apple_podcasts", launch_agent_dir=launch_agents, unload=False) is True
    assert not path.exists()


def test_one_command_setup_registers_logs_in_and_schedules_both_providers(
    tmp_path: Path, monkeypatch
) -> None:
    token = "collector-token-with-at-least-thirty-two-characters"
    posts = []
    logins = []
    schedules = []
    monkeypatch.setattr(collector.sys, "platform", "darwin")
    monkeypatch.setattr(collector, "_collector_token", lambda: token)
    monkeypatch.setattr(
        collector, "_post",
        lambda server, supplied_token, path, payload: posts.append(
            (server, supplied_token, path, payload)
        ) or {"status": "waiting"},
    )
    monkeypatch.setattr(
        collector, "login",
        lambda provider, **kwargs: logins.append((provider, kwargs["url"])),
    )

    def fake_install(provider, **kwargs):
        schedules.append((provider, kwargs["hour"], kwargs["minute"]))
        return tmp_path / f"{provider}.plist"

    monkeypatch.setattr(collector, "install_schedule", fake_install)

    paths = collector.setup_automation(
        server="https://guest-processing.example", profile_root=tmp_path / "profiles"
    )

    assert [item[3]["provider"] for item in posts] == ["spotify", "apple_podcasts"]
    assert all(item[2] == "/api/analytics-connectors/local/register" for item in posts)
    assert [item[0] for item in logins] == ["spotify", "apple_podcasts"]
    assert schedules == [("spotify", 6, 15), ("apple_podcasts", 6, 30)]
    assert paths == [tmp_path / "spotify.plist", tmp_path / "apple_podcasts.plist"]
