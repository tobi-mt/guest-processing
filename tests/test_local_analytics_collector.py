from contextlib import nullcontext
from pathlib import Path
from datetime import date
from unittest.mock import Mock

import pytest
import requests

import guest_database_manager.local_analytics_collector as collector

from guest_database_manager.local_analytics_collector import (
    BROWSER_CHANNEL_ENV,
    LocalCollectorError,
    ReauthenticationRequired,
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


def test_macos_spotify_login_keeps_attachable_session_resident(tmp_path: Path, monkeypatch) -> None:
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

    assert calls[0][0] == "/Applications/Chrome"
    assert f"--user-data-dir={(tmp_path / 'spotify').resolve()}" in calls[0]
    assert any(argument.startswith("--remote-debugging-port=") for argument in calls[0])
    assert (tmp_path / "spotify" / collector.COLLECTOR_DEBUG_PORT_FILE).is_file()
    assert "leave that window open or minimized" in calls[1]


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
    assert any(argument.startswith("--remote-debugging-port=") for argument in calls[0])
    assert "leave that window open" in calls[1]


def test_login_command_verifies_authentication_with_an_immediate_sync(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    calls = []
    monkeypatch.setattr(
        collector.sys, "argv",
        ["collector", "login", "spotify", "--server", "https://podcast.example",
         "--profile-root", str(tmp_path)],
    )
    monkeypatch.setattr(collector, "login", lambda provider, **kwargs: calls.append(("login", provider)))
    monkeypatch.setattr(collector, "_collector_token", lambda: "x" * 40)
    monkeypatch.setattr(
        collector, "sync_once",
        lambda provider, **kwargs: calls.append(("sync", provider, kwargs["server"], kwargs["headed"]))
        or {"inserted": 4, "duplicates": 6},
    )

    collector.main()

    assert calls == [
        ("login", "spotify"),
        ("sync", "spotify", "https://podcast.example", True),
    ]
    assert "authentication verified and synchronization completed: 4 inserted, 6 duplicates" in capsys.readouterr().out


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
    debug_argument = next(argument for argument in calls[0] if argument.startswith("--remote-debugging-port="))
    debug_port = debug_argument.rsplit("=", 1)[1]
    assert (f"http://127.0.0.1:{debug_port}", 1_000) in calls
    assert "browser.close" in calls
    assert "terminate" in calls


def test_sync_rotates_stale_persisted_debug_port_before_launch(tmp_path: Path, monkeypatch) -> None:
    profile = tmp_path / "spotify"
    profile.mkdir()
    (profile / collector.COLLECTOR_DEBUG_PORT_FILE).write_text("49152", encoding="utf-8")
    calls = []
    context = object()

    class Process:
        poll_count = 0

        def poll(self):
            self.poll_count += 1
            return None if self.poll_count == 1 else 0

    class Browser:
        contexts = [context]

        def close(self):
            calls.append("browser.close")

    class Chromium:
        def connect_over_cdp(self, endpoint, timeout):
            calls.append((endpoint, timeout))
            if endpoint.endswith(":49153"):
                return Browser()
            raise RuntimeError("stale debug port")

    class Playwright:
        chromium = Chromium()

    monkeypatch.setattr(collector, "_native_chrome_executable", lambda: "/Applications/Chrome")
    monkeypatch.setattr(collector, "_available_loopback_port", lambda: 49153)
    monkeypatch.setattr(
        collector.subprocess, "Popen",
        lambda arguments, **kwargs: calls.append(arguments) or Process(),
    )

    with collector._sync_browser_context(Playwright(), profile_path=profile, headless=True) as opened:
        assert opened is context

    assert "--remote-debugging-port=49153" in calls[1]
    assert (profile / collector.COLLECTOR_DEBUG_PORT_FILE).read_text(encoding="utf-8") == "49153"
    assert calls[0] == ("http://127.0.0.1:49152", 5_000)
    assert calls[2] == ("http://127.0.0.1:49153", 1_000)


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


def test_sync_explains_non_attachable_resident_profile(tmp_path: Path, monkeypatch) -> None:
    profile = tmp_path / "spotify"
    profile.mkdir()
    (profile / "SingletonLock").symlink_to("computer-12345")

    class Chromium:
        @staticmethod
        def connect_over_cdp(*args, **kwargs):
            pytest.fail("a profile without DevToolsActivePort cannot be attached")

    class Playwright:
        chromium = Chromium()

    monkeypatch.setattr(collector, "_native_chrome_executable", lambda: "/Applications/Chrome")
    monkeypatch.setattr(
        collector.subprocess, "Popen",
        lambda *args, **kwargs: pytest.fail("a locked profile must not launch a second Chrome"),
    )

    with pytest.raises(LocalCollectorError, match="open without collector access"):
        with collector._sync_browser_context(
            Playwright(), profile_path=profile, headless=False,
        ):
            pass


def test_provider_export_validation_accepts_supported_spotify_reports() -> None:
    collector._validate_provider_export(
        "spotify",
        "Date,Plays & downloads,Plays (on Spotify),Downloads (everywhere else),Audience\n"
        "11/25/2026,10,5,5,8\n",
    )

    episode_report = collector._annotate_spotify_episode_export(
        "Episode name,Publish date,Performance,Plays & downloads\nEpisode,11/25/2026,1,2\n",
        today=date(2026, 11, 27),
    )
    collector._validate_provider_export("spotify", episode_report)
    assert "2026-11-25,2026-11-27" in episode_report


def test_spotify_episode_export_rejects_unreadable_lifetime_start() -> None:
    with pytest.raises(LocalCollectorError, match="unreadable publish date"):
        collector._annotate_spotify_episode_export(
            "Episode name,Publish date,Performance,Plays & downloads\nEpisode,unknown,1,2\n"
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


def test_apple_lifetime_export_uses_earliest_episode_release_date() -> None:
    raw = (
        "Show Name,Episode ID,Episode Title,Release Date,Unique Listeners,"
        "Unique Engaged Listeners,Plays,Average Consumption\n"
        "Mirror Talk,1001,Older Episode,2020-06-12,2,1,30,75%\n"
        "Mirror Talk,1002,Newer Episode,2026-11-24,3,2,10,80%\n"
    )

    annotated = collector._annotate_apple_export(
        raw, range_days=None, today=date(2026, 11, 27),
    )

    assert "2020-06-12,2026-11-27" in annotated
    collector._validate_provider_export("apple_podcasts", annotated)


@pytest.mark.parametrize("status_times_out", [False, True])
def test_sync_reports_uncertain_uploads_when_the_second_report_times_out(
    tmp_path: Path, monkeypatch, status_times_out: bool,
) -> None:
    page = Mock(url="https://podcastsconnect.apple.com/analytics")
    export = Mock()
    export.count.return_value = 1
    export.nth.return_value.is_visible.return_value = True
    show_link = Mock()
    show_link.get_attribute.return_value = "/analytics/show/1/overview"
    password_fields = Mock()
    password_fields.count.return_value = 0
    page.locator.side_effect = [password_fields, Mock(first=show_link), Mock(first=export)]
    monkeypatch.setattr(collector, "_playwright", lambda: nullcontext)
    monkeypatch.setattr(
        collector, "_sync_browser_context", lambda *args, **kwargs: nullcontext(Mock(pages=[page])),
    )
    monkeypatch.setattr(collector, "_select_apple_all_time", Mock())
    monkeypatch.setattr(collector, "_visible_counter", lambda *args: 2)
    monkeypatch.setattr(collector, "_download_csv", lambda *args: (
        "episodes.csv",
        "Show Name,Episode ID,Episode Title,Release Date,Unique Listeners,"
        "Unique Engaged Listeners,Plays,Average Consumption\n"
        "Mirror Talk,1001,Episode,2020-06-12,2,1,3,75%\n",
    ))
    response = Mock(ok=True)
    response.json.return_value = {"inserted": 1, "duplicates": 0, "submitted": 1}
    post = Mock(side_effect=[
        response,
        requests.Timeout("private upload details"),
        requests.Timeout("private status details") if status_times_out else response,
    ])
    monkeypatch.setattr(collector.requests, "post", post)

    with pytest.raises(LocalCollectorError, match="failed during dashboard upload") as failure:
        collector.sync_once(
            "apple_podcasts", server="http://127.0.0.1:8765", token="x" * 32,
            profile_root=tmp_path, url=page.url,
        )

    assert [call.kwargs["json"]["source_reference"] for call in post.call_args_list[:2]] == [
        "apple-audience-snapshot.csv", "episodes.csv",
    ]
    assert post.call_args.kwargs["json"]["error_code"] == "collector_failed:dashboard_upload"
    message = str(failure.value)
    assert "Reports may already have been saved" in message
    assert ("did not acknowledge the failure status" in message) is status_times_out
    assert "private" not in message


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


def test_spotify_audience_composition_schema_is_supported() -> None:
    csv_text = "Date,Total,Returning,New\n11/25/2026,120,45,75\n"

    assert collector._spotify_dimension_schema(csv_text) == "audience"


def test_provider_audience_snapshot_preserves_durable_and_period_counters() -> None:
    snapshot = collector._audience_snapshot_csv(
        snapshot_date=date(2026, 11, 25), followers=4_321, listeners=1_234,
    )

    assert snapshot == "Snapshot Date,Followers,Listeners\n2026-11-25,4321,1234\n"


def test_spotify_home_url_follows_current_show_route() -> None:
    assert collector._spotify_home_url(
        "https://creators.spotify.com/analytics/show/0trwqguYCic32smqh3Ny60/overview"
    ) == "https://creators.spotify.com/home/show/0trwqguYCic32smqh3Ny60"
    assert collector._spotify_home_url("https://creators.spotify.com/login") is None


def test_spotify_all_time_uses_current_semantic_date_range_control() -> None:
    calls = []

    class Locator:
        def __init__(self, *, count=0, visible=False):
            self._count = count
            self._visible = visible

        def count(self):
            return self._count

        def nth(self, _index):
            return self

        def is_visible(self):
            return self._visible

        def click(self):
            calls.append("click")

    trigger = Locator(count=1, visible=True)
    option = Locator(count=1, visible=True)

    class Page:
        def get_by_role(self, role, *, name):
            calls.append((role, name.pattern))
            return trigger

        def get_by_text(self, text, *, exact):
            assert exact is True
            return option if text == "All time" else Locator()

        def wait_for_timeout(self, milliseconds):
            calls.append(("wait", milliseconds))

    collector._select_spotify_all_time(Page())

    assert calls[0] == ("button", "^Select date range$")
    assert calls.count("click") == 2
    assert calls[-1] == ("wait", 3_000)


@pytest.mark.parametrize(
    ("csv_text", "schema"),
    [
        ("Date,Total,Returning,New\n11/24/2026,6,1,5\n", "audience"),
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
        "guest_database_manager.local_analytics_collector", "scheduled-sync",
    ]
    assert "--headed" in payload["ProgramArguments"]
    assert payload["ProcessType"] == "Interactive"
    assert payload["LowPriorityIO"] is True
    assert payload["Nice"] == 10
    assert payload["ThrottleInterval"] == 300
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


def test_scheduled_sync_retries_transient_failures_then_succeeds(tmp_path: Path, monkeypatch) -> None:
    attempts = []
    sleeps = []

    def fake_sync(provider, **kwargs):
        attempts.append((provider, kwargs["headed"], kwargs["quiet_window"]))
        if len(attempts) < 3:
            raise LocalCollectorError("temporary provider failure")
        return {"status": "completed", "inserted": 2, "duplicates": 1}

    monkeypatch.setattr(collector, "sync_once", fake_sync)
    monkeypatch.setattr(collector.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = collector.scheduled_sync(
        "spotify", server="https://guest-processing.example", token="x" * 32,
        profile_root=tmp_path, url="https://creators.spotify.com/analytics",
        retry_delays=(1, 2),
    )

    assert result["status"] == "completed"
    assert attempts == [("spotify", True, True)] * 3
    assert sleeps == [1, 2]


def test_scheduled_sync_never_retries_owner_reauthentication(tmp_path: Path, monkeypatch) -> None:
    attempts = []

    def fake_sync(provider, **kwargs):
        attempts.append(provider)
        raise ReauthenticationRequired("owner action required")

    monkeypatch.setattr(collector, "sync_once", fake_sync)

    with pytest.raises(ReauthenticationRequired, match="owner action"):
        collector.scheduled_sync(
            "apple_podcasts", server="https://guest-processing.example", token="x" * 32,
            profile_root=tmp_path, url="https://podcastsconnect.apple.com/analytics",
            retry_delays=(),
        )

    assert attempts == ["apple_podcasts"]


def test_missing_spotify_breakdowns_do_not_block_available_reports() -> None:
    raw = {
        "geography": ("geo.csv", "Geo,Percentage\nGermany,8\n"),
        "apps": ("apps.csv", "App,Percentage\nSpotify,24.2\n"),
        # Gender and age share the window that only the audience export states.
        "gender": ("gender.csv", "Gender,Percentage\nFemale,12.9\n"),
    }

    uploads, missing = collector._select_spotify_audience_exports(
        raw, window_start=date(2026, 10, 27), window_end=date(2026, 11, 25),
    )

    assert [name for name, _ in uploads] == ["apps.csv", "geo.csv"]
    assert all("2026-10-27,2026-11-25" in csv_text for _, csv_text in uploads)
    assert missing == ["age", "audience", "gender"]


def test_scheduled_sync_retries_partial_runs_and_keeps_the_saved_result(tmp_path: Path, monkeypatch) -> None:
    notices = []
    results = iter([
        {"status": "degraded", "missing_reports": ["age"], "inserted": 4},
        {"status": "degraded", "missing_reports": ["age"], "inserted": 0},
    ])
    monkeypatch.setattr(collector, "sync_once", lambda provider, **kwargs: next(results))
    monkeypatch.setattr(collector.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(collector, "_notify_owner", lambda *args: notices.append(args))

    result = collector.scheduled_sync(
        "spotify", server="https://guest-processing.example", token="x" * 32,
        profile_root=tmp_path, url="https://creators.spotify.com/analytics",
        attempts=2, retry_delays=(0,),
    )

    assert result["status"] == "degraded"
    assert notices == []


def test_scheduled_sync_alerts_the_owner_when_action_or_retries_fail(tmp_path: Path, monkeypatch) -> None:
    notices = []
    monkeypatch.setattr(collector, "_notify_owner", lambda provider, message: notices.append(provider))
    monkeypatch.setattr(collector.time, "sleep", lambda seconds: None)
    common = {
        "server": "https://guest-processing.example", "token": "x" * 32, "profile_root": tmp_path,
        "url": "https://creators.spotify.com/analytics", "retry_delays": (0,),
    }

    def reauth(provider, **kwargs):
        raise ReauthenticationRequired("owner action required")

    monkeypatch.setattr(collector, "sync_once", reauth)
    with pytest.raises(ReauthenticationRequired):
        collector.scheduled_sync("spotify", attempts=3, **common)

    def broken(provider, **kwargs):
        raise LocalCollectorError("temporary provider failure")

    monkeypatch.setattr(collector, "sync_once", broken)
    with pytest.raises(LocalCollectorError):
        collector.scheduled_sync("apple_podcasts", attempts=2, **common)

    monkeypatch.setattr(collector, "sync_once", lambda provider, **kwargs: {"status": "completed"})
    collector.scheduled_sync("spotify", attempts=1, **common)

    assert notices == ["spotify", "apple_podcasts"]


def test_owner_notification_passes_text_as_data_not_applescript(monkeypatch) -> None:
    run = Mock()
    monkeypatch.setattr(collector.sys, "platform", "darwin")
    monkeypatch.setattr(collector.subprocess, "run", run)

    collector._notify_owner("spotify", 'Sign in" & do shell script "x')

    argv = run.call_args.args[0]
    assert argv[-1] == 'Sign in" & do shell script "x'
    assert all('do shell script' not in part for part in argv[:-1])
