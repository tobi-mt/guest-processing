"""Canonical lifecycle contract tests."""

import pytest

from guest_database_manager.lifecycle import LifecycleTransitionError, validate_state, validate_transition


@pytest.mark.parametrize(
    ("domain", "current", "target"),
    [
        ("application", "submitted", "accepted"),
        ("interview", "scheduled", "completed"),
        ("confirmation", "pending", "confirmed"),
        ("production", "editing", "ready"),
        ("production", "recorded", "released"),
        ("production", "released", "editing"),
        ("release", "scheduled", "released"),
        ("release", "unplanned", "released"),
        ("release", "released", "unplanned"),
        ("promotion", "needs_assets", "ready"),
        ("promotion", "unknown", "released"),
        ("communication", "retrying", "sent"),
    ],
)
def test_valid_transitions(domain, current, target):
    assert validate_transition(domain, current, target) == target


def test_same_state_is_idempotent():
    assert validate_transition("release", "scheduled", "scheduled") == "scheduled"


@pytest.mark.parametrize(
    ("domain", "current", "target"),
    [
        ("application", "accepted", "submitted"),
        ("interview", "completed", "scheduled"),
        ("communication", "sent", "retrying"),
    ],
)
def test_invalid_transitions_are_rejected(domain, current, target):
    with pytest.raises(LifecycleTransitionError):
        validate_transition(domain, current, target)


def test_unknown_state_is_rejected():
    with pytest.raises(LifecycleTransitionError, match="Unsupported interview state"):
        validate_state("interview", "maybe")
