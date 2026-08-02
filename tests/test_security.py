"""Security primitive tests."""

import pytest

from guest_database_manager.security import LoginRateLimiter, SessionError, SessionSigner, role_allows


def test_signed_session_expires_and_rejects_tampering():
    signer = SessionSigner("test-secret", ttl_seconds=60)
    token, claims = signer.issue(role="operator", subject="producer@example.com", now=100)

    assert signer.verify(token, now=159)["sid"] == claims["sid"]
    assert signer.verify(token, now=159)["sub"] == "producer@example.com"
    with pytest.raises(SessionError, match="expired"):
        signer.verify(token, now=160)
    with pytest.raises(SessionError, match="signature"):
        signer.verify(token + "tampered", now=120)


def test_role_hierarchy_is_explicit():
    assert role_allows("admin", "operator")
    assert role_allows("operator", "viewer")
    assert not role_allows("viewer", "operator")


def test_login_limiter_locks_and_resets_client():
    limiter = LoginRateLimiter(max_failures=2, window_seconds=60, lock_seconds=120)
    limiter.record_failure("client", now=100)
    assert limiter.is_allowed("client", now=101)
    limiter.record_failure("client", now=102)
    assert not limiter.is_allowed("client", now=103)
    assert limiter.is_allowed("client", now=223)
    limiter.record_success("client")
    assert limiter.is_allowed("client", now=104)
