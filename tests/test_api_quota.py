"""api_quota header parsing — uses a fake requests response, no real HTTP."""

from unittest.mock import MagicMock, patch

from bot import api_quota


def _fake_response(headers):
    r = MagicMock()
    r.headers = headers
    return r


@patch("bot.api_quota.requests.get")
def test_fetch_parses_headers(mock_get):
    mock_get.return_value = _fake_response({
        "x-ratelimit-businesses-limit": "500",
        "x-ratelimit-businesses-remaining": "-39",
        "x-ratelimit-businesses-reset": "1746345",
    })
    info = api_quota.fetch()
    assert info == {"limit": 500, "remaining": -39, "reset_seconds": 1746345}


@patch("bot.api_quota.requests.get", side_effect=Exception("network down"))
def test_fetch_returns_none_on_error(mock_get):
    assert api_quota.fetch() is None


@patch("bot.api_quota.requests.get")
def test_fetch_returns_none_on_missing_headers(mock_get):
    mock_get.return_value = _fake_response({})  # no quota headers
    # int("0") works, but if headers truly missing the .get default kicks in
    info = api_quota.fetch()
    assert info == {"limit": 0, "remaining": 0, "reset_seconds": 0}


def test_format_reset_buckets():
    assert "d" in api_quota.format_reset(86400 * 2 + 3600)
    assert "h" in api_quota.format_reset(3600 * 5 + 60)
    assert "m" in api_quota.format_reset(120)
    assert api_quota.format_reset(0) == "soon"


def test_summary_line_handles_none():
    assert "couldn't fetch" in api_quota.summary_line(None)


def test_summary_line_flags_over_limit():
    line = api_quota.summary_line({"limit": 500, "remaining": -10, "reset_seconds": 1000})
    assert "OVER LIMIT" in line
    assert "510" in line  # used = limit - remaining
