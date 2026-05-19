"""scrape_runner: cancel & QuotaExhausted paths, with scraper.scrape_combinacion mocked.

These tests don't spin up a Telegram bot — they call the sync function directly
with a fake ProgressBridge and a real threading.Event for cancellation.
"""

import threading
from unittest.mock import MagicMock, patch

import pytest

from bot import github_storage, leads_db, scrape_runner
from scraper import QuotaExhausted


@pytest.fixture(autouse=True)
def reset_db_state():
    """Each test gets an empty master + scrape_log to avoid cross-test pollution
    from record_scrape() calls inside scrape_runner.run."""
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


def _fake_combo_ok(_negocios=3):
    return MagicMock(return_value=(_negocios, 0, 0))


@patch("bot.scrape_runner.scrape_combinacion")
def test_full_run_processes_all_combos(mock_scrape):
    mock_scrape.return_value = (5, 1, 0)
    bridge = FakeBridge()
    cancel = threading.Event()
    result = scrape_runner.run(
        localidades=[("Madison", "Wisconsin"), ("Boulder", "Colorado")],
        categorias=["gym", "yoga studio"],
        limite=None,
        min_score=0,
        bridge=bridge,
        cancel_event=cancel,
    )
    assert mock_scrape.call_count == 4  # 2 cities × 2 cats
    assert result["combos_total"] == 4
    assert result["cancelled"] is False
    assert result["total_nuevos"] == 20  # 5 × 4 combos


@patch("bot.scrape_runner.scrape_combinacion", side_effect=QuotaExhausted("monthly quota exceeded"))
def test_quota_exhausted_aborts_after_one_combo(mock_scrape):
    bridge = FakeBridge()
    cancel = threading.Event()
    result = scrape_runner.run(
        localidades=[("Madison", "Wisconsin"), ("Boulder", "Colorado")],
        categorias=["gym", "yoga studio"],
        limite=None,
        min_score=0,
        bridge=bridge,
        cancel_event=cancel,
    )
    assert mock_scrape.call_count == 1
    assert result["cancelled"] is True
    assert any("quota exhausted" in m.lower() for m in bridge.messages)


@patch("bot.scrape_runner.scrape_combinacion")
def test_cancel_event_breaks_loop(mock_scrape):
    """If cancel_event is already set, the run should exit before any scrape."""
    mock_scrape.return_value = (1, 0, 0)
    bridge = FakeBridge()
    cancel = threading.Event()
    cancel.set()
    result = scrape_runner.run(
        localidades=[("Madison", "Wisconsin")],
        categorias=["gym"],
        limite=None,
        min_score=0,
        bridge=bridge,
        cancel_event=cancel,
    )
    assert mock_scrape.call_count == 0
    assert result["cancelled"] is True


@patch("bot.scrape_runner.scrape_combinacion")
def test_limit_short_circuits(mock_scrape):
    """When `limite` is reached via seen_ids, the loop stops scheduling new combos.

    The fake records nothing into seen_ids since it's mocked — instead we test
    that the limit check itself is respected when we manually trip it via the
    nuevos return value (limite=1 means after the first combo's added rows the
    loop breaks at the top of the next iteration).
    """
    def fake_call(*args, **kwargs):
        kwargs["seen_ids"].update({"id1", "id2"})
        return (2, 0, 0)
    mock_scrape.side_effect = fake_call
    bridge = FakeBridge()
    cancel = threading.Event()
    result = scrape_runner.run(
        localidades=[("Madison", "Wisconsin"), ("Boulder", "Colorado")],
        categorias=["gym", "yoga studio"],
        limite=1,
        min_score=0,
        bridge=bridge,
        cancel_event=cancel,
    )
    # First call hits limit, subsequent combos are skipped.
    assert mock_scrape.call_count == 1
    assert result["rows_saved"] == 2
