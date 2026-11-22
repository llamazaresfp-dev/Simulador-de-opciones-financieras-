"""Tests de estrategias/store.py (Etapa D, bloque 2; AC-D-3, AC-D-4).

Siempre en carpetas temporales (`tmp_path`). Además, la fixture autouse
de `tests/conftest.py` redirige la carpeta por defecto a una temporal,
así que ningún test toca la carpeta real `.estrategias/`.
"""

import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from estrategias import store
from estrategias.serialize import MAX_BYTES, dumps_strategy, parse_strategy_json, strategy_to_dict
from estrategias.store import (
    MAX_STORED,
    SaveResult,
    StoredStrategy,
    delete_strategy,
    list_saved,
    read_strategy,
    save_document,
    slugify,
    strategy_path,
)
from opciones import CommissionSettings, Market

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKET = Market("Acción", 100.0, 0.25, 45, 0.04, 0.01, "binomial")
SAVED_AT = "2026-11-20T10:30:00-05:00"
SLUG_PATTERN = re.compile(r"^[a-z0-9_-]{1,60}$")


def make_raw(name="Mi call", price=3.33):
    """Bytes de un documento válido con el nombre dado."""
    legs = [{
        "id": 0, "kind": "call", "side": 1, "quantity": 1.0, "strike": 105.0,
        "price": price, "premium_manual": True, "premium_source": None,
        "bid": None, "ask": None, "iv_yahoo": None, "expiry": None,
    }]
    return dumps_strategy(strategy_to_dict(legs, MARKET, CommissionSettings(), name, SAVED_AT))


def json_files(directory):
    return sorted(p.name for p in Path(directory).iterdir())


# --- slugify ---


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Iron Condor SPY", "iron-condor-spy"),
        ("Opción cubierta ñandú", "opcion-cubierta-nandu"),
        ("Call $100 @ 5%!", "call-100-5"),
        ("../../x", "x"),
        ("..\\x", "x"),
        (".oculto", "oculto"),
        ("", "estrategia"),
        ("   ", "estrategia"),
        ("¿?¡!", "estrategia"),
        ("mi_estrategia-1", "mi_estrategia-1"),
    ],
)
def test_slugify_casos(name, expected):
    assert slugify(name) == expected


def test_slugify_largo_recortado():
    slug = slugify("a" * 200)
    assert len(slug) <= 60
    assert slug == "a" * 60


def test_slugify_propiedad_300_nombres():
    rng = random.Random(7)
    alphabet = "abcXYZ áéñü.-_/\\:*?\"<>|\u0000\n🙂0123456789"
    for _ in range(300):
        name = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 120)))
        slug = slugify(name)
        assert SLUG_PATTERN.match(slug), (name, slug)
        assert not slug.startswith(".")


# --- strategy_path ---


def test_strategy_path_valido(tmp_path):
    assert strategy_path("mi-call", tmp_path) == tmp_path / "mi-call.json"


@pytest.mark.parametrize(
    "slug",
    ["", ".", "..", "a/b", "A", "/etc/passwd", "../x", "a.b", "x" * 61, "a\u0000b", "abc\n", None, 5],
)
def test_strategy_path_invalido(tmp_path, slug):
    assert strategy_path(slug, tmp_path) is None


def test_strategy_path_enlace_que_sale_de_la_carpeta(tmp_path):
    folder = tmp_path / "carpeta"
    folder.mkdir()
    outside = tmp_path / "fuera.json"
    outside.write_bytes(make_raw())
    (folder / "malo.json").symlink_to(outside)
    assert strategy_path("malo", folder) is None


# --- save_document ---


def test_guardar_crea_carpeta_y_escribe_los_bytes_exactos(tmp_path):
    folder = tmp_path / "nueva" / "carpeta"
    raw = make_raw("Iron Condor SPY")
    result = save_document(raw, folder)
    assert isinstance(result, SaveResult)
    assert result.ok and result.slug == "iron-condor-spy" and not result.exists
    assert result.message
    assert (folder / "iron-condor-spy.json").read_bytes() == raw
    assert json_files(folder) == ["iron-condor-spy.json"]  # sin temporales


