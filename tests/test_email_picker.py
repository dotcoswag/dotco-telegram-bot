"""Email ranking — covers the precedence rules in bot.email_picker."""

from bot.email_picker import pick_best_email


def test_prefers_firstname_lastname_over_info():
    assert pick_best_email(
        "info@biz.com", "john.smith@biz.com | sales@biz.com"
    ) == "john.smith@biz.com"


def test_prefers_owner_over_info_and_department():
    assert pick_best_email(
        "info@biz.com", "owner@biz.com|sales@biz.com"
    ) == "owner@biz.com"


def test_personal_single_token_beats_role():
    assert pick_best_email("info@biz.com", "mike@biz.com") == "mike@biz.com"


def test_discards_noreply_addresses():
    assert pick_best_email(
        "noreply@biz.com", "info@biz.com"
    ) == "info@biz.com"


def test_returns_empty_when_nothing_usable():
    assert pick_best_email("", "") == ""
    assert pick_best_email("noreply@biz.com", "donotreply@biz.com") == ""


def test_primary_lowercased():
    assert pick_best_email("Info@Biz.COM", "") == "info@biz.com"


def test_falls_back_to_role_when_no_personal():
    # All extras are department aliases; sales is lowest among them but is
    # the only candidate (info doesn't exist) — should still pick something.
    assert pick_best_email("", "sales@biz.com|support@biz.com") in (
        "sales@biz.com", "support@biz.com"
    )


def test_dotted_personal_beats_owner():
    # firstname.lastname is score 6, owner is score 5. Both real-person signals;
    # tie-breaker favors the more identifiable.
    assert pick_best_email(
        "owner@biz.com", "jane.doe@biz.com"
    ) == "jane.doe@biz.com"


def test_invalid_emails_skipped():
    assert pick_best_email("not-an-email", "also-bad|real@biz.com") == "real@biz.com"


def test_pipe_with_extra_whitespace():
    assert pick_best_email(
        "info@biz.com",
        "  jane.doe@biz.com   |  sales@biz.com  "
    ) == "jane.doe@biz.com"
