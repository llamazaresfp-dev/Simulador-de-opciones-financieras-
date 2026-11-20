"""Comisiones del broker, calculadas en un único sitio.

Así el gráfico y las métricas restan siempre exactamente lo mismo.

Reglas (decisiones 6 y 14):
- Apertura: cada contrato de opción paga 'per_contract' (+ recargo si es
  un índice). Las acciones no pagan comisión.
- Cierre al vencimiento: solo si la opción vence con valor (ITM estricta).
  Una opción que vence sin valor (incluido S = K) simplemente expira y no
  hay que cerrarla, así que no paga cierre.
- Cierre "hoy": si cerramos la posición hoy hay que cerrar TODAS las patas
  de opción, valgan lo que valgan, así que todas pagan cierre.
"""

import numpy as np

from opciones.models import CommissionSettings, Leg, Market


def _fee_per_contract(market: Market, settings: CommissionSettings) -> float:
    """Comisión por contrato de opción en una operación (abrir o cerrar)."""
    fee = settings.per_contract
    if market.underlying == "Índice":
        fee += settings.index_surcharge
    return fee


def open_fee(leg: Leg, market: Market, settings: CommissionSettings) -> float:
    """Comisión pagada al abrir la pata (USD)."""
    if leg.kind == "stock":
        return 0.0
    return leg.quantity * _fee_per_contract(market, settings)


def close_fee_today(leg: Leg, market: Market, settings: CommissionSettings) -> float:
    """Comisión de cierre si liquidamos hoy: misma tarifa que la apertura.

    No depende de S: hoy toda opción tiene algo de valor temporal y hay
    que cerrarla (decisión 14).
    """
    if leg.kind == "stock" or not settings.include_close:
        return 0.0
    return leg.quantity * _fee_per_contract(market, settings)


def close_fee_expiry(leg: Leg, S, market: Market, settings: CommissionSettings):
    """Comisión de cierre al vencimiento, para cada precio final S.

    Depende de S porque solo se cierra la opción que vence con valor:
    call si S > K, put si S < K (desigualdad estricta). En S = K vale 0
    y expira sola, sin comisión.
    S puede ser un número o un array de numpy.
    """
    S_arr = np.asarray(S, dtype=float)
    if leg.kind == "stock" or not settings.include_close:
        fees = np.zeros_like(S_arr)
    else:
        if leg.kind == "call":
            in_the_money = S_arr > leg.strike
        else:
            in_the_money = S_arr < leg.strike
        fee = leg.quantity * _fee_per_contract(market, settings)
        fees = np.where(in_the_money, fee, 0.0)
    if np.ndim(S) == 0:
        return float(fees)
    return fees