def test_fallo_de_replace_deja_el_archivo_viejo(tmp_path, monkeypatch):
    old = make_raw("A", price=1.0)
    assert save_document(old, tmp_path).ok

    def broken_replace(*args, **kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr(store.os, "replace", broken_replace)
    result = save_document(make_raw("A", price=2.0), tmp_path, overwrite=True)
    assert not result.ok and result.message
    assert (tmp_path / "a.json").read_bytes() == old
    assert json_files(tmp_path) == ["a.json"]


def test_fallo_al_guardar_nuevo_sin_temporales(tmp_path, monkeypatch):
    monkeypatch.setattr(store.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    result = save_document(make_raw("B"), tmp_path)
    assert not result.ok
    assert json_files(tmp_path) == []


def test_mismo_nombre_sin_sobrescribir(tmp_path):
    first = make_raw("Mi call", price=1.0)
    assert save_document(first, tmp_path).ok
    result = save_document(make_raw("Mi call", price=2.0), tmp_path)
    assert not result.ok and result.exists and result.slug == "mi-call"
    assert result.message
    assert (tmp_path / "mi-call.json").read_bytes() == first


def test_mismo_nombre_con_sobrescribir(tmp_path):
    assert save_document(make_raw("Mi call", price=1.0), tmp_path).ok
    second = make_raw("Mi call", price=2.0)
    result = save_document(second, tmp_path, overwrite=True)
    assert result.ok and result.slug == "mi-call"
    assert (tmp_path / "mi-call.json").read_bytes() == second
    assert json_files(tmp_path) == ["mi-call.json"]


def test_colision_de_slug_con_nombres_distintos(tmp_path):
    assert save_document(make_raw("A b"), tmp_path).slug == "a-b"
    assert save_document(make_raw("a-b"), tmp_path).slug == "a-b-2"
    assert save_document(make_raw("A  B"), tmp_path).slug == "a-b-3"
    # Sobrescribir el segundo escribe en -2.
    new = make_raw("a-b", price=9.0)
    result = save_document(new, tmp_path, overwrite=True)
    assert result.ok and result.slug == "a-b-2"
    assert (tmp_path / "a-b-2.json").read_bytes() == new
    assert json_files(tmp_path) == ["a-b-2.json", "a-b-3.json", "a-b.json"]


def test_colision_con_hueco_no_duplica_nombre(tmp_path):
    assert save_document(make_raw("A b"), tmp_path).slug == "a-b"
    assert save_document(make_raw("a-b"), tmp_path).slug == "a-b-2"
    os.remove(tmp_path / "a-b.json")
    result = save_document(make_raw("a-b"), tmp_path)
    assert not result.ok and result.exists and result.slug == "a-b-2"


def test_nombre_de_60_con_sufijo(tmp_path):
    name_a = "a" * 60
    name_b = "A" * 60
    assert save_document(make_raw(name_a), tmp_path).slug == "a" * 60
    result = save_document(make_raw(name_b), tmp_path)
    assert result.ok
    assert len(result.slug) <= 60 and result.slug.endswith("-2")


def test_limite_de_100(tmp_path):
    for i in range(MAX_STORED):
        (tmp_path / f"s{i}.json").write_bytes(make_raw(f"s{i}"))
    result = save_document(make_raw("nueva"), tmp_path)
    assert not result.ok and "100" in result.message
    assert not (tmp_path / "nueva.json").exists()
    # Sobrescribir una existente sí se permite.
    assert save_document(make_raw("s5", price=7.0), tmp_path, overwrite=True).ok


def test_documento_invalido_no_escribe(tmp_path):
    folder = tmp_path / "x"
    result = save_document(b"basura", folder)
    assert not result.ok and result.message
    assert not folder.exists()


def test_nombre_con_ruta_no_sale_de_la_carpeta(tmp_path):
    folder = tmp_path / "carpeta"
    result = save_document(make_raw("../../x"), folder)
    assert result.ok and result.slug == "x"
    assert json_files(folder) == ["x.json"]
    assert json_files(tmp_path) == ["carpeta"]


# --- list_saved ---


def test_carpeta_inexistente_no_se_crea(tmp_path):
    folder = tmp_path / "no-existe"
    assert list_saved(folder) == ([], [])
    assert not folder.exists()


def test_lista_ordenada_sin_distinguir_mayusculas(tmp_path):
    for name in ("beta", "Alfa", "gamma", "alfa 2"):
        assert save_document(make_raw(name), tmp_path).ok
    items, warnings = list_saved(tmp_path)
    assert warnings == []
    assert [item.strategy.name for item in items] == ["Alfa", "alfa 2", "beta", "gamma"]
    assert all(isinstance(item, StoredStrategy) for item in items)
    for item in items:
        assert item.raw == (tmp_path / f"{item.slug}.json").read_bytes()


def test_archivos_malos_se_omiten_con_aviso(tmp_path):
    assert save_document(make_raw("buena"), tmp_path).ok
    (tmp_path / "corrupto.json").write_bytes(b"{no es json")
    (tmp_path / "grande.json").write_bytes(b" " * (MAX_BYTES + 1))
    (tmp_path / "ajeno.json").write_bytes(b'{"hola": 1}')
    (tmp_path / "x.json").mkdir()
    (tmp_path / "notas.txt").write_text("ignorado")
    (tmp_path / ".oculto.json").write_bytes(make_raw("oculta"))
    items, warnings = list_saved(tmp_path)
    assert [item.slug for item in items] == ["buena"]
    assert len(warnings) == 4
    for file_name in ("corrupto.json", "grande.json", "ajeno.json", "x.json"):
        assert sum(f"«{file_name}»" in w for w in warnings) == 1
    assert all(w.startswith("No se pudo leer") for w in warnings)


def test_enlace_simbolico_se_omite(tmp_path):
    folder = tmp_path / "carpeta"
    folder.mkdir()
    target = folder / "real.json"
    target.write_bytes(make_raw("real"))
    (folder / "enlace.json").symlink_to(target)
    items, warnings = list_saved(folder)
    assert [item.slug for item in items] == ["real"]
    assert len(warnings) == 1 and "enlace.json" in warnings[0]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="sin FIFOs en este sistema")
def test_fifo_se_omite_sin_bloquear(tmp_path):
    os.mkfifo(tmp_path / "tuberia.json")
    items, warnings = list_saved(tmp_path)
    assert items == []
    assert len(warnings) == 1 and "tuberia.json" in warnings[0]
    stored, message = read_strategy("tuberia", tmp_path)
    assert stored is None and message


# --- read_strategy ---


def test_read_strategy(tmp_path):
    raw = make_raw("Mi call")
    assert save_document(raw, tmp_path).ok
    stored, message = read_strategy("mi-call", tmp_path)
    assert message is None
    assert stored.slug == "mi-call" and stored.raw == raw
    assert stored.strategy == parse_strategy_json(raw)[0]


@pytest.mark.parametrize("slug", ["no-existe", "../x", "A", ""])
def test_read_strategy_inexistente_o_invalido(tmp_path, slug):
    stored, message = read_strategy(slug, tmp_path)
    assert stored is None and isinstance(message, str) and message


def test_read_strategy_corrupto(tmp_path):
    (tmp_path / "roto.json").write_bytes(b"[1, 2")
    stored, message = read_strategy("roto", tmp_path)
    assert stored is None and message


# --- delete_strategy ---


def test_borrar(tmp_path):
    assert save_document(make_raw("Mi call"), tmp_path).ok
    assert delete_strategy("mi-call", tmp_path) == (True, None)
    assert json_files(tmp_path) == []


def test_borrar_inexistente(tmp_path):
    ok, message = delete_strategy("nada", tmp_path)
    assert not ok and message


def test_borrar_slug_invalido_no_toca_nada(tmp_path):
    folder = tmp_path / "carpeta"
    folder.mkdir()
    victim = tmp_path / "x.json"
    victim.write_bytes(make_raw("x"))
    ok, message = delete_strategy("../x", folder)
    assert not ok and message
    assert victim.exists()


def test_borrar_no_borra_directorios(tmp_path):
    (tmp_path / "dir.json").mkdir()
    ok, message = delete_strategy("dir", tmp_path)
    assert not ok and message
    assert (tmp_path / "dir.json").is_dir()


# --- Carpeta por defecto y fixture autouse (DD-6, E-2) ---


def test_carpeta_por_defecto_es_la_del_repo():
    # En un proceso nuevo (sin la fixture) el valor es <raíz>/.estrategias.
    # Solo se imprime la ruta: no se crea ni se lee la carpeta.
    result = subprocess.run(
        [sys.executable, "-c", "import estrategias.store as s; print(s.DEFAULT_STRATEGIES_DIR)"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == REPO_ROOT / ".estrategias"


def test_fixture_autouse_redirige_a_carpeta_temporal():
    current = store.DEFAULT_STRATEGIES_DIR
    assert current != REPO_ROOT / ".estrategias"
    assert REPO_ROOT not in current.parents


def test_sin_carpeta_usa_la_redirigida_en_cada_llamada():
    # E-2: directory=None lee el atributo del módulo en cada llamada.
    real_folder = REPO_ROOT / ".estrategias"
    existed_before = real_folder.exists()
    result = save_document(make_raw("Por defecto"))
    assert result.ok
    assert (store.DEFAULT_STRATEGIES_DIR / "por-defecto.json").exists()
    items, warnings = list_saved()
    assert [item.slug for item in items] == ["por-defecto"]
    assert read_strategy("por-defecto")[0] is not None
    assert delete_strategy("por-defecto") == (True, None)
    assert real_folder.exists() == existed_before


def test_cambiar_el_atributo_cambia_la_carpeta(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DEFAULT_STRATEGIES_DIR", tmp_path / "otra")
    assert save_document(make_raw("z")).ok
    assert (tmp_path / "otra" / "z.json").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git no disponible")
def test_gitignore_ignora_la_carpeta():
    result = subprocess.run(
        ["git", "check-ignore", "-v", ".estrategias/x.json"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    if result.returncode == 128:
        pytest.skip("no es un repositorio git")
    assert result.returncode == 0, result.stdout + result.stderr
    assert ".gitignore" in result.stdout and ".estrategias/" in result.stdout
