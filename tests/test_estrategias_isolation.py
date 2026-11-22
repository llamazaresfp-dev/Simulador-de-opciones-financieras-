"""Aislamiento del paquete estrategias/ (Etapa D, bloque 4; AC-D-13).

- `import estrategias` (y sus módulos) no carga streamlit, pandas,
  yfinance, curl_cffi ni `datos`, y funciona sin pandas ni yfinance.
- El motor `opciones` y `datos` no importan `estrategias` (se comprueba
  recorriendo el código con `ast`, no buscando texto: catalog.py habla
  de "estrategias clásicas" en un comentario).
- estrategias/ solo usa la biblioteca estándar, `opciones` y numpy.
- requirements.txt sigue con las mismas 7 dependencias.

Las importaciones se comprueban en un proceso NUEVO (subproceso), porque
en el proceso de pytest otras pruebas ya han importado streamlit o pandas.
"""

import ast
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


def _imported_modules(path: Path) -> list[str]:
    """Nombres de módulo de cada Import/ImportFrom absoluto de un archivo."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
    return modules


def test_import_estrategias_no_carga_nada_pesado():
    code = (
        "import sys\n"
        "import estrategias, estrategias.serialize, estrategias.store, estrategias.compare\n"
        "heavy = [m for m in ('streamlit', 'pandas', 'yfinance', 'curl_cffi', 'datos') if m in sys.modules]\n"
        "print('cargados:', heavy)\n"
        "assert heavy == [], heavy\n"
    )
    result = _run(code)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "cargados: []" in result.stdout


def test_import_opciones_y_datos_no_carga_estrategias():
    code = (
        "import sys\n"
        "import opciones, datos\n"
        "loaded = [m for m in sys.modules if m == 'estrategias' or m.startswith('estrategias.')]\n"
        "print('cargados:', loaded)\n"
        "assert loaded == [], loaded\n"
    )
    result = _run(code)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "cargados: []" in result.stdout


def test_motor_y_datos_no_importan_estrategias():
    files = sorted((REPO_ROOT / "opciones").glob("*.py")) + sorted((REPO_ROOT / "datos").glob("*.py"))
    assert len(files) > 10
    all_modules = []
    for path in files:
        modules = _imported_modules(path)
        all_modules.extend(modules)
        bad = [m for m in modules if m == "estrategias" or m.startswith("estrategias.")]
        assert bad == [], f"{path.name} importa {bad}"
    # Sanidad: el recorrido sí encuentra importaciones conocidas (no pasa en vacío).
    assert "numpy" in all_modules
    assert "opciones.models" in all_modules


def test_estrategias_funciona_sin_streamlit_pandas_ni_yfinance():
    code = (
        "import sys\n"
        "import importlib.abc\n"
        "class Block(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in ('streamlit', 'pandas', 'yfinance'):\n"
        "            raise ImportError('bloqueado: ' + name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Block())\n"
        "import estrategias.compare, estrategias.store, estrategias.serialize\n"
        "from opciones import Leg, Market, CommissionSettings, SimulationSettings\n"
        "result = estrategias.compare.compare_strategies(\n"
        "    [('Call', [Leg('call', 1, 1.0, 100.0, 2.5)])],\n"
        "    Market('Acción', 100.0, 0.25, 45, 0.04, 0.0, 'black_scholes'),\n"
        "    CommissionSettings(), SimulationSettings())\n"
        "assert len(result.rows) == 1\n"
        "print('ok')\n"
    )
    result = _run(code)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().endswith("ok")


def test_requirements_sin_cambios():
    lines = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").split()
    assert lines == [
        "numpy==2.5.5",
        "scipy==1.18.1",
        "plotly==7.1.0",
        "streamlit==1.67.0",
        "pytest==9.2.0",
        "yfinance==1.8.0",
        "pandas==3.1.1",
    ]


def test_estrategias_solo_usa_biblioteca_estandar_opciones_y_numpy():
    files = sorted((REPO_ROOT / "estrategias").glob("*.py"))
    assert {path.name for path in files} >= {"__init__.py", "serialize.py", "store.py", "compare.py"}
    allowed_third_party = {"numpy", "opciones", "estrategias"}
    for path in files:
        for module in _imported_modules(path):
            top = module.split(".")[0]
            assert top in sys.stdlib_module_names or top in allowed_third_party, (
                f"{path.name} importa {module}"
            )
