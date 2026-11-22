"""Tests de estrategias/serialize.py (Etapa D, bloque 1; AC-D-1, AC-D-2, AC-D-6).

- Ida y vuelta: estrategia -> documento JSON -> estrategia, sin pérdidas,
  con patas manuales, automáticas y de mercado.
- El "portero": cualquier archivo raro (enorme, roto, con tipos erróneos,
  valores fuera de lista o magnitudes absurdas) devuelve (None, [mensaje])
  y NUNCA lanza una excepción.
"""

import ast
import json
import random
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import opciones.validation
from estrategias import serialize
from estrategias.serialize import (
    BOUNDS,
    MAX_BYTES,
    MAX_LEGS,
    MAX_NAME_LEN,
    SCHEMA_VERSION,
    SavedLeg,
    SavedStrategy,
    dumps_strategy,
    parse_strategy_json,
    prepare_document,
    saved_leg_to_engine,
    strategy_to_dict,
)
from opciones import TEMPLATES, CommissionSettings, Leg, Market, build_legs

SAVED_AT = "2026-11-20T10:30:00-05:00"
NOW = datetime(2026, 11, 20, 10, 30, tzinfo=ZoneInfo("America/New_York"))
MARKET = Market("Acción", 100.0, 0.25, 45, 0.04, 0.01, "binomial")
SETTINGS = CommissionSettings(1.25, 0.6, False)


def leg_dict(kind="call", side=1, quantity=1.0, strike=100.0, price=2.5,
             premium_manual=False, premium_source=None, bid=None, ask=None,
             iv_yahoo=None, expiry=None, leg_id=0):
    """Pata con el mismo formato de diccionario que usa app.py."""
    return {
        "id": leg_id,
        "kind": kind,
        "side": side,
        "quantity": quantity,
        "strike": strike,
        "price": price,
        "premium_manual": premium_manual,
        "premium_source": premium_source,
        "bid": bid,
        "ask": ask,
        "iv_yahoo": iv_yahoo,
        "expiry": expiry,
    }


def iron_condor_dicts():
    """Iron condor del catálogo con primas automáticas (como en la app)."""
    template = next(t for t in TEMPLATES if t.key == "iron_condor")
    legs = build_legs(template, MARKET)
    return [
        leg_dict(leg.kind, leg.side, float(leg.quantity), leg.strike, leg.price, leg_id=i)
        for i, leg in enumerate(legs)
    ]


def manual_call_dicts():
    return [leg_dict("call", 1, 2.0, 105.0, 3.33, premium_manual=True)]


def market_leg_dicts():
    return [
        leg_dict("put", -1, 1.0, 95.0, 1.9, premium_source="mercado", bid=1.8,
                 ask=2.0, iv_yahoo=0.31, expiry="2026-12-18"),
        leg_dict("stock", 1, 100.0, None, 100.0, leg_id=1),
    ]


def valid_doc():
    """Documento válido mínimo (como diccionario, para mutarlo en los tests)."""
    return strategy_to_dict(manual_call_dicts(), MARKET, SETTINGS, "Mi call", SAVED_AT, "SPY")


def to_bytes(doc):
    return json.dumps(doc).encode("utf-8")


def assert_rejected(data):
    """(None, [mensajes en español]) sin excepción."""
    strategy, errors = parse_strategy_json(data)
    assert strategy is None
    assert errors, "debía haber al menos un mensaje"
    assert all(isinstance(e, str) and e for e in errors)
    return errors


# --- Constantes ---


def test_constantes_publicas():
    assert SCHEMA_VERSION == 1
    assert MAX_BYTES == 262144
    assert MAX_LEGS == 10
    assert MAX_NAME_LEN == 60
    assert BOUNDS["spot"] == (0.01, 1e7)
    assert BOUNDS["strike"] == (0.01, 1e7)
    assert BOUNDS["quantity"] == (1e-6, 1e5)
    assert BOUNDS["price"] == (0.0, 1e6)
    assert BOUNDS["vol"] == (0.0001, 5.0)
    assert BOUNDS["days"] == (0, 3650)
    assert BOUNDS["rate"] == (-0.5, 1.0)
    assert BOUNDS["q"] == (-0.5, 1.0)
    assert BOUNDS["per_contract"] == (0.0, 1e3)
    assert BOUNDS["index_surcharge"] == (0.0, 1e3)


# --- Ida y vuelta (AC-D-1) ---


