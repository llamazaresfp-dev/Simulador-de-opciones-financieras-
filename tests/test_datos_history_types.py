"""Tests del histórico: tipo PriceHistory, interfaz HistoryProvider,
FakeProvider.get_history y mapa de símbolos (Etapa C2, bloque 4).

El reloj siempre se fija: viernes 20-11-2026 10:30 en Nueva York.
"""

import dataclasses
import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from datos import (
    FakeProvider,
    HistoryProvider,
    MarketDataProvider,
    PriceHistory,
    RATE_HISTORY_SYMBOL,
    history_symbols,
)
from datos.errors import EmptyDataError, NetworkError, RateLimitError
from datos.fake import history_seed_for
from datos.tickers import CURATED_TICKERS, HISTORY_SYMBOLS

FIXED_NOW = datetime(2026, 11, 20, 10, 30, tzinfo=ZoneInfo("America/New_York"))
TODAY = date(2026, 11, 20)  # viernes
START = date(2024, 11, 20)
END = TODAY + timedelta(days=1)


def make_history(**changes):
    """PriceHistory de prueba; `changes` sobrescribe campos."""
    values = dict(
        ticker="SPY",
        dates=("2026-11-18", "2026-11-19"),
        close=(100.0, 101.0),
        adj_close=(99.5, 100.5),
        dividends=(("2026-11-18", 0.5),),
    )
    values.update(changes)
    return PriceHistory(**values)


# --- PriceHistory ---


def test_price_history_campos_y_valores_por_defecto():
    history = make_history()
    assert history.ticker == "SPY"
    assert history.dates == ("2026-11-18", "2026-11-19")
    assert history.close == (100.0, 101.0)
    assert history.adj_close == (99.5, 100.5)
    assert history.dividends == (("2026-11-18", 0.5),)
    assert history.source == "live"
    assert history.loaded_at is None


def test_price_history_es_inmutable():
    history = make_history()
    with pytest.raises(dataclasses.FrozenInstanceError):
        history.ticker = "QQQ"


# --- HistoryProvider ---


def test_clase_minima_cumple_history_provider():
    class Minimal:
        def get_history(self, symbol, start, end):
            return make_history()

    assert isinstance(Minimal(), HistoryProvider)
    # Una clase sin get_history no lo cumple.
    assert not isinstance(object(), HistoryProvider)


def test_fake_provider_cumple_las_dos_interfaces():
    provider = FakeProvider(today=FIXED_NOW)
    assert isinstance(provider, HistoryProvider)
    assert isinstance(provider, MarketDataProvider)


# --- Mapa de símbolos ---


def test_history_symbols_spx_prueba_gspc_y_luego_spx():
    assert history_symbols("SPX") == ("^GSPC", "^SPX")


def test_history_symbols_resto_su_propio_ticker():
    assert history_symbols("SPY") == ("SPY",)
    assert history_symbols("AAPL") == ("AAPL",)
    assert HISTORY_SYMBOLS == {"SPX": ("^GSPC", "^SPX")}


def test_simbolo_de_la_tasa():
    assert RATE_HISTORY_SYMBOL == "^IRX"


# --- FakeProvider.get_history: determinismo ---


def test_get_history_determinista():
    first = FakeProvider(today=FIXED_NOW).get_history("SPY", START, END)
    second = FakeProvider(today=FIXED_NOW).get_history("SPY", START, END)
    assert first == second


def test_dos_tickers_dan_series_distintas():
    provider = FakeProvider(today=FIXED_NOW)
    spy = provider.get_history("SPY", START, END)
    qqq = provider.get_history("QQQ", START, END)
    assert spy.dates == qqq.dates
    assert spy.close != qqq.close


def test_semilla_es_suma_de_ord_no_hash():
    assert history_seed_for("SPY") == ord("S") + ord("P") + ord("Y")
    assert history_seed_for("SPY", 5) == ord("S") + ord("P") + ord("Y") + 5


