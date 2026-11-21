"""Pruebas del adaptador de Yahoo (bloque 4) SIN Internet.

Se usa un módulo `yfinance` de mentira que se pasa al constructor
(`yf_module=...`). Las tablas que devuelve son DataFrames de pandas de
verdad, igual que las del yfinance real, para probar la conversión.
La carpeta de caché tz siempre es `tmp_path`: nunca se crea la carpeta
`.cache_datos/` real.
"""

import math
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from datos import yahoo
from datos.errors import (
    MSG_EMPTY,
    MSG_NETWORK,
    MSG_RATE_LIMIT,
    DatosError,
    EmptyDataError,
    NetworkError,
    RateLimitError,
)
from datos.provider import MarketDataProvider
from datos.service import MSG_Q_INDEX, MSG_Q_MISSING, load_with_notices
from datos.yahoo import DEFAULT_TIMEOUT, DEFAULT_TZ_CACHE_DIR, YahooProvider

TODAY = date(2026, 11, 20)
NOW = datetime(2026, 11, 20, 10, 30, tzinfo=ZoneInfo("America/New_York"))


# --- yfinance de mentira ---


class FakeYFRateLimitError(Exception):
    """Imita yfinance.exceptions.YFRateLimitError (mismo nombre de clase)."""

    def __init__(self):
        super().__init__("Too Many Requests. Rate limited. Try after a while.")


FakeYFRateLimitError.__name__ = "YFRateLimitError"


def _calls_df():
    return pd.DataFrame(
        {
            "contractSymbol": ["SPY1", "SPY2"],
            "strike": [690.0, 700.0],
            "lastPrice": [25.49, 19.9],
            "bid": [25.5, 19.49],
            "ask": [25.91, 19.9],
            "volume": [5549.0, float("nan")],
            "openInterest": [4224, 11748],
            "impliedVolatility": [0.3412, 0.3213],
            "inTheMoney": [False, False],
        }
    )


def _puts_df():
    return pd.DataFrame(
        {
            "strike": [680.0],
            "lastPrice": [10.0],
            "bid": [12.1],
            "ask": [12.4],
            "volume": [100],
            "openInterest": [900],
            "impliedVolatility": [0.29],
        }
    )


class FakeTicker:
    """Ticker falso: datos y errores configurables por la prueba."""

    def __init__(self, module, symbol, session=None):
        self.module = module
        self.symbol = symbol
        self.session = session
        cfg = module.config.get(symbol, {})
        self._cfg = cfg

    def _maybe_fail(self, what):
        error = self._cfg.get("errors", {}).get(what)
        if error is not None:
            self.module.log.append((self.symbol, what, "error"))
            raise error
        self.module.log.append((self.symbol, what))

    @property
    def fast_info(self):
        self._maybe_fail("fast_info")
        return self._cfg.get("fast_info", {})

    @property
    def info(self):
        self._maybe_fail("info")
        return self._cfg.get("info", {})

    @property
    def options(self):
        self._maybe_fail("options")
        return tuple(self._cfg.get("options", ()))

    def option_chain(self, date=None):
        self._maybe_fail("option_chain")
        chains = self._cfg.get("chains", {})
        if date not in chains:
            raise ValueError(f"Expiration `{date}` cannot be found.")
        calls, puts = chains[date]
        return SimpleNamespace(calls=calls, puts=puts, underlying={})


class FakeYF:
    """Módulo yfinance falso: registra tickers creados y llamadas."""

    def __init__(self, config=None):
        self.config = config or {}
        self.log = []
        self.tickers = []
        self.tz_cache_locations = []

    def Ticker(self, symbol, session=None):  # noqa: N802 (mismo nombre que yfinance)
        ticker = FakeTicker(self, symbol, session)
        self.tickers.append(ticker)
        return ticker

    def set_tz_cache_location(self, path):
        self.tz_cache_locations.append(path)


def _spy_config(expiries=("2026-12-04", "2026-12-18")):
    return {
        "SPY": {
            "fast_info": {"lastPrice": 689.81},
            "info": {
                "regularMarketPrice": 1.0,
                "dividendYield": 1.12,
                "trailingAnnualDividendYield": 0.0079,
            },
            "options": expiries,
            "chains": {e: (_calls_df(), _puts_df()) for e in expiries},
        },
        "^IRX": {"fast_info": {"lastPrice": 4.12}},
    }


SENTINEL_SESSION = object()


