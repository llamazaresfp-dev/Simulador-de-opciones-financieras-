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

Histórico (Etapa C2, `get_history`): NO usa fixtures. Genera en código
un movimiento browniano geométrico (GBM) determinista: días hábiles
(lunes a viernes, sin festivos) contados hacia atrás desde el reloj
inyectado y precios con `random.Random(semilla)`. La semilla es la suma
de los códigos `ord` de las letras del símbolo (nunca `hash()`, que
cambia entre ejecuciones de Python). Así dos llamadas iguales dan lo
mismo, dos tickers dan series distintas y nada caduca con el tiempo real.
`^IRX` devuelve una serie en PORCENTAJE (constante o con escalones).
Registra cada llamada en `history_calls` (símbolo, inicio, fin).
"""

import copy
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

from datos.cache import market_today
from datos.errors import EmptyDataError
from datos.service import rate_from_percent
from datos.tickers import CURATED_TICKERS, HISTORY_SYMBOLS, RATE_HISTORY_SYMBOL
from datos.types import PriceHistory

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

# --- Histórico sintético (Etapa C2) ---

# Años de historia que genera el proveedor falso (hacia atrás desde hoy).
FAKE_HISTORY_YEARS = 30

# Precio del primer día de la serie sintética (USD).
FAKE_START_PRICE = 100.0

# Sesiones por año para pasar mu y sigma anuales a diarios.
TRADING_DAYS_PER_YEAR = 252

# Cada cuántas sesiones se paga un dividendo (~un trimestre).
DIVIDEND_EVERY_SESSIONS = 63


def _known_history_symbols() -> set[str]:
    """Símbolos con histórico en el proveedor falso.

    Los tickers curados (salvo los que usan otros símbolos, como SPX),
    los símbolos del índice (^GSPC, ^SPX) y la tasa (^IRX).
    """
    symbols = {RATE_HISTORY_SYMBOL}
    for tickers in CURATED_TICKERS.values():
        for label in tickers:
            symbols.update(HISTORY_SYMBOLS.get(label, (label,)))
    return symbols


KNOWN_HISTORY_SYMBOLS = _known_history_symbols()


def history_seed_for(symbol, seed=0) -> int:
    """Semilla del histórico: suma de `ord` de las letras + `seed`."""
    return sum(ord(char) for char in symbol) + seed


def _years_before(day, years) -> date:
    """La misma fecha `years` años naturales antes (29-feb -> 28-feb)."""
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def _business_days(first, last) -> list[date]:
    """Días hábiles (lunes a viernes) entre `first` y `last`, ambos incluidos.

    Se cuentan hacia atrás desde `last` y se devuelven en orden ascendente.
    """
    days = []
    day = last
    while day >= first:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    days.reverse()
    return days


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

    Parámetros del histórico (Etapa C2; con sus valores por defecto no
    cambian nada de lo anterior):
    - sigma, mu: volatilidad y crecimiento anuales del GBM sintético.
    - seed: se suma a la semilla de cada símbolo (por defecto 0).
    - dividends: rentabilidad anual por dividendo (fracción) para pagar
      dividendos trimestrales; None = sin dividendos. Nunca en índices.
    - irx_percent_series: escalones de ^IRX como pares (fecha ISO,
      porcentaje); antes del primero vale `irx_percent`.
    - history_empty_symbols: símbolos que responden vacío (EmptyDataError).
    - history_fail_symbols: {símbolo: error} que lanza `get_history`.
    - history_years: tope de años de historia (para fuentes "cortas").
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
        sigma=0.20,
        mu=0.07,
        seed=0,
        dividends=None,
        irx_percent_series=None,
        history_empty_symbols=None,
        history_fail_symbols=None,
        history_years=None,
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
        # Histórico (Etapa C2).
        self.sigma = sigma
        self.mu = mu
        self.seed = seed
        self.dividends = dividends
        self.irx_percent_series = tuple(sorted(irx_percent_series or ()))
        self.history_empty_symbols = set(history_empty_symbols or ())
        self.history_fail_symbols = dict(history_fail_symbols or {})
        self.history_years = history_years
        # Registro de llamadas a get_history: (símbolo, inicio, fin).
        self.history_calls = []
        # Series ya generadas, por símbolo (se generan una sola vez).
        self._generated = {}

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

    # --- Interfaz HistoryProvider (Etapa C2) ---

    def get_history(self, symbol, start, end) -> PriceHistory:
        """Histórico diario sintético entre `start` (incluido) y `end` (excluido).

        - Símbolo desconocido, en `history_empty_symbols` o tramo sin días
          hábiles -> EmptyDataError.
        - Símbolo en `history_fail_symbols` (o `fail_with`) -> ese error.
        - Con `history_years`, además no devuelve nada anterior a
          `today - history_years` años.
        """
        self.history_calls.append((symbol, start, end))
        self._start("get_history")
        if symbol in self.history_fail_symbols:
            _raise(self.history_fail_symbols[symbol])
        if symbol in self.history_empty_symbols or symbol not in KNOWN_HISTORY_SYMBOLS:
            raise EmptyDataError()

        first = start
        if self.history_years is not None:
            first = max(start, _years_before(self.today, self.history_years))
        first_iso = first.isoformat()
        end_iso = end.isoformat()

        dates, close, adj_close, dividends = self._full_history(symbol)
        keep = [i for i, day in enumerate(dates) if first_iso <= day < end_iso]
        if not keep:
            raise EmptyDataError()
        return PriceHistory(
            ticker=symbol,
            dates=tuple(dates[i] for i in keep),
            close=tuple(close[i] for i in keep),
            adj_close=tuple(adj_close[i] for i in keep),
            dividends=tuple((day, amount) for day, amount in dividends if first_iso <= day < end_iso),
        )

    def _full_history(self, symbol):
        """Serie completa de un símbolo: (fechas, cierre, ajustado, dividendos).

        Abarca FAKE_HISTORY_YEARS años hasta hoy y se genera una sola vez.
        """
        if symbol not in self._generated:
            days = _business_days(_years_before(self.today, FAKE_HISTORY_YEARS), self.today)
            dates = [day.isoformat() for day in days]
            if symbol == RATE_HISTORY_SYMBOL:
                close = [self._irx_on(day) for day in dates]
                series = (dates, close, list(close), [])
            else:
                series = self._gbm_history(symbol, dates)
            self._generated[symbol] = series
        return self._generated[symbol]

    def _irx_on(self, day) -> float:
        """^IRX (porcentaje) de un día: el último escalón con fecha <= día."""
        value = self.irx_percent
        for step_day, step_value in self.irx_percent_series:
            if step_day <= day:
                value = step_value
        return value

    def _gbm_history(self, symbol, dates):
        """Precios GBM deterministas, con dividendos trimestrales opcionales."""
        rng = random.Random(history_seed_for(symbol, self.seed))
        dt = 1 / TRADING_DAYS_PER_YEAR
        drift = (self.mu - self.sigma**2 / 2) * dt
        shock = self.sigma * math.sqrt(dt)
        close = [FAKE_START_PRICE]
        for _ in range(len(dates) - 1):
            close.append(close[-1] * math.exp(drift + shock * rng.gauss(0.0, 1.0)))

        # Dividendos: cada DIVIDEND_EVERY_SESSIONS sesiones (nunca en índices).
        paid = {}
        if self.dividends and not symbol.startswith("^"):
            for i in range(DIVIDEND_EVERY_SESSIONS, len(dates), DIVIDEND_EVERY_SESSIONS):
                paid[i] = close[i - 1] * self.dividends / 4

        # Cierre ajustado: cada dividendo rebaja los cierres ANTERIORES a
        # su fecha con el factor (1 - dividendo / cierre del día previo).
        adj_close = [0.0] * len(close)
        factor = 1.0
        for i in range(len(close) - 1, -1, -1):
            adj_close[i] = close[i] * factor
            if i in paid:
                factor *= 1 - paid[i] / close[i - 1]
        dividends = [(dates[i], paid[i]) for i in sorted(paid)]
        return dates, close, adj_close, dividends
