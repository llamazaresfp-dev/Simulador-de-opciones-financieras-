"""Prueba EN VIVO contra Yahoo Finance (opcional, necesita Internet).

Omitida por defecto. Para ejecutarla a propósito:
    LIVE_DATA=1 .venv/bin/pytest tests/test_datos_live.py -q -s

Comprueba que Yahoo sigue devolviendo los campos que usa el paquete y
cuenta cuántas solicitudes HTTP hace una carga de SPY. Escribe la caché
y la caché tz de yfinance en `tmp_path`, nunca en `.cache_datos/`.
"""

import math
import os

import pytest

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
