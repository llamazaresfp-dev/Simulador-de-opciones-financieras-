"""Tests de los tipos, errores e interfaz del paquete datos/ (Etapa C1, bloque 1)."""

import dataclasses
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from datos import (
    DatosError,
    EmptyDataError,
    MarketDataProvider,
    MarketSnapshot,
    NetworkError,
    OptionQuote,
    RateLimitError,
)
from datos import errors


def make_quote(**changes):
    """Crea una cotización de prueba; `changes` sobrescribe campos."""
    values = dict(
        kind="call",
        strike=100.0,
        bid=1.50,
        ask=1.70,
        last=1.55,
        oi=500,
        volume=20,
        iv_yahoo=0.25,
    )
    values.update(changes)
    return OptionQuote(**values)


# --- OptionQuote ---


def test_option_quote_mid_is_average_of_bid_and_ask():
    quote = make_quote(bid=1.50, ask=1.70)
    assert quote.mid == pytest.approx(1.60)


def test_option_quote_mid_ignores_last():
    # El último precio es solo informativo: no entra en la prima.
    quote = make_quote(bid=2.0, ask=3.0, last=9.0)
    assert quote.mid == pytest.approx(2.5)


def test_option_quote_is_frozen():
    quote = make_quote()
    with pytest.raises(dataclasses.FrozenInstanceError):
        quote.bid = 5.0


def test_option_quote_iv_yahoo_can_be_none():
    quote = make_quote(iv_yahoo=None)
    assert quote.iv_yahoo is None


# --- MarketSnapshot ---


def make_snapshot(**changes):
    """Crea una foto de mercado de prueba; `changes` sobrescribe campos."""
    values = dict(
        ticker="SPX",
        loaded_at=datetime(2026, 11, 20, 10, 30, tzinfo=ZoneInfo("America/New_York")),
        spot=5000.0,
        rate=0.0412,
        q=None,
        q_source="indice",
        chains={"2026-12-18": [make_quote(strike=5000.0)]},
        source="live",
    )
    values.update(changes)
    return MarketSnapshot(**values)


def test_market_snapshot_accepts_q_none():
    snapshot = make_snapshot(q=None, q_source="indice")
    assert snapshot.q is None
    assert snapshot.q_source == "indice"


def test_market_snapshot_keeps_fields():
    snapshot = make_snapshot(q=0.0045, q_source="yahoo", ticker="AAPL", spot=230.0)
    assert snapshot.ticker == "AAPL"
    assert snapshot.spot == pytest.approx(230.0)
    assert snapshot.rate == pytest.approx(0.0412)
    assert snapshot.q == pytest.approx(0.0045)
    assert snapshot.source == "live"
    assert list(snapshot.chains) == ["2026-12-18"]
    assert snapshot.loaded_at.tzinfo is not None


def test_market_snapshot_is_frozen():
    snapshot = make_snapshot()
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.spot = 1.0


# --- Errores ---


@pytest.mark.parametrize("error_class", [NetworkError, RateLimitError, EmptyDataError])
def test_error_subclasses_inherit_from_datos_error(error_class):
    assert issubclass(error_class, DatosError)
    assert issubclass(DatosError, Exception)


@pytest.mark.parametrize(
    "error_class, message",
    [
        (NetworkError, errors.MSG_NETWORK),
        (RateLimitError, errors.MSG_RATE_LIMIT),
        (EmptyDataError, errors.MSG_EMPTY),
    ],
)
def test_error_without_argument_uses_its_spanish_message(error_class, message):
    error = error_class()
    assert str(error) == message
    assert error.message == message


def test_error_accepts_custom_message():
    error = NetworkError("otro texto")
    assert str(error) == "otro texto"
    assert error.message == "otro texto"


def test_error_can_be_caught_as_datos_error():
    with pytest.raises(DatosError):
        raise RateLimitError()


ALL_MESSAGES = [name for name in dir(errors) if name.startswith("MSG_")]


def test_expected_messages_exist():
    for name in ("MSG_NETWORK", "MSG_RATE_LIMIT", "MSG_EMPTY", "MSG_NO_LIQUID"):
        assert name in ALL_MESSAGES


@pytest.mark.parametrize("name", ALL_MESSAGES)
def test_every_message_is_non_empty_spanish_text(name):
    message = getattr(errors, name)
    assert isinstance(message, str)
    assert message.strip() != ""
    # Mensajes para el usuario: en español, no un identificador técnico.
    assert " " in message


# --- Protocol MarketDataProvider ---


class MinimalProvider:
    """Proveedor mínimo de prueba: cumple la interfaz sin red."""

    def get_spot(self, ticker):
        return 100.0

    def get_expirations(self, ticker):
        return ["2026-12-18"]

    def get_chain(self, ticker, expiry):
        return [{"kind": "call", "strike": 100.0}]

    def get_rate(self):
        return 0.04

    def get_dividend_yield(self, ticker):
        return None


class IncompleteProvider:
    """Le falta get_rate y get_dividend_yield: no cumple la interfaz."""

    def get_spot(self, ticker):
        return 100.0


def test_minimal_provider_satisfies_protocol():
    assert isinstance(MinimalProvider(), MarketDataProvider)


def test_incomplete_provider_does_not_satisfy_protocol():
    assert not isinstance(IncompleteProvider(), MarketDataProvider)


def test_protocol_methods_are_declared():
    for name in (
        "get_spot",
        "get_expirations",
        "get_chain",
        "get_rate",
        "get_dividend_yield",
    ):
        assert hasattr(MarketDataProvider, name)
