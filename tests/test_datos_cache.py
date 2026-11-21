"""Tests de la caché local de snapshots (Etapa C1, bloque 3c).

AC-C1-10 y AC-C1-11. Todas las pruebas escriben SIEMPRE en `tmp_path`:
la carpeta real `.cache_datos/` del repositorio nunca se toca desde la
suite. Los snapshots se arman a mano con `MarketSnapshot`/`OptionQuote`
y las fixtures del bloque 3b (sin proveedor falso ni servicio).
"""

import json
import os
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import datos
from datos import cache
from datos.cache import (
    SCHEMA_VERSION,
    cache_path,
    is_richer_or_equal,
    market_today,
    read_snapshot,
    richness,
    write_snapshot,
)
from datos.filters import DEFAULT_RULES, LiquidityRules, clean_row, filter_chain
from datos.types import MarketSnapshot, OptionQuote

FIXTURES_DIR = Path(__file__).parent / "fixtures"
NEW_YORK = ZoneInfo("America/New_York")

# Reloj fijado: todas las fechas de vencimiento se construyen relativas a él.
TODAY = date(2026, 11, 20)
LOADED_AT = datetime(2026, 11, 20, 15, 30, tzinfo=NEW_YORK)


def load_fixture(name):
    """Lee tests/fixtures/<name>.json."""
    with open(FIXTURES_DIR / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


def liquid_quotes(name):
    """Cotizaciones limpias y líquidas de una fixture (bloques 2 y 3b)."""
    fixture = load_fixture(name)
    cleaned = [q for q in (clean_row(r) for r in fixture["rows"]) if q is not None]
    return filter_chain(cleaned, fixture["spot"])


def expiry(offset_days, today=TODAY):
    """Vencimiento ISO a `offset_days` días del reloj fijado."""
    return (today + timedelta(days=offset_days)).isoformat()


def make_snapshot(ticker="SPY", fixture="spy", offsets=(10, 45), **changes):
    """Snapshot de prueba: la misma cadena líquida en cada vencimiento."""
    fixture_data = load_fixture(fixture)
    quotes = liquid_quotes(fixture)
    values = dict(
        ticker=ticker,
        loaded_at=LOADED_AT,
        spot=fixture_data["spot"],
        rate=0.04122,
        q=0.0079093,
        q_source="yahoo",
        chains={expiry(o): list(quotes) for o in offsets},
        source="live",
    )
    values.update(changes)
    return MarketSnapshot(**values)


def write_file(path, content):
    """Escribe un archivo de texto a mano (para simular corrupción)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# --- Ruta y nombre del archivo ---


def test_default_cache_dir_is_repo_root_dot_cache_datos():
    repo_root = Path(__file__).resolve().parent.parent
    assert cache.DEFAULT_CACHE_DIR == repo_root / ".cache_datos"


def test_cache_path_uses_the_curated_label(tmp_path):
    assert cache_path("SPX", tmp_path) == tmp_path / "SPX.json"
    assert cache_path("^SPX", tmp_path) == tmp_path / "SPX.json"
    assert cache_path("AAPL", tmp_path) == tmp_path / "AAPL.json"


def test_cache_path_without_dir_points_to_default():
    assert cache_path("SPY") == cache.DEFAULT_CACHE_DIR / "SPY.json"


@pytest.mark.parametrize("bad", ["", "^", "../SPY", "a/b", "a\\b", ".hidden", None, 5])
def test_cache_path_rejects_unsafe_labels(bad, tmp_path):
    with pytest.raises(ValueError):
        cache_path(bad, tmp_path)


def test_spx_snapshot_is_saved_as_spx_json_never_caret(tmp_path):
    snapshot = make_snapshot(ticker="^SPX", fixture="spx")
    written, notice = write_snapshot(snapshot, tmp_path)
    assert written is True
    assert notice is None
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["SPX.json"]
    assert not (tmp_path / "^SPX.json").exists()


# --- Escribir y leer ---


def test_write_then_read_round_trip(tmp_path):
    snapshot = make_snapshot()
    assert write_snapshot(snapshot, tmp_path) == (True, None)
    loaded = read_snapshot("SPY", tmp_path, today=TODAY)
    assert loaded is not None
    assert loaded.source == "cache"
    assert loaded.ticker == "SPY"
    assert loaded.spot == snapshot.spot
    assert loaded.rate == snapshot.rate
    assert loaded.q == snapshot.q
    assert loaded.q_source == "yahoo"
    assert loaded.loaded_at == LOADED_AT
    assert loaded.loaded_at.tzinfo is not None
    assert loaded.chains == snapshot.chains


def test_file_contents_follow_the_schema(tmp_path):
    write_snapshot(make_snapshot(), tmp_path)
    data = json.loads((tmp_path / "SPY.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == SCHEMA_VERSION
    assert datetime.fromisoformat(data["loaded_at"]).tzinfo is not None
    assert data["loaded_at"] == LOADED_AT.isoformat()
    for key in ("ticker", "spot", "rate", "q", "q_source", "chains"):
        assert key in data
    first = next(iter(data["chains"].values()))[0]
    assert set(first) == {"kind", "strike", "bid", "ask", "last", "oi", "volume", "iv_yahoo"}


def test_index_snapshot_keeps_q_none(tmp_path):
    snapshot = make_snapshot(ticker="SPX", fixture="spx", q=None, q_source="indice")
    write_snapshot(snapshot, tmp_path)
    loaded = read_snapshot("SPX", tmp_path, today=TODAY)
    assert loaded.q is None
    assert loaded.q_source == "indice"


def test_read_with_caret_label_finds_spx_json(tmp_path):
    write_snapshot(make_snapshot(ticker="SPX", fixture="spx"), tmp_path)
    assert read_snapshot("^SPX", tmp_path, today=TODAY) is not None


def test_stale_last_quote_survives_round_trip(tmp_path):
    quotes = liquid_quotes("stale_last")
    snapshot = make_snapshot(chains={expiry(30): quotes}, spot=load_fixture("stale_last")["spot"])
    write_snapshot(snapshot, tmp_path)
    loaded = read_snapshot("SPY", tmp_path, today=TODAY)
    assert loaded.chains[expiry(30)] == quotes


def test_naive_loaded_at_is_rejected(tmp_path):
    snapshot = make_snapshot(loaded_at=datetime(2026, 11, 20, 15, 30))
    with pytest.raises(ValueError):
        write_snapshot(snapshot, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_write_creates_missing_cache_dir(tmp_path):
    target = tmp_path / "sub" / "cache"
    assert write_snapshot(make_snapshot(), target) == (True, None)
    assert (target / "SPY.json").exists()


# --- Sin caché ---


def test_missing_file_means_no_cache(tmp_path):
    assert read_snapshot("SPY", tmp_path, today=TODAY) is None


def test_missing_dir_means_no_cache(tmp_path):
    assert read_snapshot("SPY", tmp_path / "nope", today=TODAY) is None


@pytest.mark.parametrize(
    "content",
    [
        "",
        "{not json",
        "[1, 2, 3]",
        "null",
        '{"schema_version": 1}',
        "\x00\x01garbage",
    ],
)
def test_corrupt_json_means_no_cache(tmp_path, content):
    write_file(tmp_path / "SPY.json", content)
    assert read_snapshot("SPY", tmp_path, today=TODAY) is None


def test_other_schema_version_means_no_cache(tmp_path):
    write_snapshot(make_snapshot(), tmp_path)
    path = tmp_path / "SPY.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = SCHEMA_VERSION + 1
    path.write_text(json.dumps(data), encoding="utf-8")
    assert read_snapshot("SPY", tmp_path, today=TODAY) is None


@pytest.mark.parametrize(
    "field, bad",
    [
        ("loaded_at", "ayer"),
        ("loaded_at", "2026-11-20T15:30:00"),  # sin zona horaria
        ("spot", -5),
        ("spot", "100"),
        ("spot", None),
        ("rate", None),
        ("q", "0.01"),
        ("q_source", "inventado"),
        ("chains", []),
        ("ticker", 7),
    ],
)
def test_invalid_field_means_no_cache(tmp_path, field, bad):
    write_snapshot(make_snapshot(), tmp_path)
    path = tmp_path / "SPY.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[field] = bad
    path.write_text(json.dumps(data), encoding="utf-8")
    assert read_snapshot("SPY", tmp_path, today=TODAY) is None


def test_unreadable_bytes_mean_no_cache(tmp_path):
    path = tmp_path / "SPY.json"
    path.write_bytes(b"\xff\xfe\xfa not utf-8")
    assert read_snapshot("SPY", tmp_path, today=TODAY) is None


# --- Filtros reaplicados al leer ---


def test_filters_are_reapplied_when_reading(tmp_path):
    # Se guarda a propósito una cadena sin filtrar (filas de bid_zero):
    # al leer solo quedan las líquidas.
    fixture = load_fixture("bid_zero")
    raw = [q for q in (clean_row(r) for r in fixture["rows"]) if q is not None]
    snapshot = make_snapshot(spot=fixture["spot"], chains={expiry(30): raw})
    write_snapshot(snapshot, tmp_path)
    loaded = read_snapshot("SPY", tmp_path, today=TODAY)
    expected = filter_chain(raw, fixture["spot"])
    assert len(raw) == 10
    assert len(expected) == 2
    assert loaded.chains[expiry(30)] == expected
    assert all(q.bid > 0 for q in loaded.chains[expiry(30)])


def test_broken_rows_in_the_file_are_dropped(tmp_path):
    write_snapshot(make_snapshot(offsets=(30,)), tmp_path)
    path = tmp_path / "SPY.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["chains"][expiry(30)]
    good = len(rows)
    rows.append({"kind": "call", "strike": 690.0, "bid": 5.0, "ask": 4.0, "oi": 500})
    rows.append({"kind": "put", "strike": 690.0})
    rows.append("no soy una fila")
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = read_snapshot("SPY", tmp_path, today=TODAY)
    assert len(loaded.chains[expiry(30)]) == good


def test_rules_parameter_is_used_when_reading(tmp_path):
    write_snapshot(make_snapshot(offsets=(30,)), tmp_path)
    strict = LiquidityRules(min_oi=10**9)
    assert read_snapshot("SPY", tmp_path, today=TODAY, rules=strict) is None
    assert read_snapshot("SPY", tmp_path, today=TODAY, rules=DEFAULT_RULES) is not None


def test_expiry_left_without_liquid_quotes_is_dropped(tmp_path):
    fixture = load_fixture("bid_zero")
    raw = [q for q in (clean_row(r) for r in fixture["rows"]) if q is not None]
    illiquid = [q for q in raw if q.bid == 0]
    snapshot = make_snapshot(
        spot=fixture["spot"], chains={expiry(20): illiquid, expiry(30): raw}
    )
    write_snapshot(snapshot, tmp_path)
    loaded = read_snapshot("SPY", tmp_path, today=TODAY)
    assert list(loaded.chains) == [expiry(30)]


# --- Días recomputados desde el reloj inyectado ---


def test_expiry_window_edges_use_the_injected_today(tmp_path):
    snapshot = make_snapshot(offsets=(6, 7, 120, 121))
    write_snapshot(snapshot, tmp_path)
    loaded = read_snapshot("SPY", tmp_path, today=TODAY)
    assert list(loaded.chains) == [expiry(7), expiry(120)]


def test_days_are_recomputed_from_a_later_today(tmp_path):
    write_snapshot(make_snapshot(offsets=(10, 45)), tmp_path)
    later = TODAY + timedelta(days=5)
    # +10 queda a 5 días (fuera de la ventana), +45 queda a 40 días.
    loaded = read_snapshot("SPY", tmp_path, today=later)
    assert list(loaded.chains) == [expiry(45)]


def test_two_clocks_with_same_relative_dates_agree(tmp_path):
    other_today = date(2027, 3, 1)
    for today, folder in ((TODAY, "a"), (other_today, "b")):
        snapshot = make_snapshot(
            chains={expiry(o, today): liquid_quotes("spy") for o in (6, 30, 121)}
        )
        write_snapshot(snapshot, tmp_path / folder)
    first = read_snapshot("SPY", tmp_path / "a", today=TODAY)
    second = read_snapshot("SPY", tmp_path / "b", today=other_today)
    assert list(first.chains) == [expiry(30, TODAY)]
    assert list(second.chains) == [expiry(30, other_today)]


def test_all_expiries_out_of_window_means_no_cache(tmp_path):
    write_snapshot(make_snapshot(offsets=(10,)), tmp_path)
    assert read_snapshot("SPY", tmp_path, today=TODAY + timedelta(days=30)) is None


def test_today_may_be_an_aware_datetime_in_new_york(tmp_path):
    write_snapshot(make_snapshot(offsets=(7,)), tmp_path)
    # 2026-11-21 02:00 UTC es todavía el 20 de noviembre en Nueva York:
    # el vencimiento a +7 sigue dentro de la ventana.
    utc_moment = datetime(2026, 11, 21, 2, 0, tzinfo=timezone.utc)
    loaded = read_snapshot("SPY", tmp_path, today=utc_moment)
    assert list(loaded.chains) == [expiry(7)]


def test_market_today_uses_new_york_date():
    assert market_today(datetime(2026, 11, 21, 2, 0, tzinfo=timezone.utc)) == TODAY
    assert market_today(datetime(2026, 11, 21, 6, 0, tzinfo=timezone.utc)) == date(2026, 11, 21)
    assert market_today(TODAY) == TODAY


def test_market_today_rejects_naive_datetime():
    with pytest.raises(ValueError):
        market_today(datetime(2026, 11, 21, 2, 0))


def test_bad_expiry_key_is_dropped(tmp_path):
    write_snapshot(make_snapshot(offsets=(30,)), tmp_path)
    path = tmp_path / "SPY.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["chains"]["no-es-fecha"] = data["chains"][expiry(30)]
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = read_snapshot("SPY", tmp_path, today=TODAY)
    assert list(loaded.chains) == [expiry(30)]


# --- Escritura atómica ---


def test_failed_replace_keeps_old_file_and_leaves_no_temp(tmp_path, monkeypatch):
    write_snapshot(make_snapshot(offsets=(10,)), tmp_path)
    before = (tmp_path / "SPY.json").read_bytes()

    def broken_replace(src, dst):
        raise OSError("disco lleno (simulado)")

    monkeypatch.setattr(cache.os, "replace", broken_replace)
    written, notice = write_snapshot(make_snapshot(offsets=(10, 45, 90)), tmp_path)
    assert written is False
    assert isinstance(notice, str) and notice
    assert (tmp_path / "SPY.json").read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["SPY.json"]


def test_failed_temp_write_leaves_nothing(tmp_path, monkeypatch):
    def broken_dump(*args, **kwargs):
        raise OSError("fallo al escribir (simulado)")

    monkeypatch.setattr(cache.json, "dump", broken_dump)
    written, notice = write_snapshot(make_snapshot(), tmp_path)
    assert written is False
    assert notice
    assert list(tmp_path.iterdir()) == []


def test_write_uses_os_replace(tmp_path, monkeypatch):
    calls = []
    real_replace = os.replace

    def spy_replace(src, dst):
        calls.append((Path(src).parent, Path(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(cache.os, "replace", spy_replace)
    write_snapshot(make_snapshot(), tmp_path)
    # El temporal vive en la misma carpeta que el destino (mismo disco).
    assert calls == [(tmp_path, tmp_path / "SPY.json")]


# --- Regla parcial-vs-rico ---


def test_richness_counts_expiries_and_quotes():
    n_quotes = len(liquid_quotes("spy"))
    snapshot = make_snapshot(offsets=(10, 45, 90))
    assert richness(snapshot) == (3, 3 * n_quotes)
    empty = make_snapshot(chains={})
    assert richness(empty) == (0, 0)


def test_is_richer_or_equal_rule():
    base = make_snapshot(offsets=(10, 45))
    assert is_richer_or_equal(base, base)
    assert is_richer_or_equal(make_snapshot(offsets=(10, 45, 90)), base)
    assert not is_richer_or_equal(make_snapshot(offsets=(10,)), base)
    # Mismos vencimientos pero menos cotizaciones: no es más rico.
    fewer = {k: v[:-1] for k, v in base.chains.items()}
    assert not is_richer_or_equal(make_snapshot(chains=fewer), base)
    # Más vencimientos pero menos cotizaciones en total: tampoco.
    thin = {expiry(o): liquid_quotes("spy")[:1] for o in (10, 45, 90)}
    assert not is_richer_or_equal(make_snapshot(chains=thin), base)


def test_partial_snapshot_does_not_overwrite_richer_cache(tmp_path):
    rich = make_snapshot(offsets=(10, 45, 90))
    assert write_snapshot(rich, tmp_path) == (True, None)
    before = (tmp_path / "SPY.json").read_bytes()

    partial = make_snapshot(
        offsets=(10,), loaded_at=LOADED_AT + timedelta(hours=1), complete=False
    )
    written, notice = write_snapshot(partial, tmp_path, today=TODAY)
    assert written is False
    assert isinstance(notice, str)
    assert "caché" in notice
    assert (tmp_path / "SPY.json").read_bytes() == before
    loaded = read_snapshot("SPY", tmp_path, today=TODAY)
    assert len(loaded.chains) == 3
    assert loaded.loaded_at == LOADED_AT


def test_fewer_quotes_same_expiries_does_not_overwrite(tmp_path):
    base = make_snapshot(offsets=(10, 45))
    write_snapshot(base, tmp_path)
    fewer = {k: v[:-1] for k, v in base.chains.items()}
    written, notice = write_snapshot(
        make_snapshot(chains=fewer, complete=False), tmp_path, today=TODAY
    )
    assert written is False
    assert notice


def test_equal_snapshot_replaces_the_cache(tmp_path):
    write_snapshot(make_snapshot(offsets=(10, 45)), tmp_path)
    newer = make_snapshot(offsets=(10, 45), loaded_at=LOADED_AT + timedelta(hours=2), spot=700.0)
    assert write_snapshot(newer, tmp_path) == (True, None)
    loaded = read_snapshot("SPY", tmp_path, today=TODAY)
    assert loaded.spot == 700.0
    assert loaded.loaded_at == LOADED_AT + timedelta(hours=2)


def test_richer_snapshot_replaces_the_cache(tmp_path):
    write_snapshot(make_snapshot(offsets=(10,)), tmp_path)
    assert write_snapshot(make_snapshot(offsets=(10, 45, 90)), tmp_path) == (True, None)
    assert len(read_snapshot("SPY", tmp_path, today=TODAY).chains) == 3


def test_complete_load_after_an_expiry_rolls_out_is_written(tmp_path):
    # Regresión F1: ayer se guardaron 3 vencimientos; hoy el primero ya
    # está fuera de la ventana y la carga completa trae solo 2. Debe
    # guardarse (antes se rechazaba y la caché se quedaba vieja).
    yesterday = TODAY - timedelta(days=1)
    saved = make_snapshot(
        chains={expiry(o, yesterday): liquid_quotes("spy") for o in (7, 45, 90)},
        loaded_at=LOADED_AT - timedelta(days=1),
    )
    assert write_snapshot(saved, tmp_path) == (True, None)
    fresh = make_snapshot(
        chains={expiry(o, yesterday): liquid_quotes("spy") for o in (45, 90)},
        spot=701.0,
    )
    assert fresh.complete is True
    assert write_snapshot(fresh, tmp_path, today=TODAY) == (True, None)
    loaded = read_snapshot("SPY", tmp_path, today=TODAY)
    assert loaded.spot == 701.0
    assert loaded.loaded_at == LOADED_AT


def test_complete_poorer_load_still_replaces_the_cache(tmp_path):
    # Una carga completa siempre manda, aunque traiga menos datos.
    write_snapshot(make_snapshot(offsets=(10, 45, 90)), tmp_path)
    assert write_snapshot(make_snapshot(offsets=(10,)), tmp_path, today=TODAY) == (True, None)
    assert len(read_snapshot("SPY", tmp_path, today=TODAY).chains) == 1


def test_partial_richer_snapshot_is_written(tmp_path):
    write_snapshot(make_snapshot(offsets=(10,)), tmp_path)
    partial = make_snapshot(offsets=(10, 45), complete=False)
    assert write_snapshot(partial, tmp_path, today=TODAY) == (True, None)
    loaded = read_snapshot("SPY", tmp_path, today=TODAY)
    assert len(loaded.chains) == 2
    assert loaded.complete is False


def test_partial_comparison_uses_todays_window(tmp_path):
    # Guardado ayer con 3 vencimientos, uno de ellos (a 7 días de ayer)
    # ya fuera de la ventana hoy. La carga parcial de hoy trae 2: hoy
    # valen lo mismo, así que se guarda.
    yesterday = TODAY - timedelta(days=1)
    saved = make_snapshot(
        chains={expiry(o, yesterday): liquid_quotes("spy") for o in (7, 45, 90)},
        loaded_at=LOADED_AT - timedelta(days=1),
    )
    write_snapshot(saved, tmp_path)
    partial = make_snapshot(
        chains={expiry(o, yesterday): liquid_quotes("spy") for o in (45, 90)},
        complete=False,
    )
    assert write_snapshot(partial, tmp_path, today=TODAY) == (True, None)
    # Comparado con el reloj de ayer, la guardada seguía siendo más rica.
    write_snapshot(saved, tmp_path)
    written, notice = write_snapshot(partial, tmp_path, today=yesterday)
    assert written is False
    assert "3 vencimientos" in notice


def test_partial_without_saved_cache_is_written(tmp_path):
    partial = make_snapshot(offsets=(10,), complete=False)
    assert write_snapshot(partial, tmp_path) == (True, None)


def test_complete_flag_is_saved_in_the_file(tmp_path):
    write_snapshot(make_snapshot(complete=False), tmp_path)
    data = json.loads((tmp_path / "SPY.json").read_text(encoding="utf-8"))
    assert data["complete"] is False
    assert read_snapshot("SPY", tmp_path, today=TODAY).complete is False


def test_old_file_without_complete_field_reads_as_complete(tmp_path):
    write_snapshot(make_snapshot(), tmp_path)
    path = tmp_path / "SPY.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["complete"]
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = read_snapshot("SPY", tmp_path, today=TODAY)
    assert loaded is not None
    assert loaded.complete is True


def test_non_bool_complete_field_means_no_cache(tmp_path):
    write_snapshot(make_snapshot(), tmp_path)
    path = tmp_path / "SPY.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["complete"] = "yes"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert read_snapshot("SPY", tmp_path, today=TODAY) is None


def test_corrupt_old_cache_is_replaced(tmp_path):
    write_file(tmp_path / "SPY.json", "{roto")
    assert write_snapshot(make_snapshot(offsets=(10,)), tmp_path) == (True, None)
    assert read_snapshot("SPY", tmp_path, today=TODAY) is not None


def test_old_cache_with_other_schema_is_replaced(tmp_path):
    write_file(tmp_path / "SPY.json", json.dumps({"schema_version": 999, "chains": {}}))
    assert write_snapshot(make_snapshot(offsets=(10,)), tmp_path) == (True, None)


def test_rich_cache_of_other_ticker_does_not_block(tmp_path):
    write_snapshot(make_snapshot(ticker="QQQ", offsets=(10, 45, 90)), tmp_path)
    assert write_snapshot(make_snapshot(ticker="SPY", offsets=(10,)), tmp_path) == (True, None)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["QQQ.json", "SPY.json"]


# --- Paquete ---


def test_package_reexports_cache_functions():
    for name in ("read_snapshot", "write_snapshot", "richness", "is_richer_or_equal"):
        assert getattr(datos, name) is getattr(cache, name)


def test_cache_does_not_import_service():
    # La caché va antes que el servicio (C-V6): no puede depender de él.
    source = Path(cache.__file__).read_text(encoding="utf-8")
    for forbidden in ("import service", "datos.service", "from datos import service"):
        assert forbidden not in source


def test_quotes_are_option_quote_instances(tmp_path):
    write_snapshot(make_snapshot(), tmp_path)
    loaded = read_snapshot("SPY", tmp_path, today=TODAY)
    for quotes in loaded.chains.values():
        assert all(isinstance(q, OptionQuote) for q in quotes)
    assert replace(loaded, source="live").source == "live"
