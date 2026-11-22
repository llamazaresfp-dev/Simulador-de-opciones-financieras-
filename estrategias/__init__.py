"""Estrategias guardadas y comparación (Etapa D).

Paquete aparte del motor: puede usar `opciones`, pero el motor no lo
conoce. No importa Streamlit ni hace nada de red.

- serialize: estrategia <-> JSON versionado y validación estricta de
  archivos (nunca lanza).
- store: carpeta `.estrategias/` (un JSON por estrategia, escritura
  atómica). Se usa como `from estrategias import store`.
- compare: malla común, prima neta y filas de la comparación. Se usa
  como `from estrategias import compare`.
"""

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

__all__ = [
    "BOUNDS",
    "MAX_BYTES",
    "MAX_LEGS",
    "MAX_NAME_LEN",
    "SCHEMA_VERSION",
    "SavedLeg",
    "SavedStrategy",
    "dumps_strategy",
    "parse_strategy_json",
    "prepare_document",
    "saved_leg_to_engine",
    "strategy_to_dict",
]
