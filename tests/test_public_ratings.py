import json
from datetime import timedelta

import pytest

from guest_database_manager.growth_intelligence import GrowthIntelligence, GrowthIntelligenceError, _metric_value
from guest_database_manager.podcast_insights import PodcastInsights
from guest_database_manager.public_ratings import (
    PROVIDER,
    PublicRatingsCollector,
    PublicRatingsError,
    _now,
    parse_apple_rating,
)


def _page(storefront: str, value="4.9", count=65, show_id="1518394292") -> str:
    payload = {
        "@context": "https://schema.org", "@type": "PodcastSeries",
        "url": f"https://podcasts.apple.com/{storefront}/podcast/mirror-talk/id{show_id}",
        "aggregateRating": {"@type": "AggregateRating", "ratingValue": value, "reviewCount": count},
    }
    return f'<script type="application/ld+json">{json.dumps(payload)}</script>'


def test_apple_rating_requires_the_requested_storefront_and_show():
    assert parse_apple_rating(_page("de"), storefront="de")["rating_count"] == 65
    # Apple silently redirects unknown storefronts to the US page.
    assert parse_apple_rating(_page("us"), storefront="xx") is None
    assert parse_apple_rating(_page("de", show_id="1"), storefront="de") is None
    assert parse_apple_rating("<html>no ratings yet</html>", storefront="fr") is None
    with pytest.raises(PublicRatingsError):
        parse_apple_rating(_page("de", value="7"), storefront="de")


def test_public_ratings_are_collected_idempotently_and_kept_out_of_reach(temp_db):
    GrowthIntelligence(temp_db.db_path).record_observations([
        {"provider": "spotify", "metric_name": "plays", "metric_value": 40,
         "period_start": "2026-11-01", "period_end": "2026-11-28", "source_reference": "spotify.csv"},
        {"provider": "spotify", "metric_name": "country_france", "metric_value": 30,
         "period_start": "2026-11-01", "period_end": "2026-11-28", "source_reference": "geo.csv"},
    ], actor="test")
    pages = {"us": _page("us", "4.9", 65), "ng": _page("ng", "5", 9)}
    calls = []

    def fetch(url):
        storefront = url.split("/")[3]
        calls.append(storefront)
        return 200, url, pages.get(storefront, "<html></html>")

    collector = PublicRatingsCollector(temp_db.db_path, fetch=fetch)
    assert "fr" in collector.storefronts()

    first = collector.run(actor="automation")
    calls.clear()
    assert collector.run(actor="automation")["status"] == "fresh"
    assert calls == []
    second = collector.run(actor="automation", force=True)

    assert (first["inserted"], first["storefronts_rated"]) == (4, 2)
    assert (second["inserted"], second["duplicates"]) == (0, 4)
    dashboard = PodcastInsights(temp_db.db_path).dashboard()
    ratings = dashboard["public_ratings"]
    assert ratings["total_ratings"] == 74
    assert ratings["weighted_average"] == pytest.approx((4.9 * 65 + 5 * 9) / 74, abs=0.01)
    assert "France" in ratings["unrated_audience_markets"]
    assert PROVIDER not in json.dumps(dashboard["provider_strength"])
    # Storefront country codes must not count as countries reached.
    assert dashboard["summary"]["topline"]["countries_reached"] == 1


def test_missing_primary_storefront_rating_is_a_format_change_with_backoff(temp_db):
    collector = PublicRatingsCollector(temp_db.db_path, fetch=lambda url: (200, url, "<html></html>"))

    result = collector.run(actor="automation")

    assert result["status"] == "error"
    assert collector.status()["last_error_code"] == "format_changed"
    assert not collector.due()
    assert collector.due(now=_now() + timedelta(hours=7))


def test_growth_intelligence_rejects_impossible_rating():
    with pytest.raises(GrowthIntelligenceError, match="cannot exceed 5"):
        _metric_value("rating_average", 5.5)


def test_ratings_run_stops_fetching_when_its_time_budget_is_spent(temp_db, monkeypatch):
    import guest_database_manager.public_ratings as ratings

    calls = []
    monkeypatch.setattr(ratings, "RUN_BUDGET_SECONDS", 0)

    result = PublicRatingsCollector(
        temp_db.db_path, fetch=lambda url: calls.append(url) or (200, url, _page("us")),
    ).run(actor="automation")

    assert calls == []
    assert (result["status"], result["error_code"]) == ("error", "unreachable")


def test_every_rated_and_audience_market_is_a_storefront_without_a_cap(temp_db):
    import pycountry

    countries = [c for c in pycountry.countries if c.name.isascii() and c.name.isalpha()][:45]
    GrowthIntelligence(temp_db.db_path).record_observations([
        {"provider": "spotify", "metric_name": f"country_{country.name.lower()}", "metric_value": 5,
         "period_start": "2026-11-01", "period_end": "2026-11-28", "source_reference": "geo.csv"}
        for country in countries
    ], actor="test")

    storefronts = PublicRatingsCollector(temp_db.db_path, fetch=lambda url: (404, url, "")).storefronts()

    assert len(storefronts) > 30
    assert {country.alpha_2.lower() for country in countries} <= set(storefronts)


def test_unreached_storefronts_are_checked_first_and_retried_early(temp_db, monkeypatch):
    import guest_database_manager.public_ratings as ratings

    def offline_after_us(url):
        storefront = url.split("/")[3]
        if storefront != "us":
            raise OSError("network")
        return 200, url, _page("us")

    collector = PublicRatingsCollector(temp_db.db_path, fetch=offline_after_us)
    result = collector.run(actor="automation")

    assert (result["status"], result["storefronts_pending"]) == ("partial", len(ratings.DEFAULT_STOREFRONTS) - 1)
    assert collector.storefronts()[0] == "gb"
    assert collector.storefronts().index("us") == len(ratings.DEFAULT_STOREFRONTS) - 1
    assert not collector.due()
    assert collector.due(now=_now() + timedelta(hours=7))

    collector.fetch = lambda url: (200, url, _page(url.split("/")[3]))
    assert collector.run(actor="automation", force=True)["storefronts_pending"] == 0
    assert collector.storefronts()[0] == "us"
    assert not collector.due(now=_now() + timedelta(hours=7))
