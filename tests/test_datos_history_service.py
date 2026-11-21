"""Tests del servicio del histórico (Etapa C2, bloque 6).

Reloj fijo (viernes 20-11-2026 10:30 en Nueva York) y caché en
`tmp_path`. Todas las llamadas a `load_history` pasan `years`.
"""

import math
from dataclasses import replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from datos import FakeProvider
from datos.errors import DatosError, EmptyDataError, NetworkError, RateLimitError
from datos.history_cache import covers, read_history, start_for_years, write_history
from datos.history_service import (
    MSG_RATE_HISTORY_MISSING,
    HistoryLoad,
    clean_history,
    history_age_text,
    load_history,
)
from datos.types import PriceHistory

NY = ZoneInfo("America/New_York")
FIXED_NOW = datetime(2026, 11, 20, 10, 30, tzinfo=NY)  # viernes
TODAY = date(2026, 11, 20)
TOMORROW = TODAY + timedelta(days=1)


def make_history(**changes):
    """PriceHistory sucio de prueba (lo limpia clean_history)."""
    values = dict(
        ticker="SPY",
        dates=("2026-11-18", "2026-11-19"),
        close=(100.0, 101.0),
        adj_close=(99.0, 101.0),
        dividends=(),
    )
    values.update(changes)
    return PriceHistory(**values)


def load(provider, tmp_path, label="SPY", years=5, now=FIXED_NOW):
    """Atajo: load_history con el reloj fijo y la caché en tmp_path."""
    return load_history(provider, label, years, now=now, cache_dir=tmp_path)


def fake(**kwargs):
    """FakeProvider con el reloj fijo."""
    return FakeProvider(today=FIXED_NOW, **kwargs)


def symbols_called(provider):
    """Símbolos pedidos a get_history, en orden."""
    return [call[0] for call in provider.history_calls]


# --- clean_history ---


def test_descarta_la_fila_de_hoy_y_las_futuras():
    history = make_history(
        dates=("2026-11-19", "2026-11-20", "2026-11-23"),
        close=(1.0, 2.0, 3.0),
        adj_close=(1.0, 2.0, 3.0),
    )
    cleaned = clean_history(history, TODAY)
    assert cleaned.dates == ("2026-11-19",)


@pytest.mark.parametrize("bad", [float("nan"), 0.0, -5.0, "texto", None, float("inf"), True])
def test_descarta_precios_no_validos_en_close(bad):
    history = make_history(close=(100.0, bad))
    cleaned = clean_history(history, TODAY)
    assert cleaned.dates == ("2026-11-18",)
    assert cleaned.close == (100.0,)
    assert cleaned.adj_close == (99.0,)


@pytest.mark.parametrize("bad", [float("nan"), 0.0, -1.0, "x"])
def test_descarta_precios_no_validos_en_adj_close(bad):
    history = make_history(adj_close=(bad, 101.0))
    cleaned = clean_history(history, TODAY)
    assert cleaned.dates == ("2026-11-19",)


def test_descarta_fechas_duplicadas_y_no_validas_y_ordena():
    history = make_history(
        dates=("2026-11-19", "2026-11-17", "2026-11-19", "no-fecha", "2026-11-18"),
        close=(3.0, 1.0, 9.0, 5.0, 2.0),
        adj_close=(3.0, 1.0, 9.0, 5.0, 2.0),
    )
    cleaned = clean_history(history, TODAY)
    assert cleaned.dates == ("2026-11-17", "2026-11-18", "2026-11-19")
    # De la fecha duplicada se conserva la primera fila.
    assert cleaned.close == (1.0, 2.0, 3.0)


def test_dividendos_solo_positivos_con_fecha_valida():
    history = make_history(
        dividends=(
            ("2026-11-18", 0.5),
            ("2026-11-17", 0.0),
            ("2026-11-16", -1.0),
            ("mal", 0.3),
            ("2026-11-10", float("nan")),
            ("2026-11-12", 0.25),
            ("2026-11-25", 0.4),  # futuro
        )
    )
    cleaned = clean_history(history, TODAY)
    assert cleaned.dividends == (("2026-11-12", 0.25), ("2026-11-18", 0.5))


def test_clean_history_no_lanza_con_basura():
    history = make_history(dates=("2026-11-18", 5, None), close=(1.0,), adj_close=(1.0, 2.0, 3.0))
    cleaned = clean_history(history, TODAY)
    assert cleaned.dates == ("2026-11-18",)


def test_clean_history_conserva_etiqueta_y_origen():
    cleaned = clean_history(make_history(source="cache", loaded_at=FIXED_NOW), FIXED_NOW)
    assert cleaned.ticker == "SPY"
    assert cleaned.source == "cache"
    assert cleaned.loaded_at == FIXED_NOW