def make_provider(tmp_path, config=None, **kwargs):
    fake = FakeYF(_spy_config() if config is None else config)
    kwargs.setdefault("session", SENTINEL_SESSION)
    provider = YahooProvider(tz_cache_dir=tmp_path / "tz", yf_module=fake, **kwargs)
    return provider, fake


# --- Construcción ---


def test_cumple_el_protocolo(tmp_path):
    provider, _fake = make_provider(tmp_path)
    assert isinstance(provider, MarketDataProvider)


def test_tz_cache_dir_inyectado(tmp_path):
    provider, fake = make_provider(tmp_path)
    assert fake.tz_cache_locations == [str(tmp_path / "tz")]
    assert (tmp_path / "tz").is_dir()
    assert provider.tz_cache_dir == tmp_path / "tz"


def test_tz_cache_dir_por_defecto_en_la_raiz_del_repo():
    repo_root = Path(__file__).resolve().parent.parent
    assert DEFAULT_TZ_CACHE_DIR == repo_root / ".cache_datos" / "yfinance"


def test_timeout_por_defecto_explicito(tmp_path):
    provider, _fake = make_provider(tmp_path)
    assert DEFAULT_TIMEOUT == 10
    assert provider.timeout == 10


def test_session_inyectada_llega_a_cada_ticker(tmp_path):
    provider, fake = make_provider(tmp_path)
    provider.get_spot("SPY")
    provider.get_rate()
    assert fake.tickers
    assert all(t.session is SENTINEL_SESSION for t in fake.tickers)


def test_ticker_se_reutiliza(tmp_path):
    provider, fake = make_provider(tmp_path)
    provider.get_spot("SPY")
    provider.get_expirations("SPY")
    provider.get_chain("SPY", "2026-12-04")
    assert [t.symbol for t in fake.tickers] == ["SPY"]


def test_timeout_session_impone_el_timeout(tmp_path, monkeypatch):
    """La sesión real fija el timeout de CADA solicitud (yfinance pasa 30)."""
    from curl_cffi import requests as curl_requests

    seen = []

    def fake_request(self, method, url, *args, **kwargs):
        seen.append((method, url, kwargs.get("timeout")))
        return "respuesta"

    monkeypatch.setattr(curl_requests.Session, "request", fake_request)
    session = yahoo.build_session(timeout=7)
    assert isinstance(session, curl_requests.Session)
    assert session.get("https://example.invalid/x", timeout=30) == "respuesta"
    session.request("GET", "https://example.invalid/y")
    assert seen == [
        ("GET", "https://example.invalid/x", 7),
        ("GET", "https://example.invalid/y", 7),
    ]


def test_sin_session_se_construye_una_con_el_timeout(tmp_path, monkeypatch):
    built = []
    monkeypatch.setattr(yahoo, "build_session", lambda timeout: built.append(timeout) or "S")
    provider = YahooProvider(tz_cache_dir=tmp_path, timeout=4, yf_module=FakeYF(_spy_config()))
    assert built == [4]
    provider.get_spot("SPY")


# --- Spot ---


def test_spot_prefiere_fast_info(tmp_path):
    provider, fake = make_provider(tmp_path)
    assert provider.get_spot("SPY") == 689.81
    assert ("SPY", "info") not in fake.log


def test_spot_fast_info_atributo(tmp_path):
    config = _spy_config()
    config["SPY"]["fast_info"] = SimpleNamespace(last_price=500.5)
    provider, _fake = make_provider(tmp_path, config)
    assert provider.get_spot("SPY") == 500.5


def test_spot_sin_fast_info_usa_info(tmp_path):
    config = _spy_config()
    config["SPY"]["fast_info"] = {"lastPrice": float("nan")}
    config["SPY"]["info"]["regularMarketPrice"] = 688.0
    provider, _fake = make_provider(tmp_path, config)
    assert provider.get_spot("SPY") == 688.0


def test_spot_sin_dato_es_respuesta_vacia(tmp_path):
    config = _spy_config()
    config["SPY"]["fast_info"] = {}
    config["SPY"]["info"] = {}
    provider, _fake = make_provider(tmp_path, config)
    with pytest.raises(EmptyDataError) as excinfo:
        provider.get_spot("SPY")
    assert excinfo.value.message == MSG_EMPTY


# --- r y q ---


def test_irx_porcentaje_a_fraccion(tmp_path):
    provider, fake = make_provider(tmp_path)
    assert provider.get_rate() == pytest.approx(0.0412)
    assert fake.tickers[-1].symbol == "^IRX"


