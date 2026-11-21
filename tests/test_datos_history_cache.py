"""Tests de la caché del histórico `.cache_datos/history/` (Etapa C2, bloque 5).

Todas las pruebas escriben en `tmp_path`: nunca en el `.cache_datos/` real.
"""

import json
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from datos import history_cache
from datos.history_cache import (
    HISTORY_SCHEMA_VERSION,
    covers,
    history_path,
    is_fresh,
    last_closed_session,
    read_history,
    start_for_years,
    write_history,
)
from datos.types import PriceHistory

NY = ZoneInfo("America/New_York")
FETCHED = datetime(2026, 11, 20, 10, 30, tzinfo=NY)  # viernes
REQUESTED = date(2024, 11, 20)


def make_history(ticker="SPY", **changes):
    """PriceHistory de prueba con dos días y un dividendo."""
    values = dict(
        ticker=ticker,
        dates=("2026-11-18", "2026-11-19"),
        close=(100.0, 101.5),
        adj_close=(99.5, 101.5),
        dividends=(("2026-11-19", 0.5),),
    )
    values.update(changes)
    return PriceHistory(**values)


def write_raw(tmp_path, label, data):
    """Escribe un JSON a mano en la carpeta de la caché del histórico."""
    path = history_path(label, tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def valid_raw(**changes):
    """Contenido válido de un archivo de caché, con cambios."""
    data = {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "ticker": "SPY",
        "fetched_at": FETCHED.isoformat(),
        "requested_start": "2024-11-20",
        "dates": ["2026-11-18", "2026-11-19"],
        "close": [100.0, 101.5],
        "adj_close": [99.5, 101.5],
        "dividends": [["2026-11-19", 0.5]],
    }
    data.update(changes)
    return data


# --- Rutas ---


def test_rutas_en_la_subcarpeta_history(tmp_path):
    assert history_path("SPY", tmp_path) == tmp_path / "history" / "SPY.json"
    assert history_path("SPX", tmp_path) == tmp_path / "history" / "SPX.json"
    # Nunca "^SPX.json" ni "^IRX.json".
    assert history_path("^SPX", tmp_path) == tmp_path / "history" / "SPX.json"
    assert history_path("^IRX", tmp_path) == tmp_path / "history" / "IRX.json"


def test_ruta_por_defecto_en_la_raiz_del_repo():
    path = history_path("SPY")
    assert path.parent.name == "history"
    assert path.parent.parent.name == ".cache_datos"


def test_etiqueta_no_valida_lanza_value_error(tmp_path):
    with pytest.raises(ValueError):
        history_path("../x", tmp_path)


# --- Escritura y lectura ---


def test_ida_y_vuelta(tmp_path):
    written, notice = write_history(make_history(), FETCHED, REQUESTED, tmp_path)
    assert (written, notice) == (True, None)
    result = read_history("SPY", tmp_path)
    assert result is not None
    history, fetched_at, requested_start = result
    assert history.ticker == "SPY"
    assert history.dates == ("2026-11-18", "2026-11-19")
    assert history.close == (100.0, 101.5)
    assert history.adj_close == (99.5, 101.5)
    assert history.dividends == (("2026-11-19", 0.5),)
    assert history.source == "cache"
    assert history.loaded_at == FETCHED
    assert fetched_at == FETCHED
    assert requested_start == REQUESTED


def test_formato_del_archivo(tmp_path):
    write_history(make_history(), FETCHED, REQUESTED, tmp_path)
    data = json.loads(history_path("SPY", tmp_path).read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["ticker"] == "SPY"
    assert data["fetched_at"] == FETCHED.isoformat()
    assert data["requested_start"] == "2024-11-20"


def test_irx_se_guarda_en_irx_json(tmp_path):
    rates = make_history(ticker="^IRX", close=(4.1, 4.2), adj_close=(4.1, 4.2), dividends=())
    write_history(rates, FETCHED, REQUESTED, tmp_path)
    assert (tmp_path / "history" / "IRX.json").is_file()
    history, _, _ = read_history("^IRX", tmp_path)
    assert history.close == (4.1, 4.2)


def test_requested_start_none_se_guarda_y_se_lee(tmp_path):
    write_history(make_history(), FETCHED, None, tmp_path)
    _, _, requested_start = read_history("SPY", tmp_path)
    assert requested_start is None


def test_cache_vieja_sin_requested_start_se_lee_con_none(tmp_path):
    data = valid_raw()
    del data["requested_start"]
    write_raw(tmp_path, "SPY", data)
    result = read_history("SPY", tmp_path)
    assert result is not None
    assert result[2] is None


def test_fetched_at_sin_zona_se_rechaza_al_escribir(tmp_path):
    with pytest.raises(ValueError):
        write_history(make_history(), datetime(2026, 11, 20, 10, 30), REQUESTED, tmp_path)
    assert not history_path("SPY", tmp_path).exists()


def test_escritura_atomica_no_deja_temporales(tmp_path):
    write_history(make_history(), FETCHED, REQUESTED, tmp_path)
    write_history(make_history(close=(1.0, 2.0)), FETCHED, REQUESTED, tmp_path)
    assert sorted(p.name for p in (tmp_path / "history").iterdir()) == ["SPY.json"]


def test_fallo_de_escritura_no_destruye_la_vieja(tmp_path, monkeypatch):
    write_history(make_history(), FETCHED, REQUESTED, tmp_path)

    def broken_replace(src, dst):
        raise OSError("disco lleno")

    monkeypatch.setattr(os, "replace", broken_replace)
    written, notice = write_history(make_history(close=(1.0, 2.0)), FETCHED, REQUESTED, tmp_path)
    assert written is False
    assert "No se pudo guardar" in notice
    monkeypatch.undo()
    history, _, _ = read_history("SPY", tmp_path)
    assert history.close == (100.0, 101.5)
    assert sorted(p.name for p in (tmp_path / "history").iterdir()) == ["SPY.json"]


def test_sin_archivo_devuelve_none(tmp_path):
    assert read_history("SPY", tmp_path) is None


def test_json_corrupto_devuelve_none(tmp_path):
    path = history_path("SPY", tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{no es json", encoding="utf-8")
    assert read_history("SPY", tmp_path) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"schema_version": None},
        {"ticker": 5},
        {"fetched_at": "ayer"},
        {"fetched_at": "2026-11-20T10:30:00"},  # sin zona
        {"requested_start": "no-fecha"},
        {"dates": ["2026-11-18"]},  # longitudes distintas
        {"close": [100.0]},
        {"adj_close": [99.5, 101.5, 102.0]},
        {"dates": ["2026-11-18", "18/11/2026"]},
        {"close": [100.0, "101"]},
        {"close": [100.0, True]},
        {"dates": [], "close": [], "adj_close": []},
        {"dividends": [["2026-11-19"]]},
        {"dividends": [["mal", 0.5]]},
        {"dividends": "no-lista"},
    ],
)
def test_contenido_no_valido_devuelve_none(tmp_path, changes):
    write_raw(tmp_path, "SPY", valid_raw(**changes))
    assert read_history("SPY", tmp_path) is None


@pytest.mark.parametrize("field", ["ticker", "fetched_at", "dates", "close", "adj_close", "dividends"])
def test_campo_ausente_devuelve_none(tmp_path, field):
    data = valid_raw()
    del data[field]
    write_raw(tmp_path, "SPY", data)
    assert read_history("SPY", tmp_path) is None


def test_lista_de_raiz_devuelve_none(tmp_path):
    write_raw(tmp_path, "SPY", [1, 2, 3])
    assert read_history("SPY", tmp_path) is None


# --- Frescura ---


def test_ultima_sesion_cerrada():
    assert last_closed_session(date(2026, 11, 20)) == date(2026, 11, 19)  # viernes -> jueves
    assert last_closed_session(date(2026, 11, 23)) == date(2026, 11, 20)  # lunes -> viernes
    assert last_closed_session(date(2026, 11, 22)) == date(2026, 11, 20)  # domingo -> viernes


def test_mismo_dia_de_mercado_es_fresca_aunque_el_dato_sea_viejo():
    assert is_fresh(FETCHED, "2020-01-02", date(2026, 11, 20))


def test_lunes_con_dato_del_viernes_es_fresca():
    fetched = datetime(2026, 11, 21, 9, 0, tzinfo=NY)  # sábado
    assert is_fresh(fetched, "2026-11-20", date(2026, 11, 23))


def test_martes_festivo_sin_dato_no_es_fresca():
    # Miércoles 25-11: la última sesión "cerrada" es el martes 24
    # (no se conocen festivos); la caché solo llega al lunes 23.
    fetched = datetime(2026, 11, 24, 9, 0, tzinfo=NY)
    assert not is_fresh(fetched, "2026-11-23", date(2026, 11, 25))


def test_ayer_sin_dato_no_es_fresca():
    fetched = datetime(2026, 11, 19, 9, 0, tzinfo=NY)
    assert not is_fresh(fetched, "2026-11-18", date(2026, 11, 20))


def test_borde_de_medianoche_usa_nueva_york():
    # 23:30 en Nueva York del jueves = 04:30 UTC del viernes.
    fetched_utc = datetime(2026, 11, 20, 4, 30, tzinfo=timezone.utc)
    # Para Nueva York aún es jueves 19: no es el mismo día que el viernes 20.
    assert not is_fresh(fetched_utc, "2026-11-18", date(2026, 11, 20))
    # Y sí es el mismo día de mercado que el jueves 19.
    assert is_fresh(fetched_utc, "2026-11-18", date(2026, 11, 19))


def test_is_fresh_acepta_date_como_ultimo_dato_y_datetime_como_hoy():
    assert is_fresh(FETCHED - timedelta(days=3), date(2026, 11, 19), FETCHED)


# --- Inicio del tramo pedido ---


def test_start_for_years_suma_un_año_de_calentamiento():
    assert start_for_years(date(2026, 11, 20), 1) == date(2024, 11, 20)
    assert start_for_years(date(2026, 11, 20), 5) == date(2020, 11, 20)
    assert start_for_years(date(2026, 11, 20), 15) == date(2010, 11, 20)


def test_start_for_years_29_de_febrero():
    # 2028 es bisiesto; 2027 y 2022 no -> 28-feb.
    assert start_for_years(date(2028, 2, 29), 0) == date(2027, 2, 28)
    assert start_for_years(date(2028, 2, 29), 5) == date(2022, 2, 28)
    # 2024 sí es bisiesto: se conserva el 29.
    assert start_for_years(date(2028, 2, 29), 3) == date(2024, 2, 29)


def test_start_for_years_acepta_reloj_con_zona():
    assert start_for_years(FETCHED, 10) == date(2015, 11, 20)


# --- Cobertura del tramo pedido (IP-10) ---


START = date(2020, 11, 20)


def test_cubre_si_el_primer_dato_es_el_inicio():
    assert covers("2020-11-20", None, START)


def test_cubre_en_el_borde_de_tolerancia():
    assert covers(START + timedelta(days=7), None, START)


def test_no_cubre_un_dia_despues_de_la_tolerancia():
    assert not covers(START + timedelta(days=8), None, START)


def test_cubre_con_fuente_corta_si_se_pidio_desde_antes():
    # La fuente solo tenía datos desde 2023, pero se pidió desde 2019.
    assert covers("2023-01-03", date(2019, 11, 20), START)
    assert covers("2023-01-03", "2020-11-20", START)


def test_no_cubre_si_se_pidio_despues_y_el_dato_es_posterior():
    assert not covers("2023-01-03", date(2022, 11, 20), START)


def test_requested_start_none_se_ignora():
    assert not covers("2023-01-03", None, START)
    assert covers("2020-11-23", None, START)


def test_tolerancia_configurable():
    assert covers(START + timedelta(days=10), None, START, tolerance_days=10)
    assert not covers(START + timedelta(days=1), None, START, tolerance_days=0)


# --- Nada fuera de tmp_path ---


def test_no_modifica_cache_py():
    # La caché del histórico reutiliza ayudantes de datos.cache sin copiarlos.
    from datos import cache

    assert history_cache._atomic_write_json is cache._atomic_write_json
    assert history_cache._file_label is cache._file_label
