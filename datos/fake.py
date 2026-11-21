"""Proveedor FALSO de datos de mercado, para pruebas sin Internet.

Cumple la misma interfaz que el proveedor de Yahoo (MarketDataProvider),
pero sus datos salen de las fixtures grabadas en `tests/fixtures/`.

Las fechas de vencimiento NO son fijas: se calculan desde el reloj que
se le pasa (`today + offset` días). Así las pruebas no caducan cuando
pasa el tiempo real.

También puede simular fallos:
- `fail_with`: TODAS las llamadas lanzan ese error (proveedor caído).
- `chain_errors`: solo la cadena de ciertos vencimientos falla
  ({17: RateLimitError} -> falla el vencimiento a 17 días).
- `dividend_error`: falla solo la consulta del dividend yield.

Guarda qué se le ha pedido (`called`, `chain_calls`) para que las
pruebas puedan comprobar, por ejemplo, que tras un 429 no se pide más.
"""

import copy
import json
from datetime import date, timedelta
from pathlib import Path

from datos.cache import market_today
from datos.errors import EmptyDataError
from datos.service import rate_from_percent

# Vencimientos por defecto, en días desde hoy. El de +150 queda fuera
# de la ventana 7–120 a propósito.
DEFAULT_OFFSETS = (10, 17, 45, 90, 150)

# Carpeta de las fixtures (raíz del repo / tests / fixtures).
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

# Qué fixture respalda cada ticker.
TICKER_FIXTURES = {"SPY": "spy", "AAPL": "aapl", "^SPX": "spx", "SPX": "spx"}

# Dividend yield (fracción) medido para cada fixture; None = sin dato.
FIXTURE_DIVIDEND_YIELDS = {"spy": 0.0079093, "aapl": 0.0030354}

# ^IRX medido al grabar (en porcentaje, como lo publica Yahoo).
DEFAULT_IRX_PERCENT = 4.122

# Valor centinela: "no se pasó este parámetro" (None sí es un valor válido).
_NOT_GIVEN = object()


def _load_fixture(name) -> dict:
    """Lee tests/fixtures/<name>.json."""
    with open(FIXTURES_DIR / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


def _raise(error):
    """Lanza `error`, sea una clase de error o un error ya creado."""
    if isinstance(error, type):
        raise error()
    raise error


class FakeProvider:
    """Proveedor de pruebas respaldado por fixtures.

    Parámetros (todos opcionales):
    - today: reloj (date o datetime con zona); por defecto la fecha de
      mercado actual. Las pruebas SIEMPRE lo fijan.
    - offsets: días desde `today` de cada vencimiento ofrecido.
    - fixture: nombre de la fixture que respalda TODOS los tickers; si no
      se da, se elige por ticker (SPY -> spy, AAPL -> aapl, ^SPX -> spx).
    - chain_fixtures: {offset: fixture} para que un vencimiento concreto
      use otras filas (p. ej. uno sin opciones líquidas).
    - spot: precio forzado; por defecto el de la fixture.
    - irx_percent: ^IRX en porcentaje (4.12 = 4,12 %).
    - dividend_yield: fracción o None; por defecto el medido de la fixture.
    - fail_with: error que lanzan todas las llamadas.
    - chain_errors: {offset: error} para fallos de cadenas concretas.
    - dividend_error: error al pedir el dividend yield.
    """

    def __init__(
        self,
        today=None,
        offsets=DEFAULT_OFFSETS,
        fixture=None,
        chain_fixtures=None,
        spot=None,
        irx_percent=DEFAULT_IRX_PERCENT,
        dividend_yield=_NOT_GIVEN,
        fail_with=None,
        chain_errors=None,
        dividend_error=None,
    ):
        self.today = market_today(today)
        self.offsets = tuple(offsets)
        self.fixture = fixture
        self.chain_fixtures = dict(chain_fixtures or {})
        self.spot = spot
        self.irx_percent = irx_percent
        self.dividend_yield = dividend_yield
        self.fail_with = fail_with
        self.chain_errors = dict(chain_errors or {})
        self.dividend_error = dividend_error
        # Registro de llamadas: nombres de método y vencimientos pedidos.
        self.called = []
        self.chain_calls = []

    # --- Ayudantes internos ---

    def _start(self, method):
        """Anota la llamada y, si el proveedor está "caído", falla."""
        self.called.append(method)
        if self.fail_with is not None:
            _raise(self.fail_with)

    def _fixture_name(self, ticker) -> str:
        """Fixture que respalda un ticker; EmptyDataError si no hay."""
        if self.fixture is not None:
            return self.fixture
        if ticker not in TICKER_FIXTURES:
            raise EmptyDataError()
        return TICKER_FIXTURES[ticker]

    def _offset_of(self, expiry) -> int:
        """Días desde `today` hasta un vencimiento ISO."""
        return (date.fromisoformat(expiry) - self.today).days

    # --- Interfaz MarketDataProvider ---

    def get_spot(self, ticker) -> float:
        """Precio del subyacente: el forzado o el de la fixture."""
        self._start("get_spot")
        data = _load_fixture(self._fixture_name(ticker))
        return self.spot if self.spot is not None else data["spot"]

    def get_expirations(self, ticker) -> list[str]:
        """Vencimientos ISO a `today + offset` días, en el orden de `offsets`."""
        self._start("get_expirations")
        self._fixture_name(ticker)
        return [(self.today + timedelta(days=o)).isoformat() for o in self.offsets]

    def get_chain(self, ticker, expiry) -> list[dict]:
        """Filas crudas de un vencimiento (copias: se pueden modificar)."""
        self._start("get_chain")
        self.chain_calls.append(expiry)
        offset = self._offset_of(expiry)
        if offset in self.chain_errors:
            _raise(self.chain_errors[offset])
        name = self.chain_fixtures.get(offset, self._fixture_name(ticker))
        return copy.deepcopy(_load_fixture(name)["rows"])

    def get_rate(self) -> float:
        """Tipo libre de riesgo en fracción (^IRX llega en porcentaje)."""
        self._start("get_rate")
        return rate_from_percent(self.irx_percent)

    def get_dividend_yield(self, ticker) -> float | None:
        """Dividend yield (fracción) o None si no hay dato."""
        self._start("get_dividend_yield")
        if self.dividend_error is not None:
            _raise(self.dividend_error)
        if self.dividend_yield is not _NOT_GIVEN:
            return self.dividend_yield
        return FIXTURE_DIVIDEND_YIELDS.get(self._fixture_name(ticker))