@pytest.mark.parametrize("make_legs", [iron_condor_dicts, manual_call_dicts, market_leg_dicts])
def test_ida_y_vuelta_campo_a_campo(make_legs):
    legs = make_legs()
    doc = strategy_to_dict(legs, MARKET, SETTINGS, "Mi estrategia", SAVED_AT, "SPY")
    strategy, errors = parse_strategy_json(dumps_strategy(doc))
    assert errors == []
    assert isinstance(strategy, SavedStrategy)
    assert strategy.name == "Mi estrategia"
    assert strategy.saved_at == SAVED_AT
    assert strategy.ticker == "SPY"
    assert strategy.market == MARKET
    assert strategy.commissions == SETTINGS
    assert len(strategy.legs) == len(legs)
    for saved, original in zip(strategy.legs, legs):
        assert isinstance(saved, SavedLeg)
        assert saved.kind == original["kind"]
        assert saved.side == original["side"]
        assert saved.quantity == original["quantity"]
        expected_strike = None if original["kind"] == "stock" else original["strike"]
        assert saved.strike == expected_strike
        assert saved.price == original["price"]
        assert saved.premium_manual == original["premium_manual"]
        assert saved.premium_source == original["premium_source"]
        if original["premium_source"] == "mercado":
            assert (saved.bid, saved.ask, saved.expiry) == (original["bid"], original["ask"], original["expiry"])
        else:
            assert (saved.bid, saved.ask, saved.expiry) == (None, None, None)


def test_ida_y_vuelta_sin_ticker_y_con_datetime():
    doc = strategy_to_dict(manual_call_dicts(), MARKET, SETTINGS, "x", NOW)
    assert doc["ticker"] is None
    assert doc["saved_at"] == NOW.isoformat(timespec="seconds")
    strategy, errors = parse_strategy_json(dumps_strategy(doc))
    assert errors == []
    assert strategy.ticker is None


def test_documento_no_contiene_campos_prohibidos():
    doc = strategy_to_dict(market_leg_dicts(), MARKET, SETTINGS, "x", SAVED_AT)
    text = dumps_strategy(doc).decode("utf-8")
    for forbidden in ('"id"', "iv_yahoo", "snapshot", "chain"):
        assert forbidden not in text
    assert doc["schema_version"] == 1
    assert set(doc) == {"schema_version", "name", "saved_at", "ticker", "market", "commissions", "legs"}


def test_bid_ask_expiry_solo_en_patas_de_mercado():
    doc = strategy_to_dict(market_leg_dicts() + manual_call_dicts(), MARKET, SETTINGS, "x", SAVED_AT)
    market_leg, stock_leg, manual_leg = doc["legs"]
    assert {"bid", "ask", "expiry"} <= set(market_leg)
    for other in (stock_leg, manual_leg):
        assert not ({"bid", "ask", "expiry"} & set(other))
    assert "strike" not in stock_leg


def test_dumps_es_utf8_con_indentacion():
    doc = strategy_to_dict(manual_call_dicts(), MARKET, SETTINGS, "Opción ñ", SAVED_AT)
    raw = dumps_strategy(doc)
    assert isinstance(raw, bytes)
    assert "Opción ñ".encode("utf-8") in raw  # ensure_ascii=False
    assert b'\n  "' in raw  # indent=2


def test_saved_leg_to_engine():
    saved = SavedLeg("call", -1, 2.0, 105.0, 3.0, True, None, None, None, None)
    assert saved_leg_to_engine(saved) == Leg("call", -1, 2.0, 105.0, 3.0)


def test_tipos_congelados():
    strategy, _ = parse_strategy_json(to_bytes(valid_doc()))
    with pytest.raises(Exception):
        strategy.name = "otro"
    assert isinstance(strategy.legs, tuple)


# --- prepare_document (AC-D-6) ---


def test_prepare_document_valido_se_relee_igual():
    raw, errors = prepare_document(iron_condor_dicts(), MARKET, SETTINGS, "  IC  ", NOW, "SPY")
    assert errors == []
    strategy, parse_errors = parse_strategy_json(raw)
    assert parse_errors == []
    assert strategy.name == "IC"
    assert raw == dumps_strategy(strategy_to_dict(iron_condor_dicts(), MARKET, SETTINGS, "IC", NOW, "SPY"))