def test_parametro_seed_cambia_la_serie():
    base = FakeProvider(today=FIXED_NOW).get_history("SPY", START, END)
    other = FakeProvider(today=FIXED_NOW, seed=7).get_history("SPY", START, END)
    assert base.close != other.close


def test_rangos_distintos_comparten_los_mismos_precios():
    # El mismo día tiene el mismo precio aunque se pida otro tramo.
    provider = FakeProvider(today=FIXED_NOW)
    long = provider.get_history("SPY", date(2020, 1, 1), END)
    short = provider.get_history("SPY", START, END)
    prices = dict(zip(long.dates, long.close))
    for day, price in zip(short.dates, short.close):
        assert prices[day] == price


# --- FakeProvider.get_history: fechas y precios ---


def test_dias_habiles_sin_fines_de_semana_y_ascendentes():
    history = FakeProvider(today=FIXED_NOW).get_history("SPY", START, END)
    days = [date.fromisoformat(d) for d in history.dates]
    assert all(d.weekday() < 5 for d in days)
    assert days == sorted(days)
    assert len(set(days)) == len(days)
    # Dos años de días hábiles (sin festivos): ~522 sesiones.
    assert 520 <= len(days) <= 524


def test_start_inclusivo_end_exclusivo():
    provider = FakeProvider(today=FIXED_NOW)
    # 18-11-2026 es miércoles; end = 20-11 (viernes) queda fuera.
    history = provider.get_history("SPY", date(2026, 11, 18), date(2026, 11, 20))
    assert history.dates == ("2026-11-18", "2026-11-19")


def test_incluye_hoy_si_es_dia_habil():
    # Como Yahoo: la fila de hoy llega (el servicio la descarta luego).
    history = FakeProvider(today=FIXED_NOW).get_history("SPY", START, END)
    assert history.dates[-1] == "2026-11-20"


def test_precios_positivos_finitos():
    history = FakeProvider(today=FIXED_NOW).get_history("SPY", START, END)
    assert all(math.isfinite(p) and p > 0 for p in history.close)
    assert all(math.isfinite(p) and p > 0 for p in history.adj_close)
    assert len(history.close) == len(history.adj_close) == len(history.dates)
    assert history.ticker == "SPY"
    assert history.source == "live"


def test_sin_dividendos_adj_close_igual_a_close():
    history = FakeProvider(today=FIXED_NOW).get_history("SPY", START, END)
    assert history.dividends == ()
    assert history.adj_close == history.close


def test_dividendos_trimestrales_opcionales():
    history = FakeProvider(today=FIXED_NOW, dividends=0.02).get_history("SPY", START, END)
    # Dos años -> unos 8 dividendos trimestrales, con fecha del tramo y > 0.
    assert 7 <= len(history.dividends) <= 9
    for day, amount in history.dividends:
        assert day in history.dates
        assert amount > 0
    # El cierre ajustado nunca supera al cierre (se descuentan dividendos).
    assert all(a <= c for a, c in zip(history.adj_close, history.close))
    assert history.adj_close[0] < history.close[0]
    # Tras el último dividendo, ajustado y normal coinciden.
    assert history.adj_close[-1] == pytest.approx(history.close[-1])


def test_indice_sin_dividendos_aunque_se_pidan():
    history = FakeProvider(today=FIXED_NOW, dividends=0.02).get_history("^GSPC", START, END)
    assert history.dividends == ()


def test_irx_devuelve_porcentaje_constante():
    history = FakeProvider(today=FIXED_NOW).get_history("^IRX", START, END)
    assert set(history.close) == {4.122}
    assert all(0 <= v <= 20 for v in history.close)


def test_irx_con_escalon():
    provider = FakeProvider(
        today=FIXED_NOW,
        irx_percent=1.0,
        irx_percent_series=(("2025-06-02", 3.5), ("2026-01-05", 4.25)),
    )
    history = provider.get_history("^IRX", START, END)
    values = dict(zip(history.dates, history.close))
    assert values["2025-05-30"] == 1.0
    assert values["2025-06-02"] == 3.5
    assert values["2026-01-02"] == 3.5
    assert values["2026-01-05"] == 4.25
    assert values["2026-11-19"] == 4.25


