"""leads_db: in-memory master + scrape_log behavior, using the memory backend."""

from datetime import datetime, timedelta, timezone

import pytest

from bot import github_storage, leads_db


@pytest.fixture(autouse=True)
def fresh_state():
    github_storage._mem_reset_for_tests()
    leads_db._reset_for_tests()
    yield
    github_storage._mem_reset_for_tests()
    leads_db._reset_for_tests()


def _row(bid: str, state: str = "Wisconsin", cat: str = "gym", score: int = 5) -> dict:
    return {
        "business_id": bid, "nombre": f"Biz {bid}", "tipo": "test",
        "subtipo": "", "rating": "4.5", "review_count": "20", "verified": "true",
        "business_status": "OPERATIONAL", "lead_score": str(score), "photos_count": "10",
        "direccion": "", "city": "Madison", "state": state, "district": "",
        "latitude": "", "longitude": "", "telefono": "+1-555-0000",
        "email": f"{bid}@example.com", "website": "", "instagram": "",
        "facebook": "", "linkedin": "", "twitter": "", "youtube": "",
        "emails_extra": "", "link_google_maps": "", "booking_link": "",
        "menu_link": "", "order_link": "",
        "localidad_buscada": "Madison", "categoria_buscada": cat, "provincia": state,
    }


def test_add_rows_dedupes_by_business_id():
    n = leads_db.add_rows([_row("1"), _row("2"), _row("1")])
    assert n == 2
    assert leads_db.business_ids() == {"1", "2"}


def test_add_rows_skips_empty_business_id():
    bad = _row("")
    n = leads_db.add_rows([bad])
    assert n == 0
    assert leads_db.business_ids() == set()


def test_record_scrape_and_is_fresh():
    leads_db.record_scrape("Madison", "Wisconsin", "gym", 5)
    assert leads_db.is_fresh("Madison", "Wisconsin", "gym", days=30)
    assert not leads_db.is_fresh("Madison", "Wisconsin", "yoga studio", days=30)


def test_is_fresh_returns_false_when_returned_count_zero():
    leads_db.record_scrape("Madison", "Wisconsin", "gym", 0)
    assert not leads_db.is_fresh("Madison", "Wisconsin", "gym", days=30)


def test_is_fresh_returns_false_when_older_than_window():
    leads_db.record_scrape("Madison", "Wisconsin", "gym", 5)
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(timespec="seconds")
    leads_db.SCRAPE_LOG[("Madison", "Wisconsin", "gym")]["last_scraped_at_iso"] = old
    assert not leads_db.is_fresh("Madison", "Wisconsin", "gym", days=30)


def test_filter_rows_by_state():
    leads_db.add_rows([_row("1", state="Wisconsin"), _row("2", state="Colorado")])
    rows = list(leads_db.filter_rows(state="Wisconsin"))
    assert len(rows) == 1 and rows[0]["business_id"] == "1"


def test_filter_rows_by_min_score():
    leads_db.add_rows([_row("a", score=3), _row("b", score=6), _row("c", score=5)])
    rows = list(leads_db.filter_rows(min_score=5))
    assert {r["business_id"] for r in rows} == {"b", "c"}


def test_filter_rows_by_category_group():
    # Use a real key from main.CATEGORIAS so the group→cats mapping resolves.
    import main as scraper_main
    group = "🏋️ Gyms & Fitness"
    a_cat = scraper_main.CATEGORIAS[group][0]
    leads_db.add_rows([_row("g", cat=a_cat), _row("x", cat="not-a-real-cat")])
    rows = list(leads_db.filter_rows(category_group=group))
    assert {r["business_id"] for r in rows} == {"g"}


def test_flush_writes_both_files_and_reload_works():
    leads_db.add_rows([_row("1"), _row("2")])
    leads_db.record_scrape("Madison", "Wisconsin", "gym", 2)
    leads_db.flush()

    # Reset in-memory state, then reload — should come back identical.
    leads_db._reset_for_tests()
    leads_db.ensure_loaded()
    assert leads_db.business_ids() == {"1", "2"}
    assert leads_db.is_fresh("Madison", "Wisconsin", "gym", days=30)


def test_stats_handles_empty_and_populated():
    assert leads_db.stats()["total"] == 0
    leads_db.add_rows([_row("1", score=7), _row("2", score=4)])
    s = leads_db.stats()
    assert s["total"] == 2
    assert s["score_hist"][7] == 1
    assert s["score_hist"][4] == 1


def test_write_filtered_csv_writes_expected_count(tmp_path):
    leads_db.add_rows([_row("a", score=2), _row("b", score=7)])
    out = tmp_path / "out.csv"
    n = leads_db.write_filtered_csv(str(out), min_score=5)
    assert n == 1
    assert out.read_text().count("\n") >= 2  # header + 1 row
