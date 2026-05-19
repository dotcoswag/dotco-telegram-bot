"""scraper.llamar_api raises QuotaExhausted on the right 429 bodies."""

from unittest.mock import MagicMock, patch

import pytest

import scraper
from scraper import QuotaExhausted


def _fake_429(message):
    r = MagicMock()
    r.status_code = 429
    r.json.return_value = {"message": message}
    r.headers = {"Retry-After": "1"}
    return r


@patch("scraper.requests.get")
def test_monthly_quota_message_raises(mock_get):
    mock_get.return_value = _fake_429(
        "You have exceeded the MONTHLY quota for Businesses on your current plan, BASIC."
    )
    with pytest.raises(QuotaExhausted):
        scraper.llamar_api("anything", 1, 0, max_retries=0)


@patch("scraper.requests.get")
def test_plan_message_raises(mock_get):
    mock_get.return_value = _fake_429("Exceeded your plan limits")
    with pytest.raises(QuotaExhausted):
        scraper.llamar_api("anything", 1, 0, max_retries=0)


@patch("scraper.requests.get")
def test_transient_429_retries_then_gives_up(mock_get):
    """A generic 429 with no quota wording should retry, not abort the whole job."""
    mock_get.return_value = _fake_429("Slow down, partner")
    # max_retries=0 means one attempt, then return [] (NOT raise)
    result = scraper.llamar_api("anything", 1, 0, max_retries=0)
    assert result == []
