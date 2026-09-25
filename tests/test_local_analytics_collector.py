from pathlib import Path

import pytest

from guest_database_manager.local_analytics_collector import (
    LocalCollectorError,
    _collector_token,
    _profile_path,
    _server_url,
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
