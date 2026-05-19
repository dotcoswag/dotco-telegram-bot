"""End-to-end DB → filter → Smartlead CSV via the same helper /db_export_smartlead uses."""

import csv

import pytest

import export_smartlead
from bot import github_storage, leads_db


@pytest.fixture(autouse=True)
def fresh_state():
    github_storage._mem_reset_for_tests()
    leads_db._reset_for_tests()
    yield
    github_storage._mem_reset_for_tests()
    leads_db._reset_for_tests()


def _row(bid, state, score, email=""):
    return {
        "business_id": bid, "nombre": f"Biz {bid}", "tipo": "gym",
        "subtipo": "", "rating": "", "review_count": "", "verified": "",
        "business_status": "", "lead_score": str(score), "photos_count": "",
        "direccion": "", "city": "X", "state": state, "district": "",
        "latitude": "", "longitude": "", "telefono": "", "email": email,
        "website": "", "instagram": "", "facebook": "", "linkedin": "",
        "twitter": "", "youtube": "", "emails_extra": "",
        "link_google_maps": "", "booking_link": "", "menu_link": "",
        "order_link": "", "localidad_buscada": "X",
        "categoria_buscada": "gym", "provincia": state,
    }


def test_filter_then_smartlead_export(tmp_path):
    leads_db.add_rows([
        _row("a", "Wisconsin", 7, "a@example.com"),
        _row("b", "Wisconsin", 2, "b@example.com"),  # below min_score
        _row("c", "Colorado",  7, "c@example.com"),  # different state
        _row("d", "Wisconsin", 7, ""),               # no email — Smartlead drops it
    ])
    raw = tmp_path / "filtered.csv"
    count = leads_db.write_filtered_csv(
        str(raw), state="Wisconsin", category_group=None, min_score=5
    )
    assert count == 2  # a, d (score>=5, Wisconsin)

    sl_path = export_smartlead.export(str(raw), min_score=0, require_qualified=False)
    with open(sl_path) as f:
        rows = list(csv.DictReader(f))
    # 'a' has email → included; 'd' has no email → dropped by Smartlead exporter
    assert {r["email"] for r in rows} == {"a@example.com"}
