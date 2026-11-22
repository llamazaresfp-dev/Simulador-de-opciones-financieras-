"""Carpeta de estrategias guardadas (Etapa D, bloque 2).

Un archivo JSON por estrategia dentro de una carpeta (por defecto
`.estrategias/` en la raíz del repositorio, ignorada por git):

- Nombre de archivo seguro ("slug"): solo `a-z`, `0-9`, `_` y `-`, como
  máximo 60 caracteres. Un nombre como `../../x` nunca sale de la carpeta.
- Escritura atómica: se escribe un temporal en la misma carpeta y se
  renombra de un golpe; nunca queda un archivo a medias.
- Ninguna función lanza excepciones: devuelven un resultado y, si algo
  falla, un mensaje en español.

La carpeta por defecto se lee del atributo del módulo EN CADA LLAMADA
(`DEFAULT_STRATEGIES_DIR`), así los tests pueden redirigirla.
"""

import os
import re
import stat
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from estrategias.serialize import MAX_BYTES, SavedStrategy, parse_strategy_json

# Carpeta por defecto: `.estrategias/` en la raíz del repositorio,
# calculada desde la ruta de este archivo (estrategias/store.py -> raíz).
DEFAULT_STRATEGIES_DIR = Path(__file__).resolve().parent.parent / ".estrategias"

MAX_STORED = 100
MAX_SLUG_LEN = 60
MAX_SUFFIX = 99
DEFAULT_SLUG = "estrategia"

_SLUG_RE = re.compile(r"[a-z0-9_-]{1,60}")

MSG_BAD_SLUG = "El nombre de archivo de la estrategia no es válido."
MSG_NOT_FOUND = "No existe la estrategia «{slug}»."
MSG_NOT_REGULAR = "«{file}» no es un archivo normal."
MSG_READ_FAILED = "No se pudo leer «{file}»: {reason}"
MSG_INVALID_DOC = "No se pudo guardar: {reason}"
MSG_EXISTS = "Ya existe una estrategia llamada «{name}». Marca «sobrescribir» para reemplazarla."
MSG_FULL = "Ya hay 100 estrategias guardadas: borra alguna antes de guardar otra."
MSG_TOO_MANY_SIMILAR = "Hay demasiadas estrategias con nombres parecidos a «{name}»."
MSG_WRITE_FAILED = "No se pudo guardar la estrategia en el disco: {reason}"
MSG_SAVED = "Estrategia «{name}» guardada."
MSG_DELETE_FAILED = "No se pudo borrar la estrategia: {reason}"


@dataclass(frozen=True)
class StoredStrategy:
    """Una estrategia leída de la carpeta.

    - slug: nombre del archivo sin `.json`.
    - strategy: la estrategia ya validada.
    - raw: los bytes exactos del archivo (para descargarlo tal cual).
    """

    slug: str
    strategy: SavedStrategy
    raw: bytes


@dataclass(frozen=True)
class SaveResult:
    """Resultado de save_document.

    - ok: True si se escribió el archivo.
    - slug: archivo usado (o el que ya existía con ese nombre), o None.
    - message: texto en español para mostrar.
    - exists: True si ya había una estrategia con ese nombre y no se
      pidió sobrescribir.
    """

    ok: bool
    slug: str | None
    message: str
    exists: bool


def _folder(directory) -> Path:
    """Carpeta a usar: la dada o la por defecto (leída ahora, no al importar)."""
    if directory is None:
        return Path(DEFAULT_STRATEGIES_DIR)
    return Path(directory)


def slugify(name) -> str:
    """Nombre -> slug seguro: minúsculas sin acentos, solo a-z, 0-9, _ y -.

    "Iron Condor SPY" -> "iron-condor-spy". Vacío -> "estrategia".
    """
    text = unicodedata.normalize("NFKD", str(name))
    # Quitamos las marcas de acento que deja NFKD (á -> a + ´).
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text).strip("-")
    text = text[:MAX_SLUG_LEN].strip("-")
    return text or DEFAULT_SLUG


def strategy_path(slug, directory=None) -> Path | None:
    """Ruta del archivo de un slug, o None si el slug no vale o la ruta saldría de la carpeta."""
    if not isinstance(slug, str) or not _SLUG_RE.fullmatch(slug):
        return None
    folder = _folder(directory)
    path = folder / f"{slug}.json"
    try:
        # resolve() sigue enlaces simbólicos: uno que apunte fuera se rechaza.
        if path.resolve().parent != folder.resolve():
            return None
    except (OSError, RuntimeError):
        return None
    return path


def _is_regular_file(path: Path) -> bool:
    """True solo para archivos normales (no enlaces, carpetas ni tuberías)."""
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


