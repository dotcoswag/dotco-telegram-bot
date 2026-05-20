"""Unit tests for bot.domain_enricher — extraction, RDAP parsing, MX classification.

External lookups (HTTPS and DNS) are mocked. Tests don't hit the network.
"""

from unittest.mock import MagicMock, patch

import pytest

from bot import domain_enricher


# ── extract_domain ───────────────────────────────────────────

def test_extract_domain_strips_www_and_scheme():
    assert domain_enricher.extract_domain("https://www.biz.com/about?x=1") == "biz.com"
    assert domain_enricher.extract_domain("http://biz.com") == "biz.com"
    assert domain_enricher.extract_domain("www.biz.com") == "biz.com"


def test_extract_domain_handles_subdomain():
    assert domain_enricher.extract_domain("https://shop.biz.com/x") == "shop.biz.com"


def test_extract_domain_empty_for_garbage():
    assert domain_enricher.extract_domain("") == ""
    assert domain_enricher.extract_domain("not a url") == ""
    assert domain_enricher.extract_domain("http://") == ""


# ── RDAP parsing ─────────────────────────────────────────────

def _rdap_response(reg_date: str, registrar: str):
    body = {"events": []}
    if reg_date:
        body["events"].append({"eventAction": "registration", "eventDate": reg_date})
    if registrar:
        body["entities"] = [{
            "roles": ["registrar"],
            "vcardArray": ["vcard", [["version", {}, "text", "4.0"],
                                     ["fn", {}, "text", registrar]]],
        }]
    r = MagicMock()
    r.ok = True
    r.json.return_value = body
    return r


@patch("bot.domain_enricher.requests.get")
def test_get_rdap_parses_registration_and_registrar(mock_get):
    mock_get.return_value = _rdap_response("2014-03-22T16:14:32Z", "GoDaddy.com, LLC")
    info = domain_enricher.get_rdap("biz.com")
    assert info["registration_date"] == "2014-03-22T16:14:32Z"
    assert info["registrar"] == "GoDaddy.com, LLC"


@patch("bot.domain_enricher.requests.get")
def test_get_rdap_handles_404(mock_get):
    r = MagicMock()
    r.ok = False
    mock_get.return_value = r
    assert domain_enricher.get_rdap("nope.example") is None


def test_years_since_returns_int():
    # 2014 → roughly 12 in 2026. The exact number varies day-to-day but >= 11.
    years = domain_enricher.years_since("2014-03-22T16:14:32Z")
    assert years is not None and years >= 11


def test_years_since_handles_bad_input():
    assert domain_enricher.years_since("") is None
    assert domain_enricher.years_since("not a date") is None


# ── MX classification ────────────────────────────────────────

def test_classify_mx_google():
    hosts = ["aspmx.l.google.com", "alt1.aspmx.l.google.com"]
    assert domain_enricher.classify_mx_provider(hosts) == "google_workspace"


def test_classify_mx_microsoft():
    hosts = ["biz-com.mail.protection.outlook.com"]
    assert domain_enricher.classify_mx_provider(hosts) == "microsoft365"


def test_classify_mx_other():
    hosts = ["mail.biz.com", "mail2.biz.com"]
    assert domain_enricher.classify_mx_provider(hosts) == "other"


def test_classify_mx_none_when_empty():
    assert domain_enricher.classify_mx_provider([]) == "none"


# ── enrich_domain (end-to-end with mocks) ────────────────────

@patch("bot.domain_enricher.get_mx_hosts")
@patch("bot.domain_enricher.get_rdap")
def test_enrich_domain_combines_sources(mock_rdap, mock_mx):
    mock_rdap.return_value = {"registration_date": "2014-03-22T16:14:32Z",
                              "registrar": "GoDaddy"}
    mock_mx.return_value = ["aspmx.l.google.com"]
    info = domain_enricher.enrich_domain("biz.com")
    assert info["domain"] == "biz.com"
    assert int(info["domain_age_years"]) >= 11
    assert info["registrar"] == "GoDaddy"
    assert info["mx_provider"] == "google_workspace"


@patch("bot.domain_enricher.get_mx_hosts", return_value=[])
@patch("bot.domain_enricher.get_rdap", return_value=None)
def test_enrich_domain_handles_failures(_rdap, _mx):
    info = domain_enricher.enrich_domain("dead.example")
    assert info["domain"] == "dead.example"
    assert info["domain_age_years"] == ""
    assert info["registrar"] == ""
    assert info["mx_provider"] == "none"
