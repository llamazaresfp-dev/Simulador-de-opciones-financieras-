"""Tests del proveedor falso y del servicio de carga (Etapa C1, bloque 3d).

AC-C1-3, AC-C1-4, AC-C1-6, AC-C1-9, AC-C1-10, AC-C1-11.

Reglas de estas pruebas:
- El reloj SIEMPRE está fijado (`today`/`now` inyectados): ninguna
  prueba depende de la fecha real del sistema.
- La caché SIEMPRE va a `tmp_path`: la carpeta real `.cache_datos/` no
  se toca desde la suite.
- Sin red: todo sale de `FakeProvider`, respaldado por las fixtures.
"""

from datetime import date, datetime, timedelta

import pytest

import datos
from datos import service
from datos.cache import cache_path, read_snapshot, write_snapshot
from datos.errors import (
    MSG_EMPTY,
    MSG_NETWORK,
    MSG_NO_LIQUID,
    MSG_RATE_LIMIT,
    DatosError,
    EmptyDataError,
    NetworkError,
    RateLimitError,
)
from datos.fake import DEFAULT_OFFSETS, FakeProvider
from datos.provider import MarketDataProvider
from datos.service import (
    MSG_Q_INDEX,
    MSG_Q_MISSING,
    cache_age_text,
    live_age_text,
    load_or_cache,
    load_snapshot,
    load_with_notices,
    rate_from_percent,
)
from datos.cache import MARKET_TZ

# Reloj fijado (hora de Nueva York, en horario de mercado).
TODAY = date(2026, 11, 20)
NOW = datetime(2026, 11, 20, 15, 30, tzinfo=MARKET_TZ)

# Segundo reloj, lejos del primero, para comprobar que el resultado
# relativo (días hasta cada vencimiento) es el mismo.
OTHER_TODAY = date(2027, 6, 7)
OTHER_NOW = datetime(2027, 6, 7, 11, 5, tzinfo=MARKET_TZ)


def make_provider(**kwargs):
    """FakeProvider con el reloj fijado por defecto."""
    kwargs.setdefault("today", TODAY)
    return FakeProvider(**kwargs)


def load(ticker="SPY", tmp_path=None, provider=None, **kwargs):
    """load_with_notices con reloj fijado y caché en tmp_path."""
    if provider is None:
        provider = make_provider()
    kwargs.setdefault("today", TODAY)
    kwargs.setdefault("now", NOW)
    return load_with_notices(ticker, provider, cache_dir=tmp_path, **kwargs)


def offsets_of(snapshot, today=TODAY):
    """Días desde `today` hasta cada vencimiento del snapshot."""
    return [(date.fromisoformat(e) - today).days for e in snapshot.chains]


# --- FakeProvider ---


def test_fake_provider_satisfies_the_protocol():
    assert isinstance(make_provider(), MarketDataProvider)


def test_fake_default_offsets():
    assert DEFAULT_OFFSETS == (10, 17, 45, 90, 150)


def test_fake_expirations_are_relative_to_the_clock():
    provider = make_provider()
    expected = [(TODAY + timedelta(days=o)).isoformat() for o in DEFAULT_OFFSETS]
    assert provider.get_expirations("SPY") == expected


def test_fake_offsets_can_be_overridden():
    provider = make_provider(offsets=(6, 7))
    assert provider.get_expirations("SPY") == ["2026-11-26", "2026-11-27"]


def test_fake_uses_fixture_data():
    provider = make_provider()
    assert provider.get_spot("SPY") == pytest.approx(689.81)
    assert provider.get_spot("AAPL") == pytest.approx(342.56)
    assert provider.get_spot("^SPX") == pytest.approx(6900.0)
    rows = provider.get_chain("SPY", provider.get_expirations("SPY")[0])
    assert len(rows) == 13
    assert {"kind", "strike", "bid", "ask", "oi"} <= set(rows[0])


