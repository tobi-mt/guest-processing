"""Canonical lifecycle states and transition validation."""

from __future__ import annotations

from collections.abc import Mapping


class LifecycleTransitionError(ValueError):
    """Raised when a requested lifecycle transition violates the domain contract."""


TRANSITIONS: Mapping[str, Mapping[str, frozenset[str]]] = {
    "application": {
        "submitted": frozenset({"triage", "needs_information", "accepted", "declined", "withdrawn"}),
        "triage": frozenset({"needs_information", "accepted", "declined", "withdrawn", "submitted"}),
        "needs_information": frozenset({"triage", "accepted", "declined", "withdrawn"}),
        "accepted": frozenset(),
        "declined": frozenset(),
        "withdrawn": frozenset(),
    },
    "interview": {
        "scheduled": frozenset({"completed", "cancelled", "no_show"}),
        "completed": frozenset(),
        "cancelled": frozenset({"scheduled"}),
        "no_show": frozenset({"scheduled", "completed"}),
    },
    "confirmation": {
        "pending": frozenset({"confirmed", "declined", "reschedule_requested"}),
        "confirmed": frozenset({"reschedule_requested", "declined"}),
        "declined": frozenset({"pending"}),
        "reschedule_requested": frozenset({"pending", "confirmed", "declined"}),
    },
    "production": {
        "idea": frozenset({"recorded", "editing", "ready", "released", "archived"}),
        "recorded": frozenset({"idea", "editing", "ready", "released", "archived"}),
        "editing": frozenset({"idea", "recorded", "ready", "released", "archived"}),
        "ready": frozenset({"idea", "recorded", "editing", "released", "archived"}),
        "released": frozenset({"idea", "recorded", "editing", "ready", "archived"}),
        "archived": frozenset({"idea", "recorded", "editing", "ready", "released"}),
    },
    "release": {
        "unplanned": frozenset({"scheduled", "released", "archived"}),
        "scheduled": frozenset({"unplanned", "released", "archived"}),
        "released": frozenset({"unplanned", "scheduled", "archived"}),
        "archived": frozenset({"unplanned", "scheduled", "released"}),
    },
    "promotion": {
        "unknown": frozenset({"needs_assets", "ready", "released", "archived"}),
        "needs_assets": frozenset({"unknown", "ready", "released", "archived"}),
        "ready": frozenset({"unknown", "needs_assets", "released", "archived"}),
        "released": frozenset({"unknown", "needs_assets", "ready", "archived"}),
        "archived": frozenset({"unknown", "needs_assets", "ready", "released"}),
    },
    "communication": {
        "pending": frozenset({"sending", "retrying", "sent", "failed", "dead_letter", "cancelled"}),
        "retrying": frozenset({"sending", "sent", "failed", "dead_letter", "cancelled"}),
        "sending": frozenset({"sent", "retrying", "failed", "dead_letter"}),
        "sent": frozenset(),
        "failed": frozenset({"retrying", "cancelled"}),
        "dead_letter": frozenset({"retrying", "cancelled"}),
        "cancelled": frozenset(),
    },
}


def normalize_state(value: object) -> str:
    return str(value or "").strip().lower()


def validate_state(domain: str, state: object) -> str:
    normalized_domain = normalize_state(domain)
    normalized_state = normalize_state(state)
    domain_transitions = TRANSITIONS.get(normalized_domain)
    if domain_transitions is None:
        raise LifecycleTransitionError(f"Unknown lifecycle domain: {domain}")
    if normalized_state not in domain_transitions:
        raise LifecycleTransitionError(f"Unsupported {normalized_domain} state: {state}")
    return normalized_state


def validate_transition(domain: str, current: object, target: object) -> str:
    """Return normalized target when a transition is valid, otherwise raise."""
    normalized_domain = normalize_state(domain)
    current_state = validate_state(normalized_domain, current)
    target_state = validate_state(normalized_domain, target)
    if current_state == target_state:
        return target_state
    if target_state not in TRANSITIONS[normalized_domain][current_state]:
        raise LifecycleTransitionError(
            f"Invalid {normalized_domain} transition: {current_state} -> {target_state}"
        )
    return target_state
