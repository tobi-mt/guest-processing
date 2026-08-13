"""Curated, source-linked partner signals for the review workspace.

Live discovery is deliberately supplied through configured feeds/providers in production;
these independently researched seed signals give the team a safe initial queue.
"""

from __future__ import annotations

from typing import Any


CURATED_SIGNALS: tuple[dict[str, Any], ...] = (
    {
        "organisation_name": "Institute for Spirituality and Health",
        "website": "https://www.spiritualityandhealth.org",
        "partner_type": "faith_community",
        "research_summary": "Current faith-community leadership cohort connects spirituality, health, prevention, and whole-person well-being.",
        "evidence": (
            {"source_url": "https://www.spiritualityandhealth.org/pressreleasearchive/2026/7/24/cities-for-better-health-houston-welcomes-applications-for-healthy-body-healthy-mind-healthy-faith-community-leadership-cohort-2", "source_title": "Cohort 2 announcement", "published_at": "2026-07-24", "fact_text": "The Institute is recruiting Greater Houston faith communities for a two-year Healthy Body, Healthy Mind, Healthy Faith Community leadership cohort."},
            {"source_url": "https://www.spiritualityandhealth.org/pressreleasearchive/2025/10/31/the-institute-launches-two-year-healthy-body-healthy-mind-healthy-faith-community-leadership-program-for-nine-houston-area-communities-of-faith", "source_title": "Programme launch", "published_at": "2025-10-31", "fact_text": "The Institute launched the two-year leadership programme to build faith communities' capacity for health and well-being work."},
        ),
    },
    {
        "organisation_name": "Church World Service — Restore & Renew",
        "website": "https://cwsglobal.org/restore-and-renew/",
        "partner_type": "faith_community",
        "research_summary": "A timely leadership and renewal programme for refugee, immigrant, and denominational faith leaders.",
        "evidence": (
            {"source_url": "https://cwsglobal.org/restore-and-renew/", "source_title": "Restore & Renew programme", "published_at": "2026", "fact_text": "CWS is offering a 2026 Healing and Leading cohort for refugee and immigrant faith leaders focused on rest, renewal and leadership development."},
            {"source_url": "https://cwsglobal.org/restore-and-renew/", "source_title": "Programme approach", "published_at": "2026", "fact_text": "The nine-month programme includes trauma-informed care, healing-centered engagement, community organizing and leadership development."},
        ),
    },
    {
        "organisation_name": "Baker Publishing Group — Capable",
        "website": "https://bakerpublishinggroup.com",
        "partner_type": "author_publisher",
        "research_summary": "A current Christian parenting and resilience book launch with a clear Mirror Talk alignment.",
        "evidence": (
            {"source_url": "https://bakerpublishinggroup.com/pages/sissy-goff-and-david-thomass-capable-lands-on-nyt-bestsellers-list-and-usa-today-bestsellers-list", "source_title": "Capable press release", "published_at": "2026-05-01", "fact_text": "Bethany House released Capable by Sissy Goff and David Thomas on April 21, 2026, about helping children develop resilience and confidence."},
            {"source_url": "https://newassets.bakerpublishinggroup.com/misc/catalogs/catalog_sp26/SP26_Nonfiction_Catalog.pdf", "source_title": "Spring 2026 catalogue", "published_at": "2026", "fact_text": "The publisher catalogue presents Capable as guidance for parents helping children face challenges and develop resilience."},
        ),
    },
)


def curated_signals() -> list[dict[str, Any]]:
    """Return copy-safe, importable suggestions; no personal contacts are included."""
    return [dict(signal, evidence=[dict(item) for item in signal["evidence"]]) for signal in CURATED_SIGNALS]
