"""Tests de la lista curada de tickers (Etapa C1, bloque 5, AC-C1-1)."""

import pytest

from datos.tickers import (
    CURATED_TICKERS,
    MANUAL_ENTRY,
    resolve_ticker,
    ticker_options,
    tickers_for,
)


def test_curated_lists_by_kind():
    assert tickers_for("Acción") == ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA"]
    assert tickers_for("ETF") == ["SPY", "QQQ", "IWM"]
    assert tickers_for("Índice") == ["SPX"]


def test_kinds_match_app_underlyings():
    # Mismos tipos que el selector "Tipo de subyacente" de la app.
    assert list(CURATED_TICKERS) == ["Acción", "ETF", "Índice"]


def test_unknown_kind_has_no_tickers():
    assert tickers_for("Bono") == []
    assert ticker_options("Bono") == [MANUAL_ENTRY]


def test_options_start_with_manual_entry():
    assert MANUAL_ENTRY == "Entrada manual"
    assert ticker_options("ETF") == ["Entrada manual", "SPY", "QQQ", "IWM"]


def test_tickers_for_returns_a_copy():
    tickers_for("ETF").append("XYZ")
    assert tickers_for("ETF") == ["SPY", "QQQ", "IWM"]


def test_spx_resolves_to_yahoo_index_symbol():
    assert resolve_ticker("Índice", "SPX") == "^SPX"


@pytest.mark.parametrize(
    "kind, name",
    [("ETF", "SPY"), ("ETF", "QQQ"), ("ETF", "IWM"), ("Acción", "AAPL"), ("Acción", "TSLA")],
)
def test_plain_tickers_resolve_to_themselves(kind, name):
    assert resolve_ticker(kind, name) == name


@pytest.mark.parametrize(
    "kind, name",
    [
        ("ETF", "XYZ"),  # fuera de la lista
        ("Acción", "SPY"),  # de la lista, pero de otro tipo
        ("Índice", "^SPX"),  # el símbolo de Yahoo no es una etiqueta curada
        ("Índice", "NDX"),
        ("ETF", ""),
        ("ETF", None),
    ],
)
def test_ticker_outside_list_is_rejected(kind, name):
    assert resolve_ticker(kind, name) is None


@pytest.mark.parametrize("kind", ["Acción", "ETF", "Índice"])
def test_manual_entry_does_not_resolve(kind):
    assert resolve_ticker(kind, MANUAL_ENTRY) is None
