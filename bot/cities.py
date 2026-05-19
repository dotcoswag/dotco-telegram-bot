"""Loads data/us_cities.json once at import time for the bot's custom-city flow."""

import json
import os

_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "us_cities.json",
)


def _load() -> list[dict]:
    with open(_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["provincias"]


# Module-level state list. Index → state dict {nombre, localidades:[...]}.
# Indices are stable for the process lifetime, so callback_data can reference them.
STATES: list[dict] = _load()


def state_name(idx: int) -> str:
    return STATES[idx]["nombre"]


def cities_in_state(idx: int) -> list[dict]:
    return STATES[idx]["localidades"]


def city_at(state_idx: int, city_idx: int) -> tuple[str, str]:
    """Return (city_name, state_name) for the indexed pair."""
    state = STATES[state_idx]
    city = state["localidades"][city_idx]
    return city["nombre"], state["nombre"]