@pytest.mark.parametrize(
    "legs, market, name",
    [
        (manual_call_dicts(), MARKET, ""),
        (manual_call_dicts(), MARKET, "   "),
        (manual_call_dicts(), MARKET, "x" * 61),
        (manual_call_dicts(), MARKET, "a\nb"),
        ([], MARKET, "x"),
        (manual_call_dicts() * 11, MARKET, "x"),
        (manual_call_dicts(), Market("Acción", 0.0, 0.25, 45, 0.04), "x"),
        (manual_call_dicts(), Market("Acción", None, 0.25, 45, 0.04), "x"),
        ([leg_dict(quantity=-1.0)], MARKET, "x"),
        ([leg_dict(strike=1e300)], MARKET, "x"),
        (manual_call_dicts(), Market("Acción", 0.001, 0.25, 45, 0.04), "x"),
        (manual_call_dicts(), Market("Acción", 100.0, 0.25, 4000, 0.04), "x"),
    ],
)
def test_prepare_document_invalido(legs, market, name):
    raw, errors = prepare_document(legs, market, SETTINGS, name, NOW)
    assert raw is None
    assert errors and all(isinstance(e, str) for e in errors)


def test_prepare_document_cota_nombra_el_campo():
    raw, errors = prepare_document(manual_call_dicts(), Market("Acción", 0.001, 0.25, 45, 0.04), SETTINGS, "x", NOW)
    assert raw is None
    assert any("spot" in e for e in errors)


def test_prepare_document_nombre_de_60_ok():
    raw, errors = prepare_document(manual_call_dicts(), MARKET, SETTINGS, "x" * 60, NOW)
    assert errors == [] and raw is not None


# --- Entradas malas (AC-D-2) ---


def mutate(path, value, delete=False):
    """Documento válido con un valor cambiado (path = lista de claves/índices)."""
    doc = valid_doc()
    target = doc
    for key in path[:-1]:
        target = target[key]
    if delete:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return doc


RAW_BAD_INPUTS = [
    b"",
    b"{",
    b"[]",
    b"null",
    b'"texto"',
    b"42",
    b'{"x": NaN}',
    b'{"x": Infinity}',
    b'{"x": -Infinity}',
    b"\xff\xfe\x00basura",
    "{\"name\": \"\udcff\"}".encode("utf-8", "surrogatepass"),
    b"[" * 100 + b"]" * 100,
    b"[" * 100_000,
    b"[" * 120_000 + b"]" * 120_000,  # > 256 KB
    None,
    "un texto, no bytes",
]


@pytest.mark.parametrize("data", RAW_BAD_INPUTS, ids=range(len(RAW_BAD_INPUTS)))
def test_bytes_malos(data):
    assert_rejected(data)


def test_tope_de_tamano_antes_de_parsear():
    doc = valid_doc()
    base = to_bytes(doc)
    # Rellenamos con espacios (JSON válido) hasta el tamaño exacto.
    exact = base[:-1] + b" " * (MAX_BYTES - len(base)) + b"}"
    assert len(exact) == MAX_BYTES
    strategy, errors = parse_strategy_json(exact)
    assert errors == [] and strategy is not None
    too_big = base[:-1] + b" " * (MAX_BYTES + 1 - len(base)) + b"}"
    assert len(too_big) == MAX_BYTES + 1
    errors = assert_rejected(too_big)
    assert any("256" in e for e in errors)


def test_tope_no_llama_a_json_loads(monkeypatch):
    calls = []
    monkeypatch.setattr(serialize.json, "loads", lambda *a, **k: calls.append(1))
    assert_rejected(b" " * (MAX_BYTES + 1))
    assert calls == []