def test_fake_unknown_ticker_is_empty_data():
    with pytest.raises(EmptyDataError):
        make_provider().get_spot("ZZZZ")


def test_fake_fail_with_raises_on_every_call():
    provider = make_provider(fail_with=NetworkError)
    for call in (
        lambda: provider.get_spot("SPY"),
        lambda: provider.get_expirations("SPY"),
        lambda: provider.get_chain("SPY", "2026-11-30"),
        lambda: provider.get_rate(),
        lambda: provider.get_dividend_yield("SPY"),
    ):
        with pytest.raises(NetworkError):
            call()


def test_fake_returns_copies_of_the_rows():
    provider = make_provider()
    expiry = provider.get_expirations("SPY")[0]
    provider.get_chain("SPY", expiry)[0]["bid"] = -1
    assert provider.get_chain("SPY", expiry)[0]["bid"] > 0


# --- r y q (AC-C1-4) ---


def test_rate_from_percent():
    assert rate_from_percent(4.12) == pytest.approx(0.0412)
    assert rate_from_percent(4.122) == pytest.approx(0.04122)


def test_rate_irx_percent_becomes_fraction(tmp_path):
    snapshot, _ = load(provider=make_provider(irx_percent=4.12), tmp_path=tmp_path)
    assert snapshot.rate == pytest.approx(0.0412)


def test_q_from_trailing_dividend_yield_fraction(tmp_path):
    snapshot, notices = load("SPY", tmp_path=tmp_path)
    assert snapshot.q == pytest.approx(0.0079093)
    assert snapshot.q_source == "yahoo"
    assert MSG_Q_MISSING not in notices


def test_q_missing_is_reported(tmp_path):
    provider = make_provider(dividend_yield=None)
    snapshot, notices = load("AAPL", tmp_path=tmp_path, provider=provider)
    assert snapshot.q is None
    assert snapshot.q_source == "no_disponible"
    assert MSG_Q_MISSING in notices
    assert MSG_Q_MISSING == "sin dividend yield disponible: q = 0, edítalo si hace falta"


def test_q_failure_is_treated_as_missing(tmp_path):
    provider = make_provider(dividend_error=NetworkError)
    snapshot, notices = load("AAPL", tmp_path=tmp_path, provider=provider)
    assert snapshot.q is None
    assert snapshot.q_source == "no_disponible"
    assert MSG_Q_MISSING in notices


@pytest.mark.parametrize("bad", [float("nan"), -0.01, float("inf")])
def test_q_invalid_value_is_treated_as_missing(tmp_path, bad):
    provider = make_provider(dividend_yield=bad)
    snapshot, notices = load("AAPL", tmp_path=tmp_path, provider=provider)
    assert snapshot.q is None
    assert snapshot.q_source == "no_disponible"
    assert MSG_Q_MISSING in notices


def test_index_has_no_q_and_shows_c10_note(tmp_path):
    provider = make_provider()
    snapshot, notices = load("^SPX", tmp_path=tmp_path, provider=provider, label="SPX")
    assert snapshot.q is None
    assert snapshot.q_source == "indice"
    assert MSG_Q_INDEX == "sin dividend yield para índices: edítalo, SPX ≈ 1,2 %"
    assert MSG_Q_INDEX in notices
    assert "get_dividend_yield" not in provider.called
    assert snapshot.ticker == "SPX"
    assert cache_path("SPX", tmp_path).exists()


def test_label_defaults_to_ticker_without_caret(tmp_path):
    snapshot, _ = load("^SPX", tmp_path=tmp_path)
    assert snapshot.ticker == "SPX"
    assert snapshot.q_source == "indice"


# --- Snapshot de una carga completa ---


