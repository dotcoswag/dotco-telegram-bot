"""Keyboard builders return non-empty, structurally-sane keyboards."""

from telegram import InlineKeyboardMarkup

from bot import keyboards


def test_tier_keyboard_has_tiers_and_custom():
    kb = keyboards.tier_keyboard()
    assert isinstance(kb, InlineKeyboardMarkup)
    rows = kb.inline_keyboard
    # 2 tiers + custom + cancel = 4 rows minimum
    assert len(rows) >= 4
    callbacks = [b.callback_data for row in rows for b in row]
    assert any(cb.endswith(keyboards.CUSTOM_TIER_VALUE) for cb in callbacks)
    assert "cancel|" in callbacks


def test_category_keyboard_renders_all_groups_and_done():
    kb = keyboards.category_keyboard(set())
    rows = kb.inline_keyboard
    cat_rows = [r for r in rows if r[0].callback_data.startswith("cat|")]
    assert len(cat_rows) == len(keyboards.CATEGORY_KEYS)
    assert any(b.callback_data == "cat_done|" for row in rows for b in row)


def test_category_keyboard_marks_selected():
    selected = {0, 2}
    kb = keyboards.category_keyboard(selected)
    rows = kb.inline_keyboard
    for i, label in enumerate(keyboards.CATEGORY_KEYS):
        btn = next(b for row in rows for b in row if b.callback_data == f"cat|{i}")
        if i in selected:
            assert btn.text.startswith("✅ ")
        else:
            assert btn.text.startswith("▫️ ")


def test_state_keyboard_covers_all_states():
    kb = keyboards.state_keyboard()
    state_buttons = [
        b for row in kb.inline_keyboard for b in row
        if b.callback_data.startswith("state|")
    ]
    from bot import cities
    assert len(state_buttons) == len(cities.STATES)


def test_city_keyboard_shows_back_and_done():
    kb = keyboards.city_keyboard(0, set())
    last_row = kb.inline_keyboard[-1]
    cbs = [b.callback_data for b in last_row]
    assert "state_back|" in cbs
    assert "cities_done|" in cbs


def test_min_score_keyboard_prefix():
    default = keyboards.min_score_keyboard()
    custom = keyboards.min_score_keyboard(prefix="slscore")
    default_cb = default.inline_keyboard[0][0].callback_data
    custom_cb = custom.inline_keyboard[0][0].callback_data
    assert default_cb.startswith("score|")
    assert custom_cb.startswith("slscore|")