def test_irx_sin_dato_es_respuesta_vacia(tmp_path):
    config = _spy_config()
    config["^IRX"]["fast_info"] = {"lastPrice": None}
    provider, _fake = make_provider(tmp_path, config)
    with pytest.raises(EmptyDataError):
        provider.get_rate()


def test_q_desde_trailing_y_no_desde_dividend_yield(tmp_path):
    provider, _fake = make_provider(tmp_path)
    assert provider.get_dividend_yield("SPY") == pytest.approx(0.0079)


def test_q_sin_trailing_es_none_aunque_haya_dividend_yield(tmp_path):
    config = _spy_config()
    del config["SPY"]["info"]["trailingAnnualDividendYield"]
    provider, _fake = make_provider(tmp_path, config)
    assert provider.get_dividend_yield("SPY") is None


@pytest.mark.parametrize("value", [None, float("nan"), -0.01, "0.01", True])
def test_q_invalido_es_none(tmp_path, value):
    config = _spy_config()
    config["SPY"]["info"]["trailingAnnualDividendYield"] = value
    provider, _fake = make_provider(tmp_path, config)
    assert provider.get_dividend_yield("SPY") is None


def test_info_que_falla_deja_q_no_disponible_con_aviso(tmp_path):
    config = _spy_config()
    config["SPY"]["errors"] = {"info": KeyError("trailingAnnualDividendYield")}
    provider, _fake = make_provider(tmp_path, config)
    with pytest.raises(DatosError):
        provider.get_dividend_yield("SPY")
    snapshot, notices = load_with_notices(
        "SPY", provider, today=TODAY, now=NOW, cache_dir=tmp_path / "cache"
    )
    assert snapshot.q is None
    assert snapshot.q_source == "no_disponible"
    assert MSG_Q_MISSING in notices


def test_info_con_429_tambien_deja_q_no_disponible(tmp_path):
    config = _spy_config()
    config["SPY"]["errors"] = {"info": FakeYFRateLimitError()}
    provider, _fake = make_provider(tmp_path, config)
    snapshot, notices = load_with_notices(
        "SPY", provider, today=TODAY, now=NOW, cache_dir=tmp_path / "cache"
    )
    assert snapshot.q is None
    assert MSG_Q_MISSING in notices
    assert snapshot.chains


# --- Vencimientos y cadenas ---


def test_vencimientos_como_lista_iso(tmp_path):
    provider, _fake = make_provider(tmp_path)
    assert provider.get_expirations("SPY") == ["2026-12-04", "2026-12-18"]


def test_sin_vencimientos_lista_vacia(tmp_path):
    config = _spy_config(expiries=())
    provider, _fake = make_provider(tmp_path, config)
    assert provider.get_expirations("SPY") == []


def test_cadena_dataframes_a_list_dict(tmp_path):
    provider, _fake = make_provider(tmp_path)
    rows = provider.get_chain("SPY", "2026-12-04")
    assert isinstance(rows, list)
    assert all(isinstance(row, dict) for row in rows)
    assert [row["kind"] for row in rows] == ["call", "call", "put"]
    first = rows[0]
    assert first == {
        "kind": "call",
        "strike": 690.0,
        "bid": 25.5,
        "ask": 25.91,
        "last": 25.49,
        "oi": 4224.0,
        "volume": 5549.0,
        "iv_yahoo": 0.3412,
    }
    # Tipos de Python puros (nada de numpy/pandas) y NaN -> None.
    for row in rows:
        for value in row.values():
            assert value is None or type(value) in (str, float)
    assert rows[1]["volume"] is None
    assert rows[2] == {
        "kind": "put",
        "strike": 680.0,
        "bid": 12.1,
        "ask": 12.4,
        "last": 10.0,
        "oi": 900.0,
        "volume": 100.0,
        "iv_yahoo": 0.29,
    }


def test_cadena_sin_columna_omite_la_clave(tmp_path):
    config = _spy_config()
    calls = _calls_df().drop(columns=["openInterest"])
    config["SPY"]["chains"]["2026-12-04"] = (calls, _puts_df())
    provider, _fake = make_provider(tmp_path, config)
    rows = provider.get_chain("SPY", "2026-12-04")
    assert "oi" not in rows[0]
    assert rows[2]["oi"] == 900.0


