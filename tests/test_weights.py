"""Tests für die CLI-Gewichtungslogik (main.parse_weights)."""

from main import parse_weights

from paketstation.config import DEFAULT_WEIGHTS


def test_default_weights_when_empty():
    assert parse_weights(None) == DEFAULT_WEIGHTS
    assert parse_weights("") == DEFAULT_WEIGHTS


def test_override_single_and_aliases():
    w = parse_weights("pop=4,pt=5")
    assert w["population"] == 4.0
    assert w["public_transport"] == 5.0
    # nicht angegebene Faktoren bleiben auf Default
    assert w["shops"] == DEFAULT_WEIGHTS["shops"]


def test_long_form_keys():
    w = parse_weights("population=1,transport=2,competition=0,walkability=3")
    assert w["population"] == 1.0
    assert w["public_transport"] == 2.0
    assert w["competition"] == 0.0
    assert w["walkability"] == 3.0


def test_invalid_values_are_ignored():
    w = parse_weights("pop=abc,unknown=5,shops=2")
    # ungültiger Float wird ignoriert -> Default bleibt
    assert w["population"] == DEFAULT_WEIGHTS["population"]
    # unbekannter Schlüssel wird ignoriert
    assert "unknown" not in w
    # gültiger Wert greift
    assert w["shops"] == 2.0


def test_does_not_mutate_default():
    parse_weights("pop=99")
    assert DEFAULT_WEIGHTS["population"] == 3
