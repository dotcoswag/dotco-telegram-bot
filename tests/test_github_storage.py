"""Smoke tests for the in-memory backend AND the GitHub API client (mocked)."""

from unittest.mock import MagicMock, patch

import pytest

from bot import github_storage


@pytest.fixture(autouse=True)
def reset_mem():
    github_storage._mem_reset_for_tests()
    yield
    github_storage._mem_reset_for_tests()


# ── memory backend ───────────────────────────────────────────

def test_memory_backend_roundtrip():
    content, sha = github_storage.get_file("foo.csv")
    assert content is None and sha is None
    new_sha = github_storage.put_file("foo.csv", b"hello,world", None, "msg")
    content, sha = github_storage.get_file("foo.csv")
    assert content == b"hello,world"
    assert sha == new_sha


def test_memory_backend_conflict_on_wrong_sha():
    github_storage.put_file("foo.csv", b"v1", None, "msg")
    with pytest.raises(github_storage.StorageError):
        github_storage.put_file("foo.csv", b"v2", "wrong_sha", "msg")


# ── github backend (mocked requests) ─────────────────────────

def _make_resp(status, json_body=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.ok = 200 <= status < 300
    r.json.return_value = json_body or {}
    r.text = text
    return r


@patch.dict("os.environ", {"LEADS_DB_BACKEND": "github"})
@patch("bot.github_storage.requests.get")
def test_gh_get_handles_404(mock_get):
    mock_get.return_value = _make_resp(404)
    assert github_storage.get_file("missing.csv") == (None, None)


@patch.dict("os.environ", {"LEADS_DB_BACKEND": "github"})
@patch("bot.github_storage.requests.get")
def test_gh_get_decodes_base64(mock_get):
    import base64
    content = b"id,name\n1,Foo\n"
    mock_get.return_value = _make_resp(
        200, {"content": base64.b64encode(content).decode(), "sha": "abc123"}
    )
    got, sha = github_storage.get_file("data/master_leads.csv")
    assert got == content and sha == "abc123"


@patch.dict("os.environ", {"LEADS_DB_BACKEND": "github"})
@patch("bot.github_storage.requests.put")
def test_gh_put_sends_prior_sha(mock_put):
    mock_put.return_value = _make_resp(200, {"content": {"sha": "newsha"}})
    sha = github_storage.put_file("a.csv", b"data", "oldsha", "msg")
    assert sha == "newsha"
    # Inspect the JSON body sent
    call = mock_put.call_args
    body = call.kwargs.get("json") or call[1].get("json")
    assert body["sha"] == "oldsha"
    assert body["message"] == "msg"


@patch.dict("os.environ", {"LEADS_DB_BACKEND": "github"})
@patch("bot.github_storage.time.sleep")
@patch("bot.github_storage.requests.put")
def test_gh_put_retries_on_5xx(mock_put, _sleep):
    mock_put.side_effect = [
        _make_resp(503),
        _make_resp(503),
        _make_resp(200, {"content": {"sha": "x"}}),
    ]
    sha = github_storage.put_file("a.csv", b"d", None, "m")
    assert sha == "x"
    assert mock_put.call_count == 3


@patch.dict("os.environ", {"LEADS_DB_BACKEND": "github"})
@patch("bot.github_storage.requests.put")
def test_gh_put_raises_on_409(mock_put):
    mock_put.return_value = _make_resp(409, text="conflict")
    with pytest.raises(github_storage.StorageError):
        github_storage.put_file("a.csv", b"d", "stale_sha", "m")