BAD_DOCS = [
    ("sin schema_version", mutate(["schema_version"], None, delete=True)),
    ("schema 0", mutate(["schema_version"], 0)),
    ("schema texto", mutate(["schema_version"], "1")),
    ("schema float", mutate(["schema_version"], 1.0)),
    ("schema bool", mutate(["schema_version"], True)),
    ("falta name", mutate(["name"], None, delete=True)),
    ("falta market", mutate(["market"], None, delete=True)),
    ("falta commissions", mutate(["commissions"], None, delete=True)),
    ("falta legs", mutate(["legs"], None, delete=True)),
    ("name número", mutate(["name"], 123)),
    ("name vacío", mutate(["name"], "")),
    ("name blancos", mutate(["name"], "   ")),
    ("name 61", mutate(["name"], "x" * 61)),
    ("name salto", mutate(["name"], "a\nb")),
    ("name NUL", mutate(["name"], "a\u0000b")),
    ("name tab", mutate(["name"], "a\tb")),
    ("legs objeto", mutate(["legs"], {})),
    ("legs vacío", mutate(["legs"], [])),
    ("legs 11", mutate(["legs"], valid_doc()["legs"] * 11)),
    ("pata no objeto", mutate(["legs", 0], 5)),
    ("kind futuro", mutate(["legs", 0, "kind"], "futuro")),
    ("kind número", mutate(["legs", 0, "kind"], 5)),
    ("side 0", mutate(["legs", 0, "side"], 0)),
    ("side 2", mutate(["legs", 0, "side"], 2)),
    ("side texto", mutate(["legs", 0, "side"], "1")),
    ("side bool", mutate(["legs", 0, "side"], True)),
    ("side float", mutate(["legs", 0, "side"], 1.0)),
    ("quantity 0", mutate(["legs", 0, "quantity"], 0)),
    ("quantity -1", mutate(["legs", 0, "quantity"], -1)),
    ("quantity texto", mutate(["legs", 0, "quantity"], "1")),
    ("quantity bool", mutate(["legs", 0, "quantity"], True)),
    ("quantity null", mutate(["legs", 0, "quantity"], None)),
    ("falta strike", mutate(["legs", 0, "strike"], None, delete=True)),
    ("strike null", mutate(["legs", 0, "strike"], None)),
    ("strike texto", mutate(["legs", 0, "strike"], "100")),
    ("strike bool", mutate(["legs", 0, "strike"], True)),
    ("price negativo", mutate(["legs", 0, "price"], -1)),
    ("price texto", mutate(["legs", 0, "price"], "2")),
    ("falta price", mutate(["legs", 0, "price"], None, delete=True)),
    ("premium_manual 1", mutate(["legs", 0, "premium_manual"], 1)),
    ("premium_manual texto", mutate(["legs", 0, "premium_manual"], "true")),
    ("premium_source otro", mutate(["legs", 0, "premium_source"], "otro")),
    ("bid sin mercado", mutate(["legs", 0, "bid"], 1.0)),
    ("ask sin mercado", mutate(["legs", 0, "ask"], 1.0)),
    ("expiry sin mercado", mutate(["legs", 0, "expiry"], "2026-12-18")),
    ("saved_at ausente", mutate(["saved_at"], None, delete=True)),
    ("saved_at ayer", mutate(["saved_at"], "ayer")),
    ("saved_at número", mutate(["saved_at"], 20261120)),
    ("saved_at sin zona", mutate(["saved_at"], "2026-11-20T10:30:00")),
    ("ticker número", mutate(["ticker"], 5)),
    ("ticker 21", mutate(["ticker"], "X" * 21)),
    ("market lista", mutate(["market"], [])),
    ("underlying Bono", mutate(["market", "underlying"], "Bono")),
    ("spot 0", mutate(["market", "spot"], 0)),
    ("spot texto", mutate(["market", "spot"], "100")),
    ("spot bool", mutate(["market", "spot"], True)),
    ("falta spot", mutate(["market", "spot"], None, delete=True)),
    ("vol 0", mutate(["market", "vol"], 0)),
    ("days -1", mutate(["market", "days"], -1)),
    ("days 1.5", mutate(["market", "days"], 1.5)),
    ("days bool", mutate(["market", "days"], True)),
    ("pricing montecarlo", mutate(["market", "pricing_model"], "montecarlo")),
    ("commissions lista", mutate(["commissions"], [])),
    ("comisión negativa", mutate(["commissions", "per_contract"], -0.1)),
    ("recargo negativo", mutate(["commissions", "index_surcharge"], -1)),
    ("include_close si", mutate(["commissions", "include_close"], "si")),
]


@pytest.mark.parametrize("label, doc", BAD_DOCS, ids=[label for label, _ in BAD_DOCS])
def test_documentos_malos(label, doc):
    assert_rejected(to_bytes(doc))


def test_pata_de_accion_con_strike_rechazada():
    doc = strategy_to_dict(market_leg_dicts(), MARKET, SETTINGS, "x", SAVED_AT)
    doc["legs"][1]["strike"] = 100.0
    errors = assert_rejected(to_bytes(doc))
    assert any("Pata 2" in e for e in errors)


def test_pata_de_mercado_con_expiry_malo():
    doc = strategy_to_dict(market_leg_dicts(), MARKET, SETTINGS, "x", SAVED_AT)
    doc["legs"][0]["expiry"] = "mañana"
    assert_rejected(to_bytes(doc))


