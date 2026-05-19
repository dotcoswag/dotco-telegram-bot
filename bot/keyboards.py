"""Inline keyboard builders for the bot conversation flows."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import main as scraper_main


TIER_KEYS = list(scraper_main.MERCADOS_RECOMENDADOS.keys())
CATEGORY_KEYS = list(scraper_main.CATEGORIAS.keys())


def tier_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=f"tier|{i}")]
            for i, label in enumerate(TIER_KEYS)]
    rows.append([InlineKeyboardButton("✖ Cancel", callback_data="cancel|")])
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