def test_cadena_con_pd_na_da_none(tmp_path):
    config = _spy_config()
    calls = _calls_df().astype({"openInterest": "Int64"})
    calls.loc[0, "openInterest"] = pd.NA
    config["SPY"]["chains"]["2026-12-04"] = (calls, _puts_df())
    provider, _fake = make_provider(tmp_path, config)
    rows = provider.get_chain("SPY", "2026-12-04")
    assert rows[0]["oi"] is None
    assert rows[1]["oi"] == 11748.0


def test_cadena_con_un_lado_none(tmp_path):
    config = _spy_config()
    config["SPY"]["chains"]["2026-12-04"] = (None, _puts_df())
    provider, _fake = make_provider(tmp_path, config)
    rows = provider.get_chain("SPY", "2026-12-04")
    assert [row["kind"] for row in rows] == ["put"]


def test_cadena_vacia_es_respuesta_vacia(tmp_path):
    config = _spy_config()
    config["SPY"]["chains"]["2026-12-04"] = (None, None)
    provider, _fake = make_provider(tmp_path, config)
    with pytest.raises(EmptyDataError):
        provider.get_chain("SPY", "2026-12-04")


def test_vencimiento_inexistente_es_respuesta_vacia(tmp_path):
    provider, _fake = make_provider(tmp_path)
    with pytest.raises(EmptyDataError):
        provider.get_chain("SPY", "2030-01-01")


# --- Mapeo de errores ---


def _requests_errors():
    import requests

    return [
        requests.exceptions.ConnectionError("conexión rechazada"),
        requests.exceptions.Timeout("tiempo agotado"),
        requests.exceptions.ReadTimeout("lectura agotada"),
    ]


def _curl_errors():
    from curl_cffi.requests import exceptions as curl_exc

    return [
        curl_exc.ConnectionError("Failed to connect"),
        curl_exc.Timeout("Operation timed out"),
        curl_exc.ConnectTimeout("connect timed out"),
        curl_exc.DNSError("Could not resolve host"),
    ]


NETWORK_ERRORS = [
    ConnectionError("sin red"),
    TimeoutError("timeout"),
    OSError("socket"),
    RuntimeError("red bloqueada en tests: use LIVE_DATA=1"),
]


@pytest.mark.parametrize(
    "error",
    NETWORK_ERRORS + _requests_errors() + _curl_errors(),
    ids=lambda e: type(e).__module__ + "." + type(e).__name__,
)
def test_errores_de_conexion_son_network_error(tmp_path, error):
    config = _spy_config()
    config["SPY"]["errors"] = {"fast_info": error, "options": error, "option_chain": error}
    provider, _fake = make_provider(tmp_path, config)
    for call in (
        lambda: provider.get_spot("SPY"),
        lambda: provider.get_expirations("SPY"),
        lambda: provider.get_chain("SPY", "2026-12-04"),
    ):
        with pytest.raises(NetworkError) as excinfo:
            call()
        assert excinfo.value.message == MSG_NETWORK
        assert excinfo.value.__cause__ is error


def _http_429(module_name):
    if module_name == "curl":
        from curl_cffi.requests import exceptions as curl_exc

        error = curl_exc.HTTPError("HTTP Error 429")
    else:
        import requests

        error = requests.exceptions.HTTPError("HTTP Error")
    error.response = SimpleNamespace(status_code=429)
    return error


@pytest.mark.parametrize(
    "error",
    [
        FakeYFRateLimitError(),
        Exception("Too Many Requests. Rate limited."),
        _http_429("curl"),
        _http_429("requests"),
    ],
    ids=["YFRateLimitError", "texto", "curl-429", "requests-429"],
)
def test_limite_de_solicitudes_es_rate_limit_error(tmp_path, error):
    config = _spy_config()
    config["SPY"]["errors"] = {"option_chain": error}
    provider, _fake = make_provider(tmp_path, config)
    with pytest.raises(RateLimitError) as excinfo:
        provider.get_chain("SPY", "2026-12-04")
    assert excinfo.value.message == MSG_RATE_LIMIT


def test_yfinance_rate_limit_real_es_rate_limit_error(tmp_path):
    from yfinance.exceptions import YFRateLimitError

    config = _spy_config()
    config["SPY"]["errors"] = {"options": YFRateLimitError()}
    provider, _fake = make_provider(tmp_path, config)
    with pytest.raises(RateLimitError):
        provider.get_expirations("SPY")


