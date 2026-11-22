"""Configuración común de los tests.

Bloqueo de red (Etapa C1, bloque 3a, AC-C1-14): ningún test puede abrir
conexiones de red por error. Se parchean `socket.socket.connect` y
`socket.getaddrinfo` para que lancen un error claro. Para ejecutar a
propósito las pruebas contra la red real: `LIVE_DATA=1`.

No se parchea `socket.socketpair` ni nada de `asyncio`: los usan asyncio
y Streamlit (AppTest) para comunicarse dentro del propio proceso.
"""

import os
import socket

import pytest

NETWORK_BLOCKED_MESSAGE = "red bloqueada en tests: use LIVE_DATA=1"


def _blocked(*args, **kwargs):
    """Sustituto de las funciones de red: siempre lanza el error claro."""
    raise RuntimeError(NETWORK_BLOCKED_MESSAGE)


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """Bloquea la red en cada test, salvo con LIVE_DATA=1."""
    if os.environ.get("LIVE_DATA") == "1":
        return
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)


@pytest.fixture(autouse=True)
def redirect_strategies_dir(monkeypatch, tmp_path_factory):
    """Etapa D (DD-6): ningún test toca la carpeta real `.estrategias/`.

    La carpeta por defecto de estrategias.store se redirige a una ruta
    temporal (que no se crea hasta que algo se guarda). store.py lee
    este atributo en cada llamada, así que el cambio llega a todo:
    también a los tests de la app que no inyectan su propia carpeta.
    """
    import estrategias.store

    folder = tmp_path_factory.mktemp("estrategias") / ".estrategias"
    monkeypatch.setattr(estrategias.store, "DEFAULT_STRATEGIES_DIR", folder)
