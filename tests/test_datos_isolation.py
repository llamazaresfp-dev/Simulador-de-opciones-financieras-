"""Aislamiento de importaciones (AC-C1-13).

Se comprueba en un proceso NUEVO (subproceso), porque en el proceso de
pytest otras pruebas ya pueden haber importado yfinance o pandas.
- `import opciones, datos` no carga yfinance, pandas ni streamlit.
- `import datos` funciona aunque yfinance no esté instalado (se simula
  bloqueando su importación con un "finder").
"""

import subprocess
import sys
from pathlib import Path

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