def test_yfinance_ticker_inexistente_es_respuesta_vacia(tmp_path):
    from yfinance.exceptions import YFTickerMissingError

    config = _spy_config()
    config["SPY"]["errors"] = {"options": YFTickerMissingError("SPY", "no data")}
    provider, _fake = make_provider(tmp_path, config)
    with pytest.raises(EmptyDataError):
        provider.get_expirations("SPY")


@pytest.mark.parametrize("error", [KeyError("x"), IndexError("x"), ValueError("x"), TypeError("x")])
def test_errores_de_formato_son_respuesta_vacia(tmp_path, error):
    config = _spy_config()
    config["SPY"]["errors"] = {"options": error}
    provider, _fake = make_provider(tmp_path, config)
    with pytest.raises(EmptyDataError):
        provider.get_expirations("SPY")


def test_datos_error_pasa_tal_cual(tmp_path):
    config = _spy_config()
    original = RateLimitError("mensaje propio")
    config["SPY"]["errors"] = {"options": original}
    provider, _fake = make_provider(tmp_path, config)
    with pytest.raises(RateLimitError) as excinfo:
        provider.get_expirations("SPY")
    assert excinfo.value is original


def test_error_desconocido_es_datos_error(tmp_path):
    class Raro(Exception):
        pass

    config = _spy_config()
    config["SPY"]["errors"] = {"options": Raro("???")}
    provider, _fake = make_provider(tmp_path, config)
    with pytest.raises(DatosError):
        provider.get_expirations("SPY")


# --- Carga completa con el servicio ---


def test_carga_spy_con_el_servicio(tmp_path):
    provider, _fake = make_provider(tmp_path)
    snapshot, notices = load_with_notices(
        "SPY", provider, today=TODAY, now=NOW, cache_dir=tmp_path / "cache"
    )
    assert snapshot.ticker == "SPY"
    assert snapshot.spot == 689.81
    assert snapshot.rate == pytest.approx(0.0412)
    assert snapshot.q == pytest.approx(0.0079)
    assert snapshot.q_source == "yahoo"
    assert sorted(snapshot.chains) == ["2026-12-04", "2026-12-18"]
    for quotes in snapshot.chains.values():
        for quote in quotes:
            assert math.isfinite(quote.mid)
    assert notices == []
    assert (tmp_path / "cache" / "SPY.json").is_file()


def test_429_en_una_cadena_para_la_carga(tmp_path):
    config = _spy_config(expiries=("2026-12-04", "2026-12-18", "2027-01-15"))
    provider, fake = make_provider(tmp_path, config)
    original = provider.get_chain
    calls = []

    def chain_with_429(ticker, expiry):
        calls.append(expiry)
        if expiry == "2026-12-18":
            config["SPY"]["errors"] = {"option_chain": FakeYFRateLimitError()}
        return original(ticker, expiry)

    provider.get_chain = chain_with_429
    snapshot, _notices = load_with_notices(
        "SPY", provider, today=TODAY, now=NOW, cache_dir=tmp_path / "cache"
    )
    assert list(snapshot.chains) == ["2026-12-04"]
    assert snapshot.complete is False
    assert calls == ["2026-12-04", "2026-12-18"]


def test_indice_spx_usa_el_simbolo_y_la_etiqueta(tmp_path):
    config = _spy_config()
    config["^SPX"] = dict(config.pop("SPY"))
    config["^SPX"]["fast_info"] = {"lastPrice": 690.0}
    provider, fake = make_provider(tmp_path, config)
    snapshot, notices = load_with_notices(
        "^SPX", provider, today=TODAY, now=NOW, cache_dir=tmp_path / "cache"
    )
    assert snapshot.ticker == "SPX"
    assert snapshot.q is None
    assert snapshot.q_source == "indice"
    assert MSG_Q_INDEX in notices
    assert {t.symbol for t in fake.tickers} == {"^SPX", "^IRX"}
    # El índice no pide dividendos a Yahoo.
    assert ("^SPX", "info") not in fake.log
    assert (tmp_path / "cache" / "SPX.json").is_file()
    assert not (tmp_path / "cache" / "^SPX.json").exists()


def test_red_caida_en_el_servicio_es_network_error(tmp_path):
    from curl_cffi.requests import exceptions as curl_exc

    config = _spy_config()
    config["SPY"]["errors"] = {"fast_info": curl_exc.ConnectionError("Failed to connect")}
    provider, _fake = make_provider(tmp_path, config)
    with pytest.raises(NetworkError):
        load_with_notices("SPY", provider, today=TODAY, now=NOW, cache_dir=tmp_path / "cache")