def test_tasa_admite_ceros_con_permiso():
    history = make_history(ticker="^IRX", close=(0.0, 0.01), adj_close=(0.0, 0.01))
    assert clean_history(history, TODAY).dates == ("2026-11-19",)
    assert clean_history(history, TODAY, allow_non_positive=True).close == (0.0, 0.01)


# --- Tramo pedido: years + 1 años naturales ---


@pytest.mark.parametrize("years", [1, 5, 15])
def test_pide_years_mas_uno_hasta_manana(tmp_path, years):
    provider = fake()
    loaded, _ = load(provider, tmp_path, years=years)
    start = TODAY.replace(year=TODAY.year - (years + 1))
    assert provider.history_calls == [("SPY", start, TOMORROW), ("^IRX", start, TOMORROW)]
    assert loaded.requested_start == start


def test_tramo_con_29_de_febrero(tmp_path):
    now = datetime(2028, 2, 29, 10, 0, tzinfo=NY)
    provider = FakeProvider(today=now)
    loaded, _ = load_history(provider, "SPY", 5, now=now, cache_dir=tmp_path)
    assert provider.history_calls[0] == ("SPY", date(2022, 2, 28), date(2028, 3, 1))
    assert provider.history_calls[1][1:] == (date(2022, 2, 28), date(2028, 3, 1))


@pytest.mark.parametrize("years", [0, 16, -1, 2.5, True, "5"])
def test_years_fuera_de_rango_lanza_value_error(tmp_path, years):
    with pytest.raises(ValueError):
        load(fake(), tmp_path, years=years)


# --- Carga en vivo ---


def test_carga_en_vivo_limpia_y_escribe_la_cache(tmp_path):
    provider = fake()
    loaded, notices = load(provider, tmp_path, years=2)
    assert isinstance(loaded, HistoryLoad)
    assert notices == []
    assert loaded.source == "live"
    assert loaded.loaded_at == FIXED_NOW
    assert loaded.symbol == "SPY"
    assert loaded.history.ticker == "SPY"
    assert loaded.history.source == "live"
    # La fila de hoy (viernes 20) se descarta.
    assert loaded.history.dates[-1] == "2026-11-19"
    cached, fetched_at, requested_start = read_history("SPY", tmp_path)
    assert cached.dates == loaded.history.dates
    assert fetched_at == FIXED_NOW
    assert requested_start == date(2023, 11, 20)
    assert read_history("^IRX", tmp_path) is not None


def test_irx_en_porcentaje_pasa_a_fraccion(tmp_path):
    loaded, _ = load(fake(irx_percent=4.12), tmp_path)
    assert loaded.rates is not None
    assert loaded.rates.ticker == "^IRX"
    assert loaded.rates.close == pytest.approx([0.0412] * len(loaded.rates.close))
    assert loaded.rates.dates == loaded.history.dates
    # La caché guarda lo que da el proveedor (porcentaje).
    cached, _, _ = read_history("^IRX", tmp_path)
    assert set(cached.close) == {4.12}


def test_fallo_solo_de_irx_no_es_fatal(tmp_path):
    provider = fake(history_fail_symbols={"^IRX": NetworkError})
    loaded, notices = load(provider, tmp_path)
    assert loaded.rates is None
    assert loaded.source == "live"
    assert MSG_RATE_HISTORY_MISSING in notices
    assert read_history("SPY", tmp_path) is not None


def test_fallo_de_irx_usa_la_tasa_guardada_si_la_hay(tmp_path):
    load(fake(irx_percent=3.0), tmp_path)
    later = FIXED_NOW + timedelta(days=3)
    provider = FakeProvider(today=later, history_fail_symbols={"^IRX": RateLimitError})
    loaded, notices = load(provider, tmp_path, now=later)
    assert loaded.rates is not None
    assert loaded.rates.close == pytest.approx([0.03] * len(loaded.rates.close))
    assert any("tasa" in notice for notice in notices)


# --- Índice: ^GSPC y luego ^SPX ---


def test_spx_usa_gspc_primero(tmp_path):
    provider = fake()
    loaded, _ = load(provider, tmp_path, label="SPX")
    assert symbols_called(provider) == ["^GSPC", "^IRX"]
    assert loaded.symbol == "^GSPC"
    assert loaded.history.ticker == "SPX"
    assert (tmp_path / "history" / "SPX.json").is_file()


def test_spx_gspc_vacio_prueba_spx(tmp_path):
    provider = fake(history_empty_symbols={"^GSPC"})
    loaded, _ = load(provider, tmp_path, label="SPX")
    assert symbols_called(provider) == ["^GSPC", "^SPX", "^IRX"]
    assert loaded.symbol == "^SPX"