def test_complete_load(tmp_path):
    snapshot, notices = load("SPY", tmp_path=tmp_path)
    assert snapshot.source == "live"
    assert snapshot.complete is True
    assert snapshot.loaded_at == NOW
    assert snapshot.spot == pytest.approx(689.81)
    # +150 días queda fuera de la ventana 7–120 a propósito.
    assert offsets_of(snapshot) == [10, 17, 45, 90]
    # Cifra medida con la fixture recortada de SPY: 9 de 13 filas líquidas.
    for quotes in snapshot.chains.values():
        assert len(quotes) == 9
    assert notices == []


def test_load_snapshot_returns_only_the_snapshot(tmp_path):
    snapshot = load_snapshot("SPY", make_provider(), today=TODAY, now=NOW, cache_dir=tmp_path)
    assert isinstance(snapshot, datos.MarketSnapshot)
    assert snapshot.complete is True


def test_out_of_window_expiry_is_never_requested(tmp_path):
    provider = make_provider()
    load("SPY", tmp_path=tmp_path, provider=provider)
    requested = [(date.fromisoformat(e) - TODAY).days for e in provider.chain_calls]
    assert requested == [10, 17, 45, 90]


def test_window_exact_edges_at_service_level(tmp_path):
    provider = make_provider(offsets=(6, 7, 120, 121))
    snapshot, _ = load("SPY", tmp_path=tmp_path, provider=provider)
    assert offsets_of(snapshot) == [7, 120]


def test_expiry_order_is_ascending(tmp_path):
    provider = make_provider(offsets=(90, 10, 45))
    snapshot, _ = load("SPY", tmp_path=tmp_path, provider=provider)
    assert offsets_of(snapshot) == [10, 45, 90]


def test_two_clocks_give_the_same_relative_result(tmp_path):
    first, _ = load("SPY", tmp_path=tmp_path / "a")
    other_provider = FakeProvider(today=OTHER_TODAY)
    second, _ = load(
        "SPY", tmp_path=tmp_path / "b", provider=other_provider, today=OTHER_TODAY, now=OTHER_NOW
    )
    assert offsets_of(first, TODAY) == offsets_of(second, OTHER_TODAY)
    assert list(first.chains.values()) == list(second.chains.values())


def test_clock_can_be_a_new_york_datetime(tmp_path):
    # `today` puede llegar como datetime con zona: se usa su fecha en Nueva York.
    snapshot, _ = load("SPY", tmp_path=tmp_path, today=NOW)
    assert offsets_of(snapshot) == [10, 17, 45, 90]


def test_today_defaults_to_the_market_date_of_now(tmp_path):
    provider = make_provider()
    snapshot, _ = load_with_notices("SPY", provider, now=NOW, cache_dir=tmp_path)
    assert offsets_of(snapshot) == [10, 17, 45, 90]


# --- Solo opciones líquidas (AC-C1-6) ---


def test_only_liquid_quotes_in_snapshot(tmp_path):
    provider = make_provider(fixture="bid_zero", spot=100.0)
    snapshot, _ = load("SPY", tmp_path=tmp_path, provider=provider)
    for quotes in snapshot.chains.values():
        assert len(quotes) == 2
        assert all(q.bid > 0 and q.ask > 0 for q in quotes)


def test_expiry_without_liquid_options_is_not_offered(tmp_path):
    provider = make_provider(chain_fixtures={17: "spx_weekend"})
    snapshot, notices = load("SPY", tmp_path=tmp_path, provider=provider)
    assert offsets_of(snapshot) == [10, 45, 90]
    # No es un fallo: la carga sigue siendo completa.
    assert snapshot.complete is True
    assert notices == []


def test_nothing_liquid_raises_no_liquid(tmp_path):
    provider = make_provider(fixture="spx_weekend")
    with pytest.raises(EmptyDataError) as info:
        load("^SPX", tmp_path=tmp_path, provider=provider)
    assert info.value.message == MSG_NO_LIQUID
    assert not cache_path("SPX", tmp_path).exists()