def _read_file(path: Path, slug: str) -> tuple[StoredStrategy | None, str | None]:
    """Lee y valida un archivo ya comprobado como normal."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_BYTES + 1)
    except OSError as error:
        return None, MSG_READ_FAILED.format(file=path.name, reason=error.strerror or "error de disco")
    strategy, errors = parse_strategy_json(raw)
    if strategy is None:
        return None, MSG_READ_FAILED.format(file=path.name, reason=errors[0])
    return StoredStrategy(slug, strategy, raw), None


def list_saved(directory=None) -> tuple[list[StoredStrategy], list[str]]:
    """Estrategias de la carpeta, ordenadas por nombre (sin distinguir mayúsculas).

    Devuelve (estrategias, avisos). Un archivo que no se puede leer se
    omite con un aviso. Si la carpeta no existe: ([], []) y NO se crea.
    """
    folder = _folder(directory)
    try:
        if not folder.is_dir():
            return [], []
        names = sorted(os.listdir(folder))
    except OSError:
        return [], []

    items = []
    warnings = []
    for file_name in names:
        # Solo archivos .json visibles (los temporales empiezan por punto).
        if not file_name.endswith(".json") or file_name.startswith("."):
            continue
        slug = file_name[: -len(".json")]
        path = folder / file_name
        if not _SLUG_RE.fullmatch(slug):
            warnings.append(MSG_READ_FAILED.format(file=file_name, reason="nombre de archivo no válido."))
            continue
        if not _is_regular_file(path):
            warnings.append(MSG_READ_FAILED.format(file=file_name, reason="no es un archivo normal."))
            continue
        stored, warning = _read_file(path, slug)
        if stored is None:
            warnings.append(warning)
        else:
            items.append(stored)

    items.sort(key=lambda item: (item.strategy.name.casefold(), item.slug))
    return items, warnings


def read_strategy(slug, directory=None) -> tuple[StoredStrategy | None, str | None]:
    """Lee una estrategia por su slug. Devuelve (estrategia, None) o (None, mensaje)."""
    path = strategy_path(slug, directory)
    if path is None:
        return None, MSG_BAD_SLUG
    if not path.exists() and not path.is_symlink():
        return None, MSG_NOT_FOUND.format(slug=slug)
    if not _is_regular_file(path):
        return None, MSG_NOT_REGULAR.format(file=path.name)
    return _read_file(path, slug)


def _candidate_slugs(base: str) -> list[str]:
    """base, base-2, ..., base-99 (la base se recorta a 57 para no pasar de 60)."""
    candidates = [base]
    for number in range(2, MAX_SUFFIX + 1):
        candidates.append(f"{base[:57]}-{number}")
    return candidates


def _count_json_files(folder: Path) -> int:
    """Número de archivos .json visibles en la carpeta (0 si no existe)."""
    try:
        return sum(1 for name in os.listdir(folder) if name.endswith(".json") and not name.startswith("."))
    except OSError:
        return 0


def _atomic_write(path: Path, raw: bytes) -> None:
    """Escribe `raw` en `path` de forma atómica (temporal + os.replace).

    Si algo falla se borra el temporal, el archivo viejo queda intacto
    y la excepción sigue hacia arriba.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(dir=path.parent, prefix=".", suffix=".tmp", delete=False)
    try:
        with tmp:
            tmp.write(raw)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp.name, path)
    except BaseException:
        try:
            os.remove(tmp.name)
        except OSError:
            pass
        raise


def save_document(raw: bytes, directory=None, overwrite=False) -> SaveResult:
    """Guarda los bytes de un documento (los mismos que se descargan, DD-4).

    - Se valida con parse_strategy_json; si no vale, no se escribe nada.
    - "Ya existe" = el mismo nombre exacto en algún archivo (DD-5): sin
      `overwrite` no se toca; con `overwrite` se reemplaza ese archivo.
    - Dos nombres distintos con el mismo slug: sufijos -2, -3, ...
    - Como máximo 100 estrategias (sobrescribir siempre se permite).
    """
    strategy, errors = parse_strategy_json(raw)
    if strategy is None:
        return SaveResult(False, None, MSG_INVALID_DOC.format(reason=errors[0]), False)

    folder = _folder(directory)
    name = strategy.name
    match = None
    first_free = None
    for slug in _candidate_slugs(slugify(name)):
        path = strategy_path(slug, folder)
        if path is None:
            continue
        if not path.exists() and not path.is_symlink():
            if first_free is None:
                first_free = slug
            continue
        stored, _ = read_strategy(slug, folder)
        if stored is not None and stored.strategy.name == name:
            match = slug
            break

    if match is not None:
        if not overwrite:
            return SaveResult(False, match, MSG_EXISTS.format(name=name), True)
        target = match
    else:
        if first_free is None:
            return SaveResult(False, None, MSG_TOO_MANY_SIMILAR.format(name=name), False)
        if _count_json_files(folder) >= MAX_STORED:
            return SaveResult(False, None, MSG_FULL, False)
        target = first_free

    try:
        _atomic_write(folder / f"{target}.json", bytes(raw))
    except Exception as error:
        reason = getattr(error, "strerror", None) or str(error) or "error de disco"
        return SaveResult(False, None, MSG_WRITE_FAILED.format(reason=reason), False)
    return SaveResult(True, target, MSG_SAVED.format(name=name), False)


def delete_strategy(slug, directory=None) -> tuple[bool, str | None]:
    """Borra el archivo de una estrategia. Devuelve (True, None) o (False, mensaje)."""
    path = strategy_path(slug, directory)
    if path is None:
        return False, MSG_BAD_SLUG
    if not _is_regular_file(path):
        return False, MSG_NOT_FOUND.format(slug=slug)
    try:
        os.remove(path)
    except OSError as error:
        return False, MSG_DELETE_FAILED.format(reason=error.strerror or "error de disco")
    return True, None
