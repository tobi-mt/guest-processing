"""Reusable Mirror Talk partnership objectives for grounded pitch generation."""

from __future__ import annotations

from typing import Any, Dict, List


PITCH_TEMPLATES: tuple[Dict[str, Any], ...] = (
    {"id": "editorial_conversation", "name": "Editorial conversation", "objective": "Invite a relevant leader or expert into a thoughtful Mirror Talk episode.", "value": "A substantive conversation that serves listeners and gives the partner's work credible depth."},
    {"id": "co_marketing", "name": "Co-marketing collaboration", "objective": "Explore a jointly promoted episode, resource, or campaign.", "value": "Shared distribution around a genuinely aligned theme without inflated audience claims."},
    {"id": "community_impact", "name": "Community impact", "objective": "Connect Mirror Talk storytelling with a mission-led programme or community initiative.", "value": "Human stories, practical insight, and a clear next step for listeners who care about the issue."},
    {"id": "series_partnership", "name": "Thematic series partnership", "objective": "Explore a small, focused series around a timely shared theme.", "value": "More depth than a one-off mention, with each episode designed around listener usefulness."},
    {"id": "sponsorship_exploration", "name": "Values-aligned sponsorship", "objective": "Open a careful conversation about supporting relevant Mirror Talk programming.", "value": "Transparent, audience-respecting integration with editorial independence preserved."},
)


def list_pitch_templates() -> List[Dict[str, Any]]:
    return [dict(item) for item in PITCH_TEMPLATES]


def get_pitch_template(template_id: str) -> Dict[str, Any]:
    return next((dict(item) for item in PITCH_TEMPLATES if item["id"] == template_id), dict(PITCH_TEMPLATES[0]))
