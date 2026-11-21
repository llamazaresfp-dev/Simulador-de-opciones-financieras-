"""Prueba EN VIVO contra Yahoo Finance (opcional, necesita Internet).

Omitida por defecto. Para ejecutarla a propósito:
    LIVE_DATA=1 .venv/bin/pytest tests/test_datos_live.py -q -s

Comprueba que Yahoo sigue devolviendo los campos que usa el paquete y
cuenta cuántas solicitudes HTTP hace una carga de SPY. Escribe la caché
y la caché tz de yfinance en `tmp_path`, nunca en `.cache_datos/`.

Etapa C2: `test_historial_en_vivo` comprueba el histórico diario de SPY,
del índice (^GSPC o ^SPX) y de la tasa ^IRX.
"""

import math
import os

import pytest

from datos.history_service import load_history
from datos.service import load_with_notices
from datos.yahoo import YahooProvider, build_session


@pytest.mark.skipif(
    os.environ.get("LIVE_DATA") != "1",
    reason="prueba en vivo: ejecútala con LIVE_DATA=1 (necesita Internet)",
)
def test_carga_spy_en_vivo(tmp_path):
    session = build_session(timeout=10)
    requests_made = []
    original_request = session.request

    def counting_request(method, url, *args, **kwargs):
        requests_made.append(url)
        return original_request(method, url, *args, **kwargs)

    session.request = counting_request

    provider = YahooProvider(tz_cache_dir=tmp_path / "tz", session=session)
    snapshot, notices = load_with_notices("SPY", provider, cache_dir=tmp_path / "cache")

    print(f"\nSolicitudes HTTP en la carga de SPY: {len(requests_made)}")
    print(f"Spot {snapshot.spot}, r {snapshot.rate}, q {snapshot.q} ({snapshot.q_source})")
    print(f"Vencimientos con opciones líquidas: {len(snapshot.chains)}; completa: {snapshot.complete}")
    print(f"Avisos: {notices}")

    assert snapshot.ticker == "SPY"
    assert snapshot.spot > 0
    assert 0 < snapshot.rate < 0.2
    assert len(snapshot.chains) >= 1
    for quotes in snapshot.chains.values():
        for quote in quotes:
            assert quote.bid > 0
            assert quote.ask >= quote.bid
            assert quote.oi >= 0
            assert math.isfinite(quote.mid)
    assert (tmp_path / "cache" / "SPY.json").is_file()


def _counting_session():
    """Sesión con timeout que anota cada URL pedida."""
    session = build_session(timeout=10)
    requests_made = []
    original_request = session.request

    def counting_request(method, url, *args, **kwargs):
        requests_made.append(url)
        return original_request(method, url, *args, **kwargs)

    session.request = counting_request
    return session, requests_made


@pytest.mark.skipif(
    os.environ.get("LIVE_DATA") != "1",
    reason="prueba en vivo: ejecútala con LIVE_DATA=1 (necesita Internet)",
)
def test_historial_en_vivo(tmp_path):
    session, requests_made = _counting_session()
    provider = YahooProvider(tz_cache_dir=tmp_path / "tz", session=session)

    for label in ("SPY", "SPX"):
        before = len(requests_made)
        loaded, notices = load_history(provider, label, 2, cache_dir=tmp_path / "cache")
        history = loaded.history
        print(f"\n{label}: símbolo {loaded.symbol}, {len(history.dates)} filas "
              f"({history.dates[0]} a {history.dates[-1]}), {len(history.dividends)} dividendos, "
              f"solicitudes {len(requests_made) - before}")
        print(f"  tasa: {None if loaded.rates is None else len(loaded.rates.dates)} filas; avisos {notices}")

        assert loaded.source == "live"
        assert history.ticker == label
        assert len(history.dates) > 400
        assert all(p > 0 and math.isfinite(p) for p in history.close + history.adj_close)
        assert all(a <= c * 1.0001 for a, c in zip(history.adj_close, history.close))
        assert loaded.rates is not None
        assert all(0 <= r < 0.2 for r in loaded.rates.close)
        assert (tmp_path / "cache" / "history" / f"{label}.json").is_file()

    assert (tmp_path / "cache" / "history" / "IRX.json").is_file()
