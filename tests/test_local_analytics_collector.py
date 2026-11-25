from pathlib import Path

import pytest

import guest_database_manager.local_analytics_collector as collector

from guest_database_manager.local_analytics_collector import (
    LocalCollectorError,
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