def test_no_expiry_in_window_raises_no_liquid(tmp_path):
    provider = make_provider(offsets=(3, 150))
    with pytest.raises(EmptyDataError) as info:
        load("SPY", tmp_path=tmp_path, provider=provider)
    assert info.value.message == MSG_NO_LIQUID
    assert provider.chain_calls == []


# --- Fallos parciales y límite de solicitudes (429) ---


def test_partial_chain_failure_skips_that_expiry(tmp_path):
    provider = make_provider(chain_errors={17: NetworkError})
    snapshot, notices = load("SPY", tmp_path=tmp_path, provider=provider)
    assert offsets_of(snapshot) == [10, 45, 90]
    assert snapshot.complete is False
    assert len(provider.chain_calls) == 4
    assert any("1 de 4" in n for n in notices)


def test_first_rate_limit_stops_further_requests(tmp_path):
    provider = make_provider(chain_errors={17: RateLimitError})
    snapshot, notices = load("SPY", tmp_path=tmp_path, provider=provider)
    # Tras el 429 en el 2.º vencimiento no se pide ninguno más.
    assert len(provider.chain_calls) == 2
    assert offsets_of(snapshot) == [10]
    assert snapshot.complete is False
    assert any("1 de 4" in n for n in notices)


def test_rate_limit_with_nothing_loaded_raises(tmp_path):
    provider = make_provider(chain_errors={10: RateLimitError})
    with pytest.raises(RateLimitError) as info:
        load("SPY", tmp_path=tmp_path, provider=provider)
    assert info.value.message == MSG_RATE_LIMIT
    assert len(provider.chain_calls) == 1
    assert not cache_path("SPY", tmp_path).exists()


def test_all_chains_failing_raises_the_error(tmp_path):
    errors = {o: NetworkError for o in DEFAULT_OFFSETS}
    provider = make_provider(chain_errors=errors)
    with pytest.raises(NetworkError) as info:
        load("SPY", tmp_path=tmp_path, provider=provider)
    assert info.value.message == MSG_NETWORK


# --- Errores con mensaje en español (AC-C1-11) ---


@pytest.mark.parametrize(
    "error, message",
    [(NetworkError, MSG_NETWORK), (RateLimitError, MSG_RATE_LIMIT), (EmptyDataError, MSG_EMPTY)],
)
def test_provider_failure_raises_datos_error_with_message(tmp_path, error, message):
    provider = make_provider(fail_with=error)
    with pytest.raises(DatosError) as info:
        load("SPY", tmp_path=tmp_path, provider=provider)
    assert isinstance(info.value, error)
    assert info.value.message == message
    assert not cache_path("SPY", tmp_path).exists()


def test_no_expirations_is_empty_data(tmp_path):
    provider = make_provider(offsets=())
    with pytest.raises(EmptyDataError) as info:
        load("SPY", tmp_path=tmp_path, provider=provider)
    assert info.value.message == MSG_EMPTY


@pytest.mark.parametrize("bad_spot", [0.0, -5.0, float("nan")])
def test_bad_spot_is_empty_data(tmp_path, bad_spot):
    provider = make_provider(spot=bad_spot)
    with pytest.raises(EmptyDataError):
        load("SPY", tmp_path=tmp_path, provider=provider)


def test_bad_rate_is_empty_data(tmp_path):
    provider = make_provider(irx_percent=float("nan"))
    with pytest.raises(EmptyDataError):
        load("SPY", tmp_path=tmp_path, provider=provider)


# --- Caché (AC-C1-10) ---


def test_successful_load_writes_the_cache(tmp_path):
    snapshot, _ = load("SPY", tmp_path=tmp_path)
    cached = read_snapshot("SPY", tmp_path, today=TODAY)
    assert cached is not None
    assert cached.source == "cache"
    assert cached.chains == snapshot.chains
    assert cached.loaded_at == NOW


