"""Tests de los filtros de liquidez y la limpieza de filas (Etapa C1, bloque 2).

Casos en el borde de cada umbral, incluidos los bordes EXACTOS (C-V3),
donde sin la tolerancia EPS un error de redondeo decimal descartaría una
opción que cumple la regla (p. ej. 0.40 - 0.30 = 0.10000000000000003).
"""

import dataclasses
import inspect
import io
import math
import tokenize

import pytest

import datos
from datos import filters
from datos.filters import (
    DEFAULT_RULES,
    EPS,
    LiquidityRules,
    clean_row,
    dedupe,
    filter_chain,
    is_expiry_in_window,
)
from datos.types import OptionQuote

SPOT = 100.0


def make_row(**changes):
    """Fila cruda de ejemplo (líquida); `changes` sobrescribe o añade claves."""
    row = dict(
        kind="call",
        strike=100.0,
        bid=2.00,
        ask=2.10,
        last=2.05,
        oi=500,
        volume=30,
        iv_yahoo=0.22,
    )
    row.update(changes)
    return row


def make_quote(**changes):
    """Cotización ya limpia (líquida por defecto)."""
    quote = clean_row(make_row(**changes))
    assert quote is not None
    return quote


def survives(quote, spot=SPOT, rules=DEFAULT_RULES):
    """True si la cotización pasa los filtros de liquidez."""
    return filter_chain([quote], spot, rules) == [quote]


# --- LiquidityRules: valores del SPEC en un único lugar ---


def test_default_rules_have_spec_values():
    rules = DEFAULT_RULES
    assert rules.min_oi == 100
    assert rules.max_rel_spread == pytest.approx(0.10)
    assert rules.max_abs_spread == pytest.approx(0.10)
    assert rules.abs_spread_mid_below == pytest.approx(1.0)
    assert rules.max_strike_distance == pytest.approx(0.20)
    assert rules.min_days == 7
    assert rules.max_days == 120
    assert rules.eps == EPS == 1e-9


def test_liquidity_rules_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT_RULES.min_oi = 5


def test_default_rules_equal_a_fresh_instance():
    assert DEFAULT_RULES == LiquidityRules()


def test_no_threshold_literals_outside_liquidity_rules():
    # Los umbrales del SPEC solo pueden aparecer en la definición de LiquidityRules.
    # Se miran solo los números del CÓDIGO (no comentarios ni docstrings):
    # fuera de la clase y de la línea `EPS = 1e-9` solo puede aparecer el 0.
    source = inspect.getsource(filters)
    rules_source = inspect.getsource(LiquidityRules)
    rest = source.replace(rules_source, "").replace("EPS = 1e-9", "")
    tokens = tokenize.generate_tokens(io.StringIO(rest).readline)
    numbers_in_code = {tok.string for tok in tokens if tok.type == tokenize.NUMBER}
    assert numbers_in_code <= {"0"}, f"umbrales fuera de LiquidityRules: {numbers_in_code}"


# --- clean_row: calidad de la fila ---


def test_clean_row_builds_option_quote():
    quote = clean_row(make_row())
    assert quote == OptionQuote(
        kind="call",
        strike=100.0,
        bid=2.00,
        ask=2.10,
        last=2.05,
        oi=500,
        volume=30,
        iv_yahoo=0.22,
    )
    assert isinstance(quote.oi, int)
    assert isinstance(quote.volume, int)


def test_clean_row_normalizes_kind():
    assert clean_row(make_row(kind=" PUT ")).kind == "put"


@pytest.mark.parametrize("kind", ["future", "", None, 3])
def test_clean_row_rejects_unknown_kind(kind):
    assert clean_row(make_row(kind=kind)) is None


@pytest.mark.parametrize("field", ["kind", "strike", "bid", "ask", "oi"])
def test_clean_row_rejects_missing_required_field(field):
    row = make_row()
    del row[field]
    assert clean_row(row) is None


@pytest.mark.parametrize("field", ["strike", "bid", "ask", "oi"])
@pytest.mark.parametrize("bad", [None, math.nan, math.inf, -1.0, "abc", True])
def test_clean_row_rejects_bad_numbers(field, bad):
    assert clean_row(make_row(**{field: bad})) is None


def test_clean_row_rejects_zero_strike():
    assert clean_row(make_row(strike=0.0)) is None


def test_clean_row_rejects_bid_above_ask():
    assert clean_row(make_row(bid=2.20, ask=2.10)) is None