def test_version_futura_dice_version():
    errors = assert_rejected(to_bytes(mutate(["schema_version"], 2)))
    assert any("versión" in e and "nueva" in e for e in errors)


def test_version_ausente_dice_version():
    errors = assert_rejected(to_bytes(mutate(["schema_version"], None, delete=True)))
    assert any("versión" in e for e in errors)


@pytest.mark.parametrize(
    "name",
    ["../../x", "..\\x", "/etc/passwd", "C:\\Windows", "  espacios  ", "x" * 60],
)
def test_nombres_de_ruta_aceptados_como_texto(name):
    strategy, errors = parse_strategy_json(to_bytes(mutate(["name"], name)))
    assert errors == []
    assert strategy.name == name.strip()


def test_claves_extra_ignoradas():
    doc = valid_doc()
    doc["extra"] = {"a": 1}
    doc["market"]["otra"] = 5
    doc["legs"][0]["iv_yahoo"] = 0.3
    doc["legs"][0]["id"] = 7
    strategy, errors = parse_strategy_json(to_bytes(doc))
    assert errors == []
    assert not hasattr(strategy, "extra")
    assert not hasattr(strategy.legs[0], "iv_yahoo")
    assert strategy == parse_strategy_json(to_bytes(valid_doc()))[0]


def test_sin_coercion_silenciosa():
    # Un valor fuera de lista nunca se cambia por un valor por defecto.
    for path, value in [
        (["market", "pricing_model"], "montecarlo"),
        (["legs", 0, "premium_source"], "otro"),
        (["market", "underlying"], "Bono"),
    ]:
        strategy, errors = parse_strategy_json(to_bytes(mutate(path, value)))
        assert strategy is None and errors


def test_pricing_model_y_ticker_ausentes_son_error():
    assert_rejected(to_bytes(mutate(["market", "pricing_model"], None, delete=True)))
    strategy, errors = parse_strategy_json(to_bytes(mutate(["ticker"], None)))
    assert errors == [] and strategy.ticker is None


def test_reutiliza_validadores_del_motor(monkeypatch):
    calls = {"market": 0, "legs": 0}
    real_market = opciones.validation.validate_market
    real_legs = opciones.validation.validate_legs

    def spy_market(market):
        calls["market"] += 1
        return real_market(market)

    def spy_legs(legs):
        calls["legs"] += 1
        return real_legs(legs) + ["Pata 1: error del motor simulado."]

    monkeypatch.setattr(opciones.validation, "validate_market", spy_market)
    monkeypatch.setattr(opciones.validation, "validate_legs", spy_legs)
    errors = assert_rejected(to_bytes(valid_doc()))
    assert calls == {"market": 1, "legs": 1}
    assert "Pata 1: error del motor simulado." in errors


# --- Cotas de magnitud (DD-21, S-2, S-5) ---


MARKET_BOUND_CASES = [
    # (campo, dentro, fuera)
    ("spot", 0.01, 0.001),
    ("spot", 1e7, 1e7 + 1),
    ("vol", 5.0, 5.01),
    ("vol", 0.0001, 0.00009),
    ("days", 3650, 3651),
    ("days", 0, -1),
    ("rate", 1.0, 1.01),
    ("rate", -0.5, -0.51),
    ("q", 1.0, 1.01),
    ("q", -0.5, -0.51),
]


@pytest.mark.parametrize("field, inside, outside", MARKET_BOUND_CASES)
def test_cotas_del_mercado(field, inside, outside):
    strategy, errors = parse_strategy_json(to_bytes(mutate(["market", field], inside)))
    assert errors == [] and strategy is not None
    errors = assert_rejected(to_bytes(mutate(["market", field], outside)))
    assert any(f"«{field}»" in e for e in errors)


COMMISSION_BOUND_CASES = [
    ("per_contract", 1e3, 1e3 + 1),
    ("per_contract", 0.0, -0.01),
    ("index_surcharge", 1e3, 1e3 + 1),
]


@pytest.mark.parametrize("field, inside, outside", COMMISSION_BOUND_CASES)
def test_cotas_de_comisiones(field, inside, outside):
    strategy, errors = parse_strategy_json(to_bytes(mutate(["commissions", field], inside)))
    assert errors == [] and strategy is not None
    errors = assert_rejected(to_bytes(mutate(["commissions", field], outside)))
    assert any(f"«{field}»" in e for e in errors)


