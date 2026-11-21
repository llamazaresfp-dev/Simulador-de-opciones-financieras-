"""Pruebas de YahooProvider.get_history SIN Internet (Etapa C2, bloque 7).

Se pasa al constructor un módulo `yfinance` de mentira (`yf_module`).
Su `Ticker.history` devuelve un DataFrame de pandas de verdad (como el
yfinance real) o una tabla mínima sin pandas. La caché tz siempre va a
`tmp_path`.
"""

import math
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from datos.errors import EmptyDataError, NetworkError, RateLimitError
from datos.provider import HistoryProvider, MarketDataProvider
from datos.types import PriceHistory
from datos.yahoo import YahooProvider

REPO_ROOT = Path(__file__).resolve().parent.parent
START = date(2026, 11, 16)
END = date(2026, 11, 21)
SESSION = object()


def history_frame(close=(100.0, 101.0, 102.0), adj=(99.0, 100.5, 102.0), dividends=(0.0, 0.5, 0.0)):
    """DataFrame como el de `Ticker.history(auto_adjust=False, actions=True)`."""
    index = pd.DatetimeIndex(
        ["2026-11-17", "2026-11-18", "2026-11-19"], name="Date"
    ).tz_localize("America/New_York")
    return pd.DataFrame(
        {
            "Open": [1.0, 1.0, 1.0],
            "High": [1.0, 1.0, 1.0],
            "Low": [1.0, 1.0, 1.0],
            "Close": list(close),
            "Adj Close": list(adj),
            "Volume": [10, 20, 30],
            "Dividends": list(dividends),
            "Stock Splits": [0.0, 0.0, 0.0],
        },
        index=index,
    )


class FakeTicker:
    """Ticker falso: `history` devuelve la tabla o lanza el error configurado."""

    def __init__(self, module, symbol, session=None):
        self.module = module
        self.symbol = symbol
        self.session = session

    def history(self, **kwargs):
        self.module.calls.append((self.symbol, kwargs))
        result = self.module.config.get(self.symbol)
        if isinstance(result, Exception):
            raise result
        return result


class FakeYF:
    """Módulo yfinance falso: tablas por símbolo y registro de llamadas."""

    def __init__(self, config):
        self.config = config
        self.calls = []
        self.tickers = []

    def Ticker(self, symbol, session=None):  # noqa: N802 (mismo nombre que yfinance)
        ticker = FakeTicker(self, symbol, session)
        self.tickers.append(ticker)
        return ticker

    def set_tz_cache_location(self, path):
        pass


def make_provider(tmp_path, config):
    fake = FakeYF(config)
    provider = YahooProvider(tz_cache_dir=tmp_path / "tz", yf_module=fake, session=SESSION)
    return provider, fake


# --- Interfaz ---


def test_cumple_las_dos_interfaces(tmp_path):
    provider, _ = make_provider(tmp_path, {})
    assert isinstance(provider, HistoryProvider)
    assert isinstance(provider, MarketDataProvider)


# --- Llamada a yfinance ---


def test_llama_a_history_con_los_parametros_acordados(tmp_path):
    provider, fake = make_provider(tmp_path, {"SPY": history_frame()})
    provider.get_history("SPY", START, END)
    assert fake.calls == [
        (
            "SPY",
            {"start": START, "end": END, "interval": "1d", "auto_adjust": False, "actions": True},
        )
    ]


def test_usa_la_sesion_con_timeout(tmp_path):
    provider, fake = make_provider(tmp_path, {"SPY": history_frame()})
    provider.get_history("SPY", START, END)
    assert fake.tickers[0].session is SESSION


# --- Conversión ---


def test_convierte_la_tabla_a_price_history(tmp_path):
    provider, _ = make_provider(tmp_path, {"SPY": history_frame()})
    history = provider.get_history("SPY", START, END)
    assert isinstance(history, PriceHistory)
    assert history.ticker == "SPY"
    assert history.dates == ("2026-11-17", "2026-11-18", "2026-11-19")
    assert history.close == (100.0, 101.0, 102.0)
    assert history.adj_close == (99.0, 100.5, 102.0)
    assert all(type(v) is float for v in history.close + history.adj_close)
    # Solo los dividendos > 0.
    assert history.dividends == (("2026-11-18", 0.5),)
    assert history.source == "live"