def test_clean_row_keeps_zero_bid_for_the_liquidity_filter():
    # bid = 0 no es un dato roto: lo descarta la liquidez, no la limpieza.
    quote = clean_row(make_row(bid=0.0))
    assert quote is not None
    assert quote.bid == 0.0


@pytest.mark.parametrize("bad", [None, math.nan, -1.0, "x"])
def test_clean_row_optional_fields_become_safe_defaults(bad):
    quote = clean_row(make_row(last=bad, volume=bad, iv_yahoo=bad))
    assert quote is not None
    assert quote.last is None
    assert quote.volume == 0
    assert quote.iv_yahoo is None


def test_clean_row_optional_fields_may_be_absent():
    row = make_row()
    for field in ("last", "volume", "iv_yahoo"):
        del row[field]
    quote = clean_row(row)
    assert quote is not None
    assert (quote.last, quote.volume, quote.iv_yahoo) == (None, 0, None)


def test_clean_row_rejects_non_integer_open_interest():
    assert clean_row(make_row(oi=100.5)) is None


def test_clean_row_accepts_integer_valued_float_open_interest():
    quote = clean_row(make_row(oi=100.0))
    assert quote.oi == 100
    assert isinstance(quote.oi, int)


def test_clean_row_never_raises_on_garbage():
    assert clean_row({}) is None
    assert clean_row(None) is None
    assert clean_row("not a row") is None


def test_clean_row_output_has_no_nan():
    quote = clean_row(make_row(last=math.nan, iv_yahoo=math.nan, volume=math.nan))
    for value in dataclasses.astuple(quote):
        assert not (isinstance(value, float) and math.isnan(value))


# --- filter_chain: liquidez ---


@pytest.mark.parametrize("bid, ask", [(0.0, 2.10), (0.0, 0.0)])
def test_zero_bid_or_ask_is_filtered(bid, ask):
    assert not survives(make_quote(bid=bid, ask=ask))


def test_zero_ask_with_positive_bid_cannot_exist_after_cleaning():
    # ask = 0 con bid > 0 es bid > ask: lo descarta la limpieza.
    assert clean_row(make_row(bid=0.5, ask=0.0)) is None


@pytest.mark.parametrize("oi, expected", [(99, False), (100, True), (101, True)])
def test_open_interest_threshold(oi, expected):
    assert survives(make_quote(oi=oi)) is expected


@pytest.mark.parametrize(
    "bid, ask, expected",
    [
        (9.50, 10.50, True),  # spread 1,00 / mid 10,00 = exactamente 10 %
        (9.4995, 10.5005, False),  # 1,001 / 10,00 = 10,01 %
        (19.00, 21.00, True),  # 2,00 / 20,00 = exactamente 10 %
        (10.00, 10.50, True),  # ~4,9 %
    ],
)
def test_relative_spread_threshold(bid, ask, expected):
    assert survives(make_quote(bid=bid, ask=ask)) is expected


@pytest.mark.parametrize(
    "bid, ask, expected",
    [
        (0.50, 0.60, True),  # 0,10 exacto (binario-exacto en la resta)
        (0.30, 0.40, True),  # 0,10 exacto: sin EPS falla (0.10000000000000003)
        (0.50, 0.61, False),  # 0,11
        (0.30, 0.41, False),  # 0,11
    ],
)
def test_absolute_spread_threshold_when_mid_below_one(bid, ask, expected):
    assert survives(make_quote(bid=bid, ask=ask)) is expected


def test_bid_030_ask_040_really_needs_the_tolerance():
    # Demuestra por qué existe EPS: la resta decimal no da 0.10 exacto.
    assert not (0.40 - 0.30 <= 0.10)
    assert 0.40 - 0.30 <= 0.10 + EPS


def test_absolute_spread_rule_does_not_apply_when_mid_is_one_or_more():
    # mid = 1,05, spread 0,10 -> 9,5 % pasa por la regla relativa;
    # mid = 1,00, spread 0,11 -> 11 % y la regla absoluta ya no aplica.
    assert survives(make_quote(bid=1.00, ask=1.10))
    assert not survives(make_quote(bid=0.945, ask=1.055))


@pytest.mark.parametrize(
    "strike, expected",
    [
        (80.0, True),  # exactamente -20 %
        (120.0, True),  # exactamente +20 %
        (79.99, False),
        (120.01, False),
        (100.0, True),
    ],
)
def test_strike_window_around_spot(strike, expected):
    assert survives(make_quote(strike=strike)) is expected