LEG_BOUND_CASES = [
    ("strike", 0.01, 0.001),
    ("strike", 1e7, 1e7 + 1),
    ("quantity", 1e-6, 1e-7),
    ("quantity", 1e5, 1e5 + 1),
    ("price", 1e6, 1e6 + 1),
    ("price", 0.0, -0.01),
]


@pytest.mark.parametrize("field, inside, outside", LEG_BOUND_CASES)
def test_cotas_de_las_patas(field, inside, outside):
    strategy, errors = parse_strategy_json(to_bytes(mutate(["legs", 0, field], inside)))
    assert errors == [] and strategy is not None
    errors = assert_rejected(to_bytes(mutate(["legs", 0, field], outside)))
    assert any(f"«{field}»" in e and "Pata 1" in e for e in errors)


def test_cotas_de_bid_ask():
    doc = strategy_to_dict(market_leg_dicts(), MARKET, SETTINGS, "x", SAVED_AT)
    doc["legs"][0]["bid"] = 1e6 + 1
    errors = assert_rejected(to_bytes(doc))
    assert any("«bid»" in e for e in errors)
    doc["legs"][0]["bid"] = 1.8
    doc["legs"][0]["ask"] = -1
    assert_rejected(to_bytes(doc))


NUMERIC_PATHS = [
    ["market", "spot"],
    ["market", "vol"],
    ["market", "days"],
    ["market", "rate"],
    ["market", "q"],
    ["commissions", "per_contract"],
    ["commissions", "index_surcharge"],
    ["legs", 0, "strike"],
    ["legs", 0, "quantity"],
    ["legs", 0, "price"],
]
HOSTILE_TEXTS = ["1e300", "1e308", "-1e6", "1e999", "-1e999"]


@pytest.mark.parametrize("path", NUMERIC_PATHS, ids=lambda p: ".".join(map(str, p)))
@pytest.mark.parametrize("text", HOSTILE_TEXTS)
def test_valores_hostiles_en_cada_campo_numerico(path, text):
    # Se inserta el número como TEXTO del JSON: 1e999 se parsea como inf
    # sin pasar por parse_constant.
    marker = 987654.321
    raw = to_bytes(mutate(path, marker)).replace(b"987654.321", text.encode())
    assert_rejected(raw)


@pytest.mark.parametrize("spot", [1e-300, 1e-200, 1e-150])
def test_spot_diminuto_rechazado(spot):
    errors = assert_rejected(to_bytes(mutate(["market", "spot"], spot)))
    assert any("«spot»" in e for e in errors)


def test_mensaje_de_cota_en_espanol():
    errors = assert_rejected(to_bytes(mutate(["market", "spot"], 0.001)))
    assert any("debe estar entre 0,01 y 10000000" in e for e in errors)


# --- Nunca lanza (fuzz sembrado) ---


def test_fuzz_sembrado_nunca_lanza():
    rng = random.Random(20261122)
    base = dumps_strategy(strategy_to_dict(market_leg_dicts(), MARKET, SETTINGS, "Fuzz", SAVED_AT))
    samples = []
    for _ in range(100):
        data = bytearray(base)
        for _ in range(rng.randint(1, 8)):
            position = rng.randrange(len(data))
            data[position] = rng.randrange(256)
        samples.append(bytes(data))
    values = [None, True, -1, 0, 1e308, "x", [], {}, 1.5, "mercado"]
    for _ in range(100):
        doc = strategy_to_dict(market_leg_dicts(), MARKET, SETTINGS, "Fuzz", SAVED_AT)
        section = rng.choice(["root", "market", "commissions", "leg"])
        if section == "root":
            target = doc
        elif section == "leg":
            target = doc["legs"][rng.randrange(2)]
        else:
            target = doc[section]
        key = rng.choice(list(target))
        target[key] = rng.choice(values)
        samples.append(json.dumps(doc).encode())
    assert len(samples) == 200
    for data in samples:
        strategy, errors = parse_strategy_json(data)
        # Exactamente una de las dos salidas está "vacía".
        assert (strategy is None) != (errors == [])


# --- Inspección del código fuente ---


def test_codigo_fuente_sin_eval_ni_pickle():
    source = Path(serialize.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called.add(node.func.id)
    assert imported <= {"json", "math", "datetime", "dataclasses", "opciones"}
    assert not ({"eval", "exec", "compile", "__import__"} & called)
    for word in ("pickle", "yaml", "marshal"):
        assert word not in source