def test_spx_ambos_vacios_es_error(tmp_path):
    provider = fake(history_empty_symbols={"^GSPC", "^SPX"})
    with pytest.raises(EmptyDataError):
        load(provider, tmp_path, label="SPX")
    assert symbols_called(provider) == ["^GSPC", "^SPX"]


def test_spx_error_de_red_no_reintenta_con_spx(tmp_path):
    provider = fake(history_fail_symbols={"^GSPC": NetworkError})
    with pytest.raises(NetworkError):
        load(provider, tmp_path, label="SPX")
    assert symbols_called(provider) == ["^GSPC"]


# --- Reutilización de la caché ---


def test_cache_fresca_que_cubre_no_llama_al_proveedor(tmp_path):
    load(fake(), tmp_path, years=5)
    provider = fake()
    loaded, notices = load(provider, tmp_path, years=5)
    assert provider.history_calls == []
    assert loaded.source == "cache"
    assert loaded.loaded_at == FIXED_NOW
    assert loaded.symbol is None
    assert loaded.requested_start == start_for_years(TODAY, 5)
    assert loaded.rates is not None
    assert notices == []


def test_menos_anios_que_los_cacheados_reutiliza(tmp_path):
    load(fake(), tmp_path, years=10)
    provider = fake()
    loaded, _ = load(provider, tmp_path, years=5)
    assert provider.history_calls == []
    assert loaded.source == "cache"


def test_mas_anios_que_los_cacheados_descarga_de_nuevo(tmp_path):
    load(fake(), tmp_path, years=5)
    provider = fake()
    loaded, _ = load(provider, tmp_path, years=10)
    start = start_for_years(TODAY, 10)
    assert provider.history_calls == [("SPY", start, TOMORROW), ("^IRX", start, TOMORROW)]
    assert loaded.source == "live"
    _, _, requested_start = read_history("SPY", tmp_path)
    assert requested_start == start


def test_fuente_corta_fresca_no_descarga_en_bucle(tmp_path):
    load(fake(history_years=2), tmp_path, years=10)
    provider = fake(history_years=2)
    loaded, _ = load(provider, tmp_path, years=10)
    assert provider.history_calls == []
    assert loaded.source == "cache"


def test_cache_caducada_descarga_y_reescribe(tmp_path):
    old_now = FIXED_NOW - timedelta(days=7)
    load_history(FakeProvider(today=old_now), "SPY", 5, now=old_now, cache_dir=tmp_path)
    provider = fake()
    loaded, _ = load(provider, tmp_path, years=5)
    assert symbols_called(provider) == ["SPY", "^IRX"]
    assert loaded.source == "live"
    _, fetched_at, _ = read_history("SPY", tmp_path)
    assert fetched_at == FIXED_NOW


def test_cache_del_viernes_sirve_el_lunes(tmp_path):
    load(fake(), tmp_path, years=3)
    monday = datetime(2026, 11, 23, 9, 0, tzinfo=NY)
    # La caché del viernes 10:30 tiene hasta el jueves 19: el lunes la
    # última sesión cerrada es el viernes 20 -> no está al día.
    provider = FakeProvider(today=monday)
    load_history(provider, "SPY", 3, now=monday, cache_dir=tmp_path)
    assert symbols_called(provider) == ["SPY", "^IRX"]
    # El mismo lunes por la tarde ya sirve: se descargó ese día de mercado.
    later = monday + timedelta(hours=6)
    provider = FakeProvider(today=later)
    load_history(provider, "SPY", 3, now=later, cache_dir=tmp_path)
    assert provider.history_calls == []


def test_tasa_caducada_se_descarga_sola(tmp_path):
    load(fake(), tmp_path, years=3)
    # Se borra la tasa guardada: solo se pide ^IRX.
    (tmp_path / "history" / "IRX.json").unlink()
    provider = fake()
    loaded, _ = load(provider, tmp_path, years=3)
    assert symbols_called(provider) == ["^IRX"]
    assert loaded.source == "cache"
    assert loaded.rates is not None


# --- Sin red ---


def test_sin_red_con_cache_usa_la_cache_con_aviso(tmp_path):
    old_now = FIXED_NOW - timedelta(days=7)
    load_history(FakeProvider(today=old_now), "SPY", 5, now=old_now, cache_dir=tmp_path)
    provider = fake(fail_with=NetworkError)
    loaded, notices = load(provider, tmp_path, years=5)
    assert loaded.source == "cache"
    assert loaded.loaded_at == old_now
    assert loaded.rates is not None
    # Tras el fallo no se insiste: una sola solicitud.
    assert symbols_called(provider) == ["SPY"]
    assert notices[0] == NetworkError().message
    assert "histórico guardado de" in notices[1]