def test_strike_window_exact_edges_with_non_round_spot():
    # Spot no redondo: los bordes calculados acarrean error de redondeo.
    spot = 437.3
    low = spot * 0.8
    high = spot * 1.2
    assert survives(make_quote(strike=low), spot=spot)
    assert survives(make_quote(strike=high), spot=spot)
    assert not survives(make_quote(strike=low - 0.01), spot=spot)
    assert not survives(make_quote(strike=high + 0.01), spot=spot)


@pytest.mark.parametrize("spot", [0.0, -5.0, math.nan, None])
def test_invalid_spot_filters_everything_without_raising(spot):
    assert filter_chain([make_quote()], spot, DEFAULT_RULES) == []


def test_filter_chain_keeps_order_and_uses_default_rules():
    quotes = [
        make_quote(strike=95.0),
        make_quote(strike=105.0, oi=10),  # fuera por OI
        make_quote(kind="put", strike=90.0),
    ]
    assert filter_chain(quotes, SPOT) == [quotes[0], quotes[2]]


def test_filter_chain_empty_input():
    assert filter_chain([], SPOT, DEFAULT_RULES) == []


# --- Duplicados (kind, strike) ---


def test_dedupe_keeps_first_per_kind_and_strike():
    first = make_quote(strike=100.0, bid=2.00)
    second = make_quote(strike=100.0, bid=2.05)
    put = make_quote(kind="put", strike=100.0)
    assert dedupe([first, second, put]) == [first, put]


def test_filter_chain_removes_duplicates():
    first = make_quote(strike=100.0, bid=2.00)
    second = make_quote(strike=100.0, bid=2.05)
    assert filter_chain([first, second], SPOT, DEFAULT_RULES) == [first]


def test_filter_chain_keeps_liquid_duplicate_when_first_is_illiquid():
    illiquid = make_quote(strike=100.0, oi=5)
    liquid = make_quote(strike=100.0, oi=500)
    assert filter_chain([illiquid, liquid], SPOT, DEFAULT_RULES) == [liquid]


# --- Ventana de vencimientos (días naturales) ---


@pytest.mark.parametrize(
    "days, expected",
    [(6, False), (7, True), (120, True), (121, False), (0, False), (-3, False)],
)
def test_expiry_window(days, expected):
    assert is_expiry_in_window(days, DEFAULT_RULES) is expected
    assert is_expiry_in_window(days) is expected


# --- Umbrales en un solo lugar: cambiar LiquidityRules cambia el resultado ---


def test_changing_rules_changes_results():
    quote = make_quote(oi=50, strike=130.0, bid=1.00, ask=1.30)
    assert not survives(quote)
    loose = LiquidityRules(min_oi=10, max_rel_spread=0.30, max_strike_distance=0.35)
    assert survives(quote, rules=loose)
    assert is_expiry_in_window(150, LiquidityRules(max_days=200))
    assert not is_expiry_in_window(7, LiquidityRules(min_days=8))


def test_tighter_absolute_spread_rule():
    quote = make_quote(bid=0.30, ask=0.40)
    assert not survives(quote, rules=LiquidityRules(max_abs_spread=0.05))


# --- Fila sucia completa (calidad + liquidez juntas) ---


def test_dirty_rows_end_to_end():
    rows = [
        make_row(strike=95.0),  # buena
        make_row(strike=95.0, bid=2.01),  # duplicada
        make_row(strike=96.0, bid=math.nan),  # NaN
        make_row(strike=97.0, bid=3.0, ask=2.0),  # bid > ask
        make_row(strike=98.0, ask=-1.0),  # negativo
        {"kind": "put", "strike": 99.0},  # columnas ausentes
        make_row(strike=101.0, bid=0.0),  # ilíquida (bid 0)
        make_row(kind="put", strike=104.0),  # buena
    ]
    quotes = [q for q in (clean_row(r) for r in rows) if q is not None]
    result = filter_chain(quotes, SPOT, DEFAULT_RULES)
    assert [(q.kind, q.strike) for q in result] == [("call", 95.0), ("put", 104.0)]
    assert result[0].bid == pytest.approx(2.00)


# --- Reexportaciones del paquete ---


def test_package_reexports_filters():
    for name in (
        "DEFAULT_RULES",
        "EPS",
        "LiquidityRules",
        "clean_row",
        "dedupe",
        "filter_chain",
        "is_expiry_in_window",
    ):
        assert getattr(datos, name) is getattr(filters, name)
        assert name in datos.__all__


