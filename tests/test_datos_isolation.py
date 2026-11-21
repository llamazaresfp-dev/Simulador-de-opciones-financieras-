"""Aislamiento de importaciones (AC-C1-13).

Se comprueba en un proceso NUEVO (subproceso), porque en el proceso de
pytest otras pruebas ya pueden haber importado yfinance o pandas.
- `import opciones, datos` no carga yfinance, pandas ni streamlit.
- `import datos` funciona aunque yfinance no esté instalado (se simula
  bloqueando su importación con un "finder").

Etapa C2 (bloque 8, AC-C2-16/17):
- `import datos` y los módulos del histórico no cargan yfinance ni pandas.
- `opciones.backtest` y `opciones.calibration` no cargan streamlit,
  pandas, yfinance, curl_cffi ni `datos`, y funcionan sin pandas/yfinance.
- `requirements.txt` sigue con las mismas 7 dependencias.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(code):
    """Ejecuta `code` con el Python actual desde la raíz del repo."""
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_import_opciones_y_datos_sin_yfinance_ni_pandas():
    code = (
        "import sys\n"
        "import opciones, datos\n"
        "import datos.yahoo\n"
        "heavy = [m for m in ('yfinance', 'pandas', 'streamlit', 'curl_cffi') if m in sys.modules]\n"
        "print('cargados:', heavy)\n"
        "assert heavy == [], heavy\n"
        "assert hasattr(datos, 'YahooProvider')\n"
    )
    result = _run(code)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "cargados: []" in result.stdout


def test_import_datos_con_yfinance_bloqueado():
    code = (
        "import sys\n"
        "import importlib.abc\n"
        "class Block(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in ('yfinance', 'pandas'):\n"
        "            raise ImportError('bloqueado: ' + name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Block())\n"
        "import datos\n"
        "from datos import FakeProvider, YahooProvider, load_snapshot\n"
        "try:\n"
        "    YahooProvider()\n"
        "except ImportError as error:\n"
        "    print('constructor:', error)\n"
        "else:\n"
        "    raise AssertionError('YahooProvider() debía necesitar yfinance')\n"
        "print('ok')\n"
    )
    result = _run(code)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "constructor: bloqueado: yfinance" in result.stdout
    assert result.stdout.strip().endswith("ok")


# --- Etapa C2 ---

# Bloqueador de importaciones (pandas y yfinance) para los subprocesos.
BLOCK_PANDAS_YFINANCE = (
    "import sys\n"
    "import importlib.abc\n"
    "class Block(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name.split('.')[0] in ('yfinance', 'pandas'):\n"
    "            raise ImportError('bloqueado: ' + name)\n"
    "        return None\n"
    "sys.meta_path.insert(0, Block())\n"
)


def _require_engine_modules():
    """Omite la prueba si los módulos nuevos del motor aún no existen."""
    for name in ("opciones.backtest", "opciones.calibration"):
        if importlib.util.find_spec(name) is None:
            pytest.skip(f"{name} todavía no existe")


def test_datos_e_historico_sin_yfinance_ni_pandas():
    code = (
        "import sys\n"
        "import datos\n"
        "import datos.history_cache, datos.history_service\n"
        "from datos import load_history, HistoryProvider, PriceHistory\n"
        "heavy = [m for m in ('yfinance', 'pandas', 'streamlit', 'curl_cffi') if m in sys.modules]\n"
        "print('cargados:', heavy)\n"
        "assert heavy == [], heavy\n"
    )
    result = _run(code)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "cargados: []" in result.stdout


def test_motor_nuevo_no_carga_ui_ni_datos():
    _require_engine_modules()
    code = (
        "import sys\n"
        "import opciones.backtest, opciones.calibration\n"
        "bad = [m for m in ('streamlit', 'pandas', 'yfinance', 'curl_cffi', 'datos')\n"
        "       if m in sys.modules]\n"
        "print('cargados:', bad)\n"
        "assert bad == [], bad\n"
    )
    result = _run(code)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "cargados: []" in result.stdout


def test_motor_nuevo_funciona_con_pandas_y_yfinance_bloqueados():
    _require_engine_modules()
    code = BLOCK_PANDAS_YFINANCE + (
        "from opciones.backtest import run_backtest\n"
        "from opciones.calibration import calibration_bins\n"
        "assert callable(run_backtest) and callable(calibration_bins)\n"
        "print('ok')\n"
    )
    result = _run(code)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().endswith("ok")


def test_requirements_sin_dependencias_nuevas():
    lines = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").split()
    names = [line.split("==")[0] for line in lines]
    assert names == ["numpy", "scipy", "plotly", "streamlit", "pytest", "yfinance", "pandas"]
