"""Sanity-check the cities JSON shape and helper functions."""

from bot import cities


def test_states_loaded():
    assert len(cities.STATES) >= 50  # 50 states + DC


def test_state_has_localidades():
    for s in cities.STATES:
        assert "nombre" in s
        assert "localidades" in s
        assert len(s["localidades"]) >= 1


def test_city_at_returns_pair():
    name, state = cities.city_at(0, 0)
    assert isinstance(name, str) and isinstance(state, str)
    assert name == cities.cities_in_state(0)[0]["nombre"]


def test_madison_is_in_wisconsin():
    wisconsin = next(s for s in cities.STATES if s["nombre"] == "Wisconsin")
    cities_names = {c["nombre"] for c in wisconsin["localidades"]}
    assert "Madison" in cities_names