# --- Fixtures grabadas y sintéticas (Etapa C1, bloque 3b) ---
# Las filas viven en tests/fixtures/*.json. Las reales (aapl, spy,
# spx_weekend) se grabaron de Yahoo el sábado 2026-11-21 y se recortaron;
# las demás son sintéticas (campo "source": "synthetic").
#
# Cifras MEDIDAS con DEFAULT_RULES sobre estas fixtures exactas
# (filas crudas -> filas limpias -> filas que sobreviven):
#   aapl         12 -> 12 -> 8  (4 calls + 4 puts; 4 caen por spread)
#   spy          13 -> 13 -> 9  (2 caen por OI 13/91, 2 por spread)
#   spx_weekend  12 -> 10 -> 0  (mercado cerrado: todo bid = 0; 2 OI null)
#   spx          15 -> 15 -> 11 (sintética; 2 por OI < 100, 2 por spread)
#   bid_zero     10 -> 10 -> 2
#   dirty        14 -> 4  -> 3  (10 filas rotas; 1 duplicada)
#   stale_last    2 -> 2  -> 2
#   edge_exact   11 -> 11 -> 6  (cada fila trae su "expect")
# Sobre la grabación completa (sábado) las cifras fueron AAPL 15/28,
# SPY 124/148, ^SPX 0/197: el fin de semana ensancha los spreads.

import json  # noqa: E402
from pathlib import Path  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# (nombre, filas crudas, filas limpias, filas que sobreviven)
MEASURED_SURVIVAL = [
    ("aapl", 12, 12, 8),
    ("spy", 13, 13, 9),
    ("spx_weekend", 12, 10, 0),
    ("spx", 15, 15, 11),
    ("bid_zero", 10, 10, 2),
    ("dirty", 14, 4, 3),
    ("stale_last", 2, 2, 2),
    ("edge_exact", 11, 11, 6),
]

REQUIRED_RAW_KEYS = {"kind", "strike", "bid", "ask", "oi"}


