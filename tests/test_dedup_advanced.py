"""Phone-based dedup in master + domain-based dedup at Smartlead export."""

import csv

import pytest

from bot import github_storage, leads_db


@pytest.fixture(autouse=True)
def fresh_state():
    github_storage._mem_reset_for_tests()
    leads_db._reset_for_tests()
    yield
    github_storage._mem_reset_for_tests()
    leads_db._reset_for_tests()


def _row(bid, phone="+1-555-0100", state="Wisconsin", score=5, email="x@biz.com"):
    return {
        "business_id": bid, "nombre": "Biz", "tipo": "", "subtipo": "",
        "rating": "", "review_count": "", "verified": "", "business_status": "",
        "lead_score": str(score), "photos_count": "", "direccion": "",
        "city": "", "state": state, "district": "", "latitude": "",
        "longitude": "", "telefono": phone, "email": email, "website": "",
        "instagram": "", "facebook": "", "linkedin": "", "twitter": "",
        "youtube": "", "emails_extra": "", "link_google_maps": "",
        "booking_link": "", "menu_link": "", "order_link": "",
        "localidad_buscada": "", "categoria_buscada": "", "provincia": state,
    }


# ── phone normalization ──────────────────────────────────────

def test_normalize_phone_strips_formatting():
    assert leads_db._normalize_phone("+1 (608) 555-0100") == "6085550100"
    assert leads_db._normalize_phone("608.555.0100") == "6085550100"


def test_normalize_phone_drops_us_country_code():
    assert leads_db._normalize_phone("16085550100") == "6085550100"


def test_normalize_phone_returns_empty_for_short():
    assert leads_db._normalize_phone("555-0100") == ""
    assert leads_db._normalize_phone("") == ""


# ── phone dedup in add_rows ──────────────────────────────────

def test_add_rows_skips_duplicate_phone():
    n1 = leads_db.add_rows([_row("bid-1", phone="+1-608-555-0100")])
    n2 = leads_db.add_rows([_row("bid-2", phone="(608) 555-0100")])
    assert n1 == 1 and n2 == 0
    assert leads_db.business_ids() == {"bid-1"}


def test_add_rows_keeps_distinct_phones():
    leads_db.add_rows([_row("bid-1", phone="608-555-0100")])
    n2 = leads_db.add_rows([_row("bid-2", phone="608-555-0200")])
    assert n2 == 1
    assert leads_db.business_ids() == {"bid-1", "bid-2"}


def test_add_rows_allows_empty_phone():
    """A row without a phone should be added; subsequent empty-phone rows too."""
    n1 = leads_db.add_rows([_row("bid-1", phone="")])
    n2 = leads_db.add_rows([_row("bid-2", phone="")])
    assert n1 == 1 and n2 == 1


# ── domain dedup at Smartlead export ─────────────────────────

def test_smartlead_export_dedups_by_business_domain(tmp_path):
    """Two leads with different scores at biz.com → only highest-score row survives."""
    import scraper as scraper_mod
    import export_smartlead

    src = tmp_path / "src.csv"
    with open(src, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=scraper_mod.COLUMNAS_CSV)
        w.writeheader()
        w.writerow(_row("a", email="info@biz.com", score=3))
        w.writerow(_row("b", phone="+1-555-0200", email="owner@biz.com", score=6))
        w.writerow(_row("c", phone="+1-555-0300", email="sales@otherbiz.com", score=4))

    out = export_smartlead.export(str(src), min_score=0)
    with open(out) as f:
        rows = list(csv.DictReader(f))
    emails = sorted(r["email"] for r in rows)
    assert emails == ["owner@biz.com", "sales@otherbiz.com"]


def test_smartlead_export_keeps_all_free_provider_rows(tmp_path):
    """gmail.com is a personal domain — should NOT dedup."""
    import scraper as scraper_mod
    import export_smartlead

    src = tmp_path / "src.csv"
    with open(src, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=scraper_mod.COLUMNAS_CSV)
        w.writeheader()
        w.writerow(_row("a", phone="+1-555-0100", email="alice@gmail.com", score=5))
        w.writerow(_row("b", phone="+1-555-0200", email="bob@gmail.com", score=4))

    out = export_smartlead.export(str(src), min_score=0)
    with open(out) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2


def test_smartlead_export_dedup_can_be_disabled(tmp_path):
    import scraper as scraper_mod
    import export_smartlead

    src = tmp_path / "src.csv"
    with open(src, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=scraper_mod.COLUMNAS_CSV)
        w.writeheader()
        w.writerow(_row("a", email="info@biz.com", score=3))
        w.writerow(_row("b", phone="+1-555-0200", email="sales@biz.com", score=6))

    out = export_smartlead.export(str(src), min_score=0, dedup_by_domain=False)
    with open(out) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
