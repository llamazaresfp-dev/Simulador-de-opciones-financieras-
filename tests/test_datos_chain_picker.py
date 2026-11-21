"""Selector de patas reales del Constructor (Etapa C1, bloque 6).

Pruebas con AppTest: la app se ejecuta sin navegador, con el proveedor
FALSO (sin red), la caché en tmp_path y el reloj fijo.

Qué se comprueba:
- AC-C1-6: el selector solo ofrece opciones líquidas (las de
  `snapshot.chains` del vencimiento elegido); con la fixture `bid_zero`
  las filas sin comprador/vendedor nunca aparecen.
- AC-C1-7: la prima de la pata es el mid (bid+ask)/2, nunca el último
  precio (fixture `stale_last`: last muy lejos del mid).
- AC-C1-8: la IV que muestra la app es la del motor calculada con el mid
  (ida y vuelta: precio del motor con esa IV ≈ mid); la IV de Yahoo solo
  aparece como "referencia" y no cambia nada.
"""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from streamlit.testing.v1 import AppTest

from datos import FakeProvider
from opciones import Leg, Market, implied_vol
from opciones.pricing import option_price

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")

# Reloj fijo: viernes 20/11/2026 10:30 en Nueva York.
FIXED_NOW = datetime(2026, 11, 20, 10, 30, tzinfo=ZoneInfo("America/New_York"))
PICKER_LABEL = "Añadir pata desde la cadena real"