def load_fixture(name):
    """Lee tests/fixtures/<name>.json (admite los literales NaN/Infinity)."""
    with open(FIXTURES_DIR / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


def run_filters(fixture, rules=DEFAULT_RULES):
    """Limpia y filtra las filas de una fixture: (limpias, supervivientes)."""
    cleaned = [q for q in (clean_row(r) for r in fixture["rows"]) if q is not None]
    return cleaned, filter_chain(cleaned, fixture["spot"], rules)


def has_nan(quote):
    """True si algún campo numérico de la cotización es NaN o infinito."""
    values = [getattr(quote, f.name) for f in dataclasses.fields(quote)]
    return any(
        isinstance(v, float) and not math.isfinite(v) for v in values if v is not None
    )


@pytest.mark.parametrize("name, n_raw, n_clean, n_alive", MEASURED_SURVIVAL)
def test_fixture_survival_counts(name, n_raw, n_clean, n_alive):
    fixture = load_fixture(name)
    cleaned, alive = run_filters(fixture)
    assert len(fixture["rows"]) == n_raw
    assert len(cleaned) == n_clean
    assert len(alive) == n_alive
    assert not any(has_nan(q) for q in alive)


@pytest.mark.parametrize("name", [m[0] for m in MEASURED_SURVIVAL])
def test_fixture_is_well_formed(name):
    fixture = load_fixture(name)
    assert fixture["source"] in ("real", "synthetic")
    assert fixture["spot"] > 0
    assert fixture["rows"]


@pytest.mark.parametrize("name", ["aapl", "spy", "spx_weekend", "spx"])
def test_chain_fixtures_keep_the_raw_row_keys(name):
    for row in load_fixture(name)["rows"]:
        assert REQUIRED_RAW_KEYS <= set(row)


def test_real_fixtures_are_marked_real_and_spx_liquid_is_synthetic():
    for name in ("aapl", "spy", "spx_weekend"):
        assert load_fixture(name)["source"] == "real"
    assert load_fixture("spx")["source"] == "synthetic"


def test_aapl_survivors_are_the_measured_strikes():
    _, alive = run_filters(load_fixture("aapl"))
    assert [(q.kind, q.strike) for q in alive] == [
        ("call", 330.0),
        ("call", 340.0),
        ("call", 345.0),
        ("call", 360.0),
        ("put", 320.0),
        ("put", 340.0),
        ("put", 345.0),
        ("put", 375.0),
    ]


def test_spy_drops_low_open_interest_and_wide_spreads():
    _, alive = run_filters(load_fixture("spy"))
    strikes = {(q.kind, q.strike) for q in alive}
    assert ("call", 702.0) not in strikes  # OI 13
    assert ("call", 714.0) not in strikes  # OI 91
    assert ("put", 706.0) not in strikes  # spread 3,49 / mid 28,7 = 12 %
    assert ("put", 715.0) not in strikes  # spread 3,72 / mid 33,4 = 11 %
    # Yahoo rellena con 1e-05 la IV que no sabe calcular: la fila sigue
    # siendo líquida (la IV de Yahoo es solo referencia, no filtra).
    put_755 = next(q for q in alive if (q.kind, q.strike) == ("put", 755.0))
    assert put_755.iv_yahoo == pytest.approx(1e-05)


def test_spx_weekend_all_bids_zero_nothing_survives():
    fixture = load_fixture("spx_weekend")
    assert all(row["bid"] == 0 for row in fixture["rows"])
    cleaned, alive = run_filters(fixture)
    assert cleaned  # las filas no están rotas: son ilíquidas
    assert alive == []


def test_spx_synthetic_filters_low_oi_and_wide_spreads():
    _, alive = run_filters(load_fixture("spx"))
    strikes = {(q.kind, q.strike) for q in alive}
    for dropped in [("call", 7100.0), ("put", 7100.0), ("call", 7200.0), ("put", 6800.0)]:
        assert dropped not in strikes
    assert sum(q.kind == "call" for q in alive) == 6
    assert sum(q.kind == "put" for q in alive) == 5


def test_bid_zero_fixture_offers_none_of_the_zero_bid_rows():
    _, alive = run_filters(load_fixture("bid_zero"))
    assert all(q.bid > 0 and q.ask > 0 for q in alive)
    assert [(q.kind, q.strike) for q in alive] == [("call", 100.0), ("put", 100.0)]


def test_dirty_fixture_drops_broken_rows_and_keeps_the_rest():
    cleaned, alive = run_filters(load_fixture("dirty"))
    assert [(q.kind, q.strike) for q in cleaned] == [
        ("call", 95.0),
        ("call", 95.0),
        ("put", 100.0),
        ("put", 104.0),
    ]
    assert [(q.kind, q.strike) for q in alive] == [
        ("call", 95.0),
        ("put", 100.0),
        ("put", 104.0),
    ]
    # Del duplicado se conserva la primera fila (bid 5,60).
    assert alive[0].bid == pytest.approx(5.60)
    # Opcionales NaN -> valores seguros.
    put_100 = alive[1]
    assert put_100.last is None and put_100.iv_yahoo is None and put_100.volume == 0
    assert not any(has_nan(q) for q in cleaned)


def test_stale_last_premium_comes_from_mid_not_last():
    _, alive = run_filters(load_fixture("stale_last"))
    put = next(q for q in alive if q.kind == "put")
    assert put.last == pytest.approx(176.0)
    assert put.mid == pytest.approx(328.5)  # (322 + 335) / 2
    assert abs(put.mid - put.last) > 100


def edge_rows():
    """Filas de edge_exact como parámetros (id = caso legible)."""
    return [pytest.param(row, id=row["case"]) for row in load_fixture("edge_exact")["rows"]]


@pytest.mark.parametrize("row", edge_rows())
def test_edge_exact_rows(row):
    quote = clean_row(row)
    assert quote is not None
    assert survives(quote, spot=load_fixture("edge_exact")["spot"]) is row["expect"]


@pytest.mark.parametrize(
    "case", load_fixture("edge_exact")["expiry_days"], ids=lambda c: f"{c['days']}d"
)
def test_edge_exact_expiry_days(case):
    assert is_expiry_in_window(case["days"]) is case["expect"]


def test_edge_exact_needs_the_tolerance():
    # Sin EPS, la fila 0,30/0,40 (y la de 10 % exacto) se perdería.
    no_eps = LiquidityRules(eps=0.0)
    _, with_eps = run_filters(load_fixture("edge_exact"))
    _, without = run_filters(load_fixture("edge_exact"), no_eps)
    assert ("put", 103.0) in {(q.kind, q.strike) for q in with_eps}
    assert ("put", 103.0) not in {(q.kind, q.strike) for q in without}


def test_fixtures_have_no_absolute_dates():
    # El reloj se fija en los tests (bloque 3d): las fixtures no llevan fechas.
    for path in FIXTURES_DIR.glob("*.json"):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        assert "expiry" not in fixture
        for row in fixture["rows"]:
            assert "last_trade" not in row and "expiry" not in row
            assert not any(isinstance(v, str) and v[:4].isdigit() for v in row.values())
