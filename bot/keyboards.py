"""Inline keyboard builders for the bot conversation flows."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import main as scraper_main

from bot import cities


TIER_KEYS = list(scraper_main.MERCADOS_RECOMENDADOS.keys())
CATEGORY_KEYS = list(scraper_main.CATEGORIAS.keys())

CUSTOM_TIER_VALUE = "custom"


def tier_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=f"tier|{i}")]
            for i, label in enumerate(TIER_KEYS)]
    rows.append([InlineKeyboardButton("🌎 Pick cities manually",
                                      callback_data=f"tier|{CUSTOM_TIER_VALUE}")])
    rows.append([InlineKeyboardButton("✖ Cancel", callback_data="cancel|")])
    return InlineKeyboardMarkup(rows)


def state_keyboard() -> InlineKeyboardMarkup:
    """3-column grid of US states + DC. Indices map to bot.cities.STATES."""
    rows = []
    cols = 3
    for i in range(0, len(cities.STATES), cols):
        row = []
        for j in range(cols):
            if i + j >= len(cities.STATES):
                break
            row.append(InlineKeyboardButton(
                cities.state_name(i + j),
                callback_data=f"state|{i + j}",
            ))
        rows.append(row)
    rows.append([
        InlineKeyboardButton("✔ Done picking cities", callback_data="cities_done|"),
        InlineKeyboardButton("✖ Cancel", callback_data="cancel|"),
    ])
    return InlineKeyboardMarkup(rows)


def city_keyboard(state_idx: int, selected_in_state: set[int]) -> InlineKeyboardMarkup:
    rows = []
    for ci, city in enumerate(cities.cities_in_state(state_idx)):
        mark = "✅ " if ci in selected_in_state else "▫️ "
        pop = city.get("poblacion", 0)
        label = f"{mark}{city['nombre']} ({pop//1000}k)"
        rows.append([InlineKeyboardButton(label, callback_data=f"city|{ci}")])
    rows.append([
        InlineKeyboardButton("← Back to states", callback_data="state_back|"),
        InlineKeyboardButton("✔ Done", callback_data="cities_done|"),
    ])
    return InlineKeyboardMarkup(rows)


def category_keyboard(selected: set[int]) -> InlineKeyboardMarkup:
    rows = []
    for i, label in enumerate(CATEGORY_KEYS):
        mark = "✅ " if i in selected else "▫️ "
        rows.append([InlineKeyboardButton(f"{mark}{label}", callback_data=f"cat|{i}")])
    rows.append([
        InlineKeyboardButton("✔ Done", callback_data="cat_done|"),
        InlineKeyboardButton("✖ Cancel", callback_data="cancel|"),
    ])
    return InlineKeyboardMarkup(rows)


def min_score_keyboard(prefix: str = "score") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(str(n), callback_data=f"{prefix}|{n}") for n in range(0, 4)],
            [InlineKeyboardButton(str(n), callback_data=f"{prefix}|{n}") for n in range(4, 8)],
            [InlineKeyboardButton("✖ Cancel", callback_data="cancel|")]]
    return InlineKeyboardMarkup(rows)


def yes_no_keyboard(prefix: str, default_no: bool = True) -> InlineKeyboardMarkup:
    yes = InlineKeyboardButton("Yes", callback_data=f"{prefix}|yes")
    no_label = "No (default)" if default_no else "No"
    no = InlineKeyboardButton(no_label, callback_data=f"{prefix}|no")
    return InlineKeyboardMarkup([[no, yes]])


def confirm_keyboard(has_fresh_combos: bool) -> InlineKeyboardMarkup:
    """Final confirm step for /scrape. When there are fresh combos in the master
    DB, offer to skip them (recommended) or run all. When none, single-button run.
    Always offers a Cancel."""
    if has_fresh_combos:
        rows = [
            [InlineKeyboardButton("✓ Skip fresh (recommended)",
                                  callback_data="confirm|skip_fresh")],
            [InlineKeyboardButton("⚠ Run all (re-scrape fresh too)",
                                  callback_data="confirm|run_all")],
            [InlineKeyboardButton("✖ Cancel", callback_data="cancel|")],
        ]
    else:
        rows = [
            [InlineKeyboardButton("▶ Run", callback_data="confirm|skip_fresh")],
            [InlineKeyboardButton("✖ Cancel", callback_data="cancel|")],
        ]
    return InlineKeyboardMarkup(rows)


def state_picker_keyboard(prefix: str = "dbstate", include_all: bool = True) -> InlineKeyboardMarkup:
    """State picker for /db_export and /db_export_smartlead. Uses `prefix|N`
    where N is the state index, or `prefix|all` for the All-states option."""
    rows = []
    if include_all:
        rows.append([InlineKeyboardButton("🌐 All states", callback_data=f"{prefix}|all")])
    cols = 3
    for i in range(0, len(cities.STATES), cols):
        row = []
        for j in range(cols):
            if i + j >= len(cities.STATES):
                break
            row.append(InlineKeyboardButton(
                cities.state_name(i + j),
                callback_data=f"{prefix}|{i + j}",
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton("✖ Cancel", callback_data="cancel|")])
    return InlineKeyboardMarkup(rows)


def group_picker_keyboard(prefix: str = "dbgrp", include_all: bool = True) -> InlineKeyboardMarkup:
    """Single-select group picker for /db_export filters."""
    rows = []
    if include_all:
        rows.append([InlineKeyboardButton("🌐 All groups", callback_data=f"{prefix}|all")])
    for i, label in enumerate(CATEGORY_KEYS):
        rows.append([InlineKeyboardButton(label, callback_data=f"{prefix}|{i}")])
    rows.append([InlineKeyboardButton("✖ Cancel", callback_data="cancel|")])
    return InlineKeyboardMarkup(rows)


FEATURE_KEYS = ("first_name", "opener", "qualify")


def feature_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    rows = []
    for f in FEATURE_KEYS:
        mark = "✅ " if f in selected else "▫️ "
        rows.append([InlineKeyboardButton(f"{mark}{f}", callback_data=f"feat|{f}")])
    rows.append([
        InlineKeyboardButton("✔ Done", callback_data="feat_done|"),
        InlineKeyboardButton("✖ Cancel", callback_data="cancel|"),
    ])
    return InlineKeyboardMarkup(rows)