def test_partial_load_does_not_overwrite_richer_cache(tmp_path):
    load("SPY", tmp_path=tmp_path)
    provider = make_provider(chain_errors={17: RateLimitError})
    partial, notices = load("SPY", tmp_path=tmp_path, provider=provider)
    assert partial.complete is False
    # El aviso de la caché llega a la lista de avisos.
    assert any("se conserva la caché" in n for n in notices)
    cached = read_snapshot("SPY", tmp_path, today=TODAY)
    assert offsets_of(cached) == [10, 17, 45, 90]


def test_complete_load_replaces_the_cache(tmp_path):
    first = make_provider(offsets=(10, 17, 45, 90))
    load("SPY", tmp_path=tmp_path, provider=first)
    second = make_provider(offsets=(10, 45))
    load("SPY", tmp_path=tmp_path, provider=second)
    cached = read_snapshot("SPY", tmp_path, today=TODAY)
    assert offsets_of(cached) == [10, 45]


# --- Respaldo con la caché ---


def test_load_or_cache_live_when_provider_works(tmp_path):
    snapshot, notices = load_or_cache(
        "SPY", make_provider(), today=TODAY, now=NOW, cache_dir=tmp_path
    )
    assert snapshot.source == "live"
    assert notices == []


def test_load_or_cache_falls_back_to_cache(tmp_path):
    saved_at = datetime(2026, 11, 19, 10, 0, tzinfo=MARKET_TZ)
    load("SPY", tmp_path=tmp_path, now=saved_at)
    snapshot, notices = load_or_cache(
        "SPY", make_provider(fail_with=NetworkError), today=TODAY, now=NOW, cache_dir=tmp_path
    )
    assert snapshot.source == "cache"
    assert snapshot.loaded_at == saved_at
    assert notices[0] == MSG_NETWORK
    assert cache_age_text(saved_at) in notices[1]


def test_load_or_cache_without_cache(tmp_path):
    snapshot, notices = load_or_cache(
        "SPY", make_provider(fail_with=RateLimitError), today=TODAY, now=NOW, cache_dir=tmp_path
    )
    assert snapshot is None
    assert notices == [MSG_RATE_LIMIT, service.MSG_NO_CACHE]


def test_load_or_cache_index_uses_label(tmp_path):
    load("^SPX", tmp_path=tmp_path, label="SPX")
    snapshot, _ = load_or_cache(
        "^SPX",
        make_provider(fail_with=NetworkError),
        today=TODAY,
        now=NOW,
        cache_dir=tmp_path,
        label="SPX",
    )
    assert snapshot.source == "cache"
    assert snapshot.ticker == "SPX"


# --- Textos de antigüedad (AC-C1-9) ---


def test_live_age_text_uses_local_time():
    expected = NOW.astimezone().strftime("%H:%M")
    assert live_age_text(NOW) == f"datos con ~15 min de retraso; cargados a las {expected}"


def test_cache_age_text_uses_local_time():
    expected = NOW.astimezone().strftime("%d/%m %H:%M")
    assert cache_age_text(NOW) == f"datos guardados de {expected}"


def test_age_text_by_snapshot_source(tmp_path):
    snapshot, _ = load("SPY", tmp_path=tmp_path)
    assert service.age_text(snapshot) == live_age_text(NOW)
    cached = read_snapshot("SPY", tmp_path, today=TODAY)
    assert service.age_text(cached) == cache_age_text(NOW)


# --- Reexportaciones ---


def test_package_reexports_service_and_fake():
    assert datos.FakeProvider is FakeProvider
    assert datos.load_snapshot is load_snapshot
    assert datos.load_with_notices is load_with_notices
    assert datos.load_or_cache is load_or_cache
    assert datos.live_age_text is live_age_text
    assert datos.cache_age_text is cache_age_text


def test_write_snapshot_is_the_one_from_cache():
    # El servicio guarda con la función del bloque 3c, no con una copia.
    assert service.write_snapshot is write_snapshot