# --- Errores ---


def test_ticker_desconocido_es_respuesta_vacia():
    with pytest.raises(EmptyDataError) as info:
        FakeProvider(today=FIXED_NOW).get_history("XYZ", START, END)
    assert "vacía" in info.value.message


def test_rango_sin_dias_es_respuesta_vacia():
    provider = FakeProvider(today=FIXED_NOW)
    # Sábado y domingo: ningún día hábil.
    with pytest.raises(EmptyDataError):
        provider.get_history("SPY", date(2026, 11, 14), date(2026, 11, 16))
    # Tramo futuro.
    with pytest.raises(EmptyDataError):
        provider.get_history("SPY", date(2027, 1, 1), date(2027, 2, 1))


def test_fail_with_falla_tambien_get_history():
    provider = FakeProvider(today=FIXED_NOW, fail_with=RateLimitError)
    with pytest.raises(RateLimitError):
        provider.get_history("SPY", START, END)
    assert provider.history_calls == [("SPY", START, END)]


def test_todos_los_tickers_curados_tienen_historico():
    provider = FakeProvider(today=FIXED_NOW)
    for tickers in CURATED_TICKERS.values():
        for label in tickers:
            for symbol in history_symbols(label):
                assert provider.get_history(symbol, START, END).dates


# --- Mandos nuevos (solo afectan a lo indicado) ---


def test_history_calls_registra_cada_llamada():
    provider = FakeProvider(today=FIXED_NOW)
    provider.get_history("SPY", START, END)
    provider.get_history("^IRX", START, END)
    assert provider.history_calls == [("SPY", START, END), ("^IRX", START, END)]
    assert provider.called == ["get_history", "get_history"]


def test_history_empty_symbols_solo_afecta_a_esos_simbolos():
    provider = FakeProvider(today=FIXED_NOW, history_empty_symbols={"^GSPC"})
    with pytest.raises(EmptyDataError):
        provider.get_history("^GSPC", START, END)
    assert provider.get_history("^SPX", START, END).dates
    assert provider.get_history("SPY", START, END).dates


def test_history_fail_symbols_solo_afecta_a_esos_simbolos():
    provider = FakeProvider(
        today=FIXED_NOW, history_fail_symbols={"^IRX": NetworkError, "^GSPC": NetworkError()}
    )
    with pytest.raises(NetworkError):
        provider.get_history("^IRX", START, END)
    with pytest.raises(NetworkError):
        provider.get_history("^GSPC", START, END)
    assert provider.get_history("SPY", START, END).dates
    assert [call[0] for call in provider.history_calls] == ["^IRX", "^GSPC", "SPY"]


def test_history_years_recorta_hacia_atras():
    provider = FakeProvider(today=FIXED_NOW, history_years=1)
    history = provider.get_history("SPY", date(2020, 1, 1), END)
    assert history.dates[0] >= "2025-11-20"
    assert history.dates[0] <= "2025-11-24"
    # Pedir un tramo anterior al tope no devuelve nada.
    with pytest.raises(EmptyDataError):
        provider.get_history("SPY", date(2020, 1, 1), date(2021, 1, 1))


def test_valores_por_defecto_no_cambian_la_salida():
    base = FakeProvider(today=FIXED_NOW).get_history("SPY", START, END)
    explicit = FakeProvider(
        today=FIXED_NOW,
        history_empty_symbols=None,
        history_fail_symbols=None,
        history_years=None,
    ).get_history("SPY", START, END)
    assert base == explicit


def test_metodos_de_opciones_no_cambian():
    # Los métodos de C1 siguen igual con los parámetros nuevos.
    provider = FakeProvider(today=FIXED_NOW, history_years=1, history_empty_symbols={"SPY"})
    assert provider.get_spot("SPY") > 0
    assert provider.get_rate() == pytest.approx(0.04122)
    assert provider.called == ["get_spot", "get_rate"]
    assert provider.history_calls == []