def test_nan_se_conserva_como_nan_para_que_lo_limpie_el_servicio(tmp_path):
    frame = history_frame(close=(100.0, float("nan"), 102.0), dividends=(float("nan"), 0.0, -1.0))
    provider, _ = make_provider(tmp_path, {"SPY": frame})
    history = provider.get_history("SPY", START, END)
    assert math.isnan(history.close[1])
    assert history.dividends == ()


def test_sin_columna_adj_close_usa_close(tmp_path):
    frame = history_frame().drop(columns=["Adj Close", "Dividends"])
    provider, _ = make_provider(tmp_path, {"^GSPC": frame})
    history = provider.get_history("^GSPC", START, END)
    assert history.adj_close == history.close
    assert history.dividends == ()


def test_irx_llega_en_porcentaje_sin_convertir(tmp_path):
    frame = history_frame(close=(4.12, 4.1, 4.08), adj=(4.12, 4.1, 4.08), dividends=(0, 0, 0))
    provider, _ = make_provider(tmp_path, {"^IRX": frame})
    history = provider.get_history("^IRX", START, END)
    assert history.close == (4.12, 4.1, 4.08)


# --- Errores ---


def test_tabla_vacia_es_respuesta_vacia(tmp_path):
    provider, _ = make_provider(tmp_path, {"SPY": history_frame().iloc[0:0]})
    with pytest.raises(EmptyDataError):
        provider.get_history("SPY", START, END)


def test_sin_tabla_es_respuesta_vacia(tmp_path):
    provider, _ = make_provider(tmp_path, {"SPY": None})
    with pytest.raises(EmptyDataError):
        provider.get_history("SPY", START, END)


def test_sin_columna_close_es_respuesta_vacia(tmp_path):
    provider, _ = make_provider(tmp_path, {"SPY": history_frame().drop(columns=["Close"])})
    with pytest.raises(EmptyDataError):
        provider.get_history("SPY", START, END)


class FakeYFRateLimitError(Exception):
    """Imita yfinance.exceptions.YFRateLimitError (mismo nombre de clase)."""


FakeYFRateLimitError.__name__ = "YFRateLimitError"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ConnectionError("sin red"), NetworkError),
        (TimeoutError("timeout"), NetworkError),
        (RuntimeError("red bloqueada en tests: use LIVE_DATA=1"), NetworkError),
        (FakeYFRateLimitError("Too Many Requests"), RateLimitError),
        (KeyError("Close"), EmptyDataError),
    ],
)
def test_errores_se_traducen(tmp_path, error, expected):
    provider, _ = make_provider(tmp_path, {"SPY": error})
    with pytest.raises(expected) as info:
        provider.get_history("SPY", START, END)
    assert info.value.message


# --- Sin pandas ---


def test_funciona_sin_pandas_con_una_tabla_minima():
    """En un proceso nuevo, con pandas bloqueado, la conversión funciona."""
    code = (
        "import sys, importlib.abc\n"
        "from datetime import date\n"
        "class Block(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in ('yfinance', 'pandas'):\n"
        "            raise ImportError('bloqueado: ' + name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Block())\n"
        "from datos.yahoo import YahooProvider\n"
        "class Column:\n"
        "    def __init__(self, values): self.values = values\n"
        "    def tolist(self): return list(self.values)\n"
        "class Table:\n"
        "    empty = False\n"
        "    index = [date(2026, 11, 18), date(2026, 11, 19)]\n"
        "    columns = ['Close', 'Dividends']\n"
        "    def __getitem__(self, name):\n"
        "        return Column({'Close': [10.0, 11.0], 'Dividends': [0.0, 0.2]}[name])\n"
        "class Ticker:\n"
        "    def __init__(self, symbol, session=None): pass\n"
        "    def history(self, **kwargs): return Table()\n"
        "class YF:\n"
        "    Ticker = Ticker\n"
        "    def set_tz_cache_location(self, path): pass\n"
        "import tempfile\n"
        "p = YahooProvider(tz_cache_dir=tempfile.mkdtemp(), yf_module=YF(), session=object())\n"
        "h = p.get_history('SPY', date(2026, 11, 1), date(2026, 11, 21))\n"
        "assert h.dates == ('2026-11-18', '2026-11-19'), h.dates\n"
        "assert h.adj_close == (10.0, 11.0)\n"
        "assert h.dividends == (('2026-11-19', 0.2),)\n"
        "assert 'pandas' not in sys.modules\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "ok"
