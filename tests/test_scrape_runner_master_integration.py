"""scrape_runner integration: master DB priming, fresh-combo skip, dedup across runs."""

import threading
from unittest.mock import patch

import pytest

from bot import github_storage, leads_db, scrape_runner


@pytest.fixture(autouse=True)
def fresh_state():
    github_storage._mem_reset_for_tests()
    leads_db._reset_for_tests()
    yield
    github_storage._mem_reset_for_tests()
    leads_db._reset_for_tests()


class FakeBridge:
    def __init__(self):
        self.messages = []
    def push(self, text, force=False):
        self.messages.append(text)


def _make_fake_scrape_combinacion(return_rows_per_call):
    """Return a fake `scrape_combinacion` that yields a fixed set of rows the
    first time, then 0 on subsequent calls. Mutates the passed-in seen_ids and
    invokes on_new_rows.
    """
    calls = {"n": 0}

    def fake(localidad, categoria, provincia, archivo_csv, seen_ids, limite_total,
             min_score=0, cancel_event=None, on_new_rows=None, limite_por_combo=None):
        calls["n"] += 1
        if calls["n"] > 1:
            return (0, 0, 0)  # subsequent combos return nothing new
        new_rows = []
        for bid in return_rows_per_call:
            if bid in seen_ids:
                continue
            seen_ids.add(bid)
            row = {
                "business_id": bid, "nombre": f"Biz {bid}", "lead_score": "5",
                "state": provincia, "categoria_buscada": categoria,
                "city": localidad, "provincia": provincia,
                "tipo": "", "subtipo": "", "rating": "", "review_count": "",
                "verified": "", "business_status": "", "photos_count": "",
                "direccion": "", "district": "", "latitude": "", "longitude": "",
                "telefono": "", "email": "", "website": "", "instagram": "",
                "facebook": "", "linkedin": "", "twitter": "", "youtube": "",
                "emails_extra": "", "link_google_maps": "", "booking_link": "",
                "menu_link": "", "order_link": "", "localidad_buscada": localidad,
            }
            new_rows.append(row)
        if on_new_rows and new_rows:
            on_new_rows(new_rows)
        return (len(new_rows), 0, 0)
    return fake


@patch("bot.scrape_runner.scrape_combinacion")
def test_master_grows_after_run(mock_scrape):
    mock_scrape.side_effect = _make_fake_scrape_combinacion(["b1", "b2", "b3"])
    result = scrape_runner.run(
        localidades=[("Madison", "Wisconsin")],
        categorias=["gym"],
        limite=None, min_score=0,
        bridge=FakeBridge(),
        cancel_event=threading.Event(),
        skip_fresh=True,
    )
    assert result["total_nuevos"] == 3
    assert leads_db.business_ids() == {"b1", "b2", "b3"}


@patch("bot.scrape_runner.scrape_combinacion")
def test_rerun_same_combo_skips_when_skip_fresh(mock_scrape):
    """First run populates master + scrape_log. Second run with skip_fresh=True
    must skip the same combo entirely (zero calls to scrape_combinacion)."""
    mock_scrape.side_effect = _make_fake_scrape_combinacion(["b1"])
    scrape_runner.run(
        localidades=[("Madison", "Wisconsin")], categorias=["gym"],
        limite=None, min_score=0,
        bridge=FakeBridge(), cancel_event=threading.Event(), skip_fresh=True,
    )
    first_call_count = mock_scrape.call_count

    result2 = scrape_runner.run(
        localidades=[("Madison", "Wisconsin")], categorias=["gym"],
        limite=None, min_score=0,
        bridge=FakeBridge(), cancel_event=threading.Event(), skip_fresh=True,
    )
    # No additional calls — the only combo was fresh-skipped.
    assert mock_scrape.call_count == first_call_count
    assert result2["combos_total"] == 0
    assert result2["combos_skipped_fresh"] == 1


@patch("bot.scrape_runner.scrape_combinacion")
def test_rerun_with_skip_fresh_false_runs_again_but_dedups(mock_scrape):
    mock_scrape.side_effect = _make_fake_scrape_combinacion(["b1"])
    scrape_runner.run(
        localidades=[("Madison", "Wisconsin")], categorias=["gym"],
        limite=None, min_score=0,
        bridge=FakeBridge(), cancel_event=threading.Event(), skip_fresh=True,
    )

    # Second run — skip_fresh=False, but master is primed so seen_ids prevents dupes.
    mock_scrape.side_effect = _make_fake_scrape_combinacion(["b1", "b2"])
    result = scrape_runner.run(
        localidades=[("Madison", "Wisconsin")], categorias=["gym"],
        limite=None, min_score=0,
        bridge=FakeBridge(), cancel_event=threading.Event(), skip_fresh=False,
    )
    # b1 was already in master → only b2 is new.
    assert result["total_nuevos"] == 1
    assert leads_db.business_ids() == {"b1", "b2"}