def loaded_app(tmp_path, underlying: str, ticker: str, fixture=None) -> AppTest:
    """App con datos cargados del proveedor falso (opcionalmente otra fixture)."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["data_provider"] = FakeProvider(today=FIXED_NOW, fixture=fixture)
    at.session_state["cache_dir"] = str(tmp_path)
    at.session_state["clock"] = lambda: FIXED_NOW
    at.run()
    if at.session_state["underlying"] != underlying:
        at.selectbox(key="underlying").set_value(underlying).run()
    at.selectbox(key="ticker_choice").set_value(ticker).run()
    at.button(key="load_data").click().run()
    assert not at.exception
    return at


def add_market_leg(at: AppTest, kind: str, strike: float, side: int = 1) -> dict:
    """Elige tipo, dirección y strike en el selector, pulsa "Añadir pata"
    y devuelve la pata nueva (la última de la lista)."""
    at.selectbox(key="pick_kind").set_value(kind).run()
    at.selectbox(key="pick_side").set_value(side).run()
    at.selectbox(key="pick_strike").set_value(strike).run()
    at.button(key="add_market_leg").click().run()
    assert not at.exception
    return at.session_state["legs"][-1]


def selected_quotes(at: AppTest) -> list:
    """Cotizaciones del vencimiento elegido, tal como las guarda el snapshot."""
    state = at.session_state
    return state["snapshot"].chains[state["expiry_choice"]]


def all_captions(at: AppTest) -> list[str]:
    return [caption.value for caption in at.caption]


# --- AC-C1-6: solo opciones líquidas -------------------------------------


def test_picker_appears_after_loading(tmp_path):
    at = loaded_app(tmp_path, "ETF", "SPY")
    assert PICKER_LABEL in [expander.label for expander in at.expander]


def test_strike_options_come_only_from_selected_chain(tmp_path):
    at = loaded_app(tmp_path, "ETF", "SPY")
    quotes = selected_quotes(at)
    for kind in ("call", "put"):
        at.selectbox(key="pick_kind").set_value(kind).run()
        expected = sorted(q.strike for q in quotes if q.kind == kind)
        box = at.selectbox(key="pick_strike")
        # Si el strike elegido también existe en el otro tipo, se conserva.
        assert box.value in expected
        assert len(box.options) == len(expected)
        assert [o.split(" · ")[0] for o in box.options] == [f"{s:.2f}" for s in expected]
        # Cada etiqueta lleva bid, ask, mid e IV de Yahoo.
        assert all("bid" in o and "ask" in o and "mid" in o and "IV Yahoo" in o for o in box.options)


def test_bid_zero_rows_never_offered(tmp_path):
    # Fixture `bid_zero` (spot 100): solo la call 100 (2,00/2,10) y la put
    # 100 (1,80/1,90) tienen comprador y vendedor; el resto tiene bid = 0
    # o ask = 0 y NO puede aparecer.
    at = loaded_app(tmp_path, "ETF", "SPY", fixture="bid_zero")
    at.selectbox(key="pick_kind").set_value("call").run()
    calls = at.selectbox(key="pick_strike").options
    assert calls == ["100.00 · bid 2.00 / ask 2.10 / mid 2.05 · IV Yahoo —"]
    at.selectbox(key="pick_kind").set_value("put").run()
    puts = at.selectbox(key="pick_strike").options
    assert puts == ["100.00 · bid 1.80 / ask 1.90 / mid 1.85 · IV Yahoo —"]
    for expiry, chain in at.session_state["snapshot"].chains.items():
        assert all(q.bid > 0 and q.ask > 0 for q in chain), expiry


# --- AC-C1-7: prima = mid, nunca el último precio ---------------------------


def test_added_leg_uses_mid_and_stores_quote(tmp_path):
    at = loaded_app(tmp_path, "ETF", "SPY")
    quote = next(q for q in selected_quotes(at) if q.kind == "call" and q.strike == 700.0)
    leg = add_market_leg(at, "call", 700.0, side=-1)
    assert leg["price"] == pytest.approx((quote.bid + quote.ask) / 2)
    assert leg["premium_manual"] is True
    assert leg["premium_source"] == "mercado"
    assert (leg["kind"], leg["side"], leg["strike"]) == ("call", -1, 700.0)
    assert (leg["bid"], leg["ask"], leg["iv_yahoo"]) == (quote.bid, quote.ask, quote.iv_yahoo)
    assert leg["expiry"] == at.session_state["expiry_choice"]


def test_stale_last_price_is_ignored(tmp_path):
    # Fixture `stale_last`: put 7000 con bid 322 / ask 335 y last 176.
    at = loaded_app(tmp_path, "Índice", "SPX", fixture="stale_last")
    leg = add_market_leg(at, "put", 7000.0)
    assert leg["price"] == pytest.approx(328.5)  # (322 + 335) / 2
    assert leg["price"] != pytest.approx(176.0)
    assert at.number_input(key=f"leg_{leg['id']}_price").value == pytest.approx(328.5)
    assert "Pata 2: precio mercado (mid de bid 322.00 / ask 335.00)." in all_captions(at)


def test_market_leg_premium_survives_global_changes(tmp_path):
    at = loaded_app(tmp_path, "ETF", "SPY")
    leg = add_market_leg(at, "put", 690.0)
    mid = leg["price"]
    at.number_input(key="spot").set_value(650.0).run()
    at.number_input(key="vol_pct").set_value(35.0).run()
    at.radio(key="pricing_model_input").set_value("black_scholes").run()
    assert not at.exception
    assert at.session_state["legs"][-1]["price"] == pytest.approx(mid)
    assert at.session_state["legs"][-1]["premium_source"] == "mercado"


# --- AC-C1-8: IV del motor con el mid; IV de Yahoo solo de referencia -------


def test_engine_iv_round_trips_mid_and_yahoo_iv_is_reference(tmp_path):
    # Fixture `stale_last` (índice -> Black-Scholes): call 6700, bid 150 /
    # ask 156 -> mid 153; spot 6680, 10 días, r 4,12 %, q 0 (q del índice
    # no se toca), IV de Yahoo 0,17.
    at = loaded_app(tmp_path, "Índice", "SPX", fixture="stale_last")
    leg = add_market_leg(at, "call", 6700.0)
    market = Market(underlying="Índice", spot=6680.0, vol=0.20, days=10, rate=0.0412, q=0.0)
    result = implied_vol(Leg("call", 1, 1.0, 6700.0, 153.0), market)
    assert result.vol is not None
    # Ida y vuelta: precio del motor con la IV calculada ≈ mid.
    engine_price = option_price("call", Market(
        underlying="Índice", spot=6680.0, vol=result.vol, days=10, rate=0.0412, q=0.0,
    ), 6700.0)
    assert engine_price == pytest.approx(153.0, abs=1e-6)

    texts = all_captions(at)
    shown = f"Pata 2 (Call, strike 6700.00): volatilidad implícita {round(result.vol * 100, 2):.2f} %"
    assert shown in texts
    assert "IV Yahoo (referencia): 17.00 %" in texts
    # La IV del motor no es la de Yahoo (no se usa en ningún cálculo).
    assert round(result.vol * 100, 2) != 17.00
    assert leg["price"] == pytest.approx(153.0)


def test_yahoo_iv_does_not_change_engine_iv(tmp_path):
    # Misma pata con y sin IV de Yahoo: la IV del motor mostrada es la misma.
    at = loaded_app(tmp_path, "Índice", "SPX", fixture="stale_last")
    add_market_leg(at, "call", 6700.0)
    with_ref = [t for t in all_captions(at) if "volatilidad implícita" in t]
    at.session_state["legs"][-1]["iv_yahoo"] = None
    at.run()
    without_ref = [t for t in all_captions(at) if "volatilidad implícita" in t]
    assert with_ref == without_ref
    assert not any(t.startswith("IV Yahoo (referencia)") for t in all_captions(at))