def test_sin_red_y_cache_que_no_cubre_usa_la_cache_igual(tmp_path):
    old_now = FIXED_NOW - timedelta(days=7)
    load_history(FakeProvider(today=old_now), "SPY", 2, now=old_now, cache_dir=tmp_path)
    loaded, notices = load(fake(fail_with=NetworkError), tmp_path, years=10)
    assert loaded.source == "cache"
    # requested_start refleja la caché (IP-11), no lo pedido ahora.
    assert loaded.requested_start == start_for_years(old_now, 2)
    assert not covers(loaded.history.dates[0], loaded.requested_start, start_for_years(TODAY, 10))


def test_sin_red_y_cache_vieja_sin_requested_start(tmp_path):
    history = make_history(dates=("2020-01-02", "2026-11-12"), close=(1.0, 2.0), adj_close=(1.0, 2.0))
    write_history(history, FIXED_NOW - timedelta(days=7), None, tmp_path)
    loaded, _ = load(fake(fail_with=NetworkError), tmp_path, years=5)
    assert loaded.requested_start is None
    assert loaded.rates is None
    # `covers` cae al criterio del primer dato.
    assert covers(loaded.history.dates[0], loaded.requested_start, start_for_years(TODAY, 5))
    assert not covers(loaded.history.dates[0], loaded.requested_start, start_for_years(TODAY, 10))


def test_sin_red_y_sin_cache_es_datos_error_en_espanol(tmp_path):
    with pytest.raises(NetworkError) as info:
        load(fake(fail_with=NetworkError), tmp_path)
    assert isinstance(info.value, DatosError)
    assert "conexión" in info.value.message
    assert "No hay histórico guardado" in info.value.message


def test_limite_de_solicitudes_se_mapea(tmp_path):
    with pytest.raises(RateLimitError) as info:
        load(fake(fail_with=RateLimitError), tmp_path)
    assert "limitado" in info.value.message


def test_respuesta_vacia_se_mapea(tmp_path):
    with pytest.raises(EmptyDataError):
        load(fake(history_empty_symbols={"SPY"}), tmp_path)


def test_solo_fila_de_hoy_es_respuesta_vacia(tmp_path):
    class TodayOnly:
        def get_history(self, symbol, start, end):
            return make_history(dates=("2026-11-20",), close=(1.0,), adj_close=(1.0,))

    with pytest.raises(EmptyDataError):
        load(TodayOnly(), tmp_path)


# --- Histórico más corto que lo pedido (AC-C2-4) ---


def test_historico_corto_se_entrega_tal_cual(tmp_path):
    loaded, _ = load(fake(history_years=3), tmp_path, years=10)
    first = date.fromisoformat(loaded.history.dates[0])
    assert date(2023, 11, 20) <= first <= date(2023, 11, 24)
    assert loaded.requested_start == start_for_years(TODAY, 10)


def test_historico_corto_da_el_aviso_con_los_anios_reales(tmp_path):
    backtest = pytest.importorskip("opciones.backtest")
    loaded, _ = load(fake(history_years=3), tmp_path, years=10)
    days = backtest.to_day_numbers(loaded.history.dates)
    _index, years_available, warning = backtest.first_analyzed_index(days, 30, 10)
    # 3 años de datos - 1 año de calentamiento ≈ 2 años analizables.
    assert years_available == pytest.approx(2.0, abs=0.05)
    assert warning is not None
    assert "2" in warning


# --- Textos de antigüedad ---


def test_texto_de_carga_en_vivo(tmp_path):
    loaded, _ = load(fake(), tmp_path)
    hour = FIXED_NOW.astimezone().strftime("%H:%M")
    assert history_age_text(loaded, FIXED_NOW) == f"histórico cargado a las {hour}"


def test_texto_de_cache(tmp_path):
    old_now = FIXED_NOW - timedelta(days=7)
    load_history(FakeProvider(today=old_now), "SPY", 5, now=old_now, cache_dir=tmp_path)
    loaded, _ = load(fake(fail_with=NetworkError), tmp_path)
    when = old_now.astimezone().strftime("%d/%m %H:%M")
    assert history_age_text(loaded, FIXED_NOW) == f"histórico guardado de {when}"


def test_texto_de_cache_del_mismo_dia(tmp_path):
    load(fake(), tmp_path)
    loaded, _ = load(fake(), tmp_path, now=FIXED_NOW + timedelta(hours=1))
    hour = FIXED_NOW.astimezone().strftime("%H:%M")
    assert history_age_text(loaded, FIXED_NOW + timedelta(hours=1)) == (
        f"histórico guardado hoy a las {hour}"
    )


def test_sin_nan_en_lo_cargado(tmp_path):
    loaded, _ = load(fake(dividends=0.02), tmp_path)
    for values in (loaded.history.close, loaded.history.adj_close, loaded.rates.close):
        assert all(math.isfinite(v) for v in values)
    assert loaded.history.dividends
    assert all(amount > 0 for _, amount in loaded.history.dividends)
