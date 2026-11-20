---
name: close-fee-rational-close
description: "Backlog: cobrar la comisión de cierre al vencimiento solo si el valor de la opción supera la comisión (cierre racional); cambiaría la decisión 6."
date: 20-11-26
status: backlog
priority: low
---

# Backlog: comisión de cierre racional al vencimiento

**Priority**: Low (efecto <= una comisión por contrato).

## Problem

Hoy (decisión 6) la curva al vencimiento cobra la comisión de cierre en toda pata de opción ITM estricta, aunque el valor de la opción sea menor que la comisión. Ejemplo: call largo con S apenas por encima de K vale unos centavos y paga 0,65 USD de cierre; en la práctica un trader racional no cerraría y dejaría vencer. Esto crea un pequeño salto artificial de hasta una comisión por contrato en la curva y desplaza ligeramente breakevens y extremos.

## Root cause

`close_fee_expiry` en `opciones/commissions.py` usa solo la condición ITM estricta, sin comparar el valor de la opción con la comisión.

## Fix options

- Cobrar el cierre al vencimiento solo si el valor intrínseco por contrato (x multiplicador) supera la comisión de cierre ("cierre racional").
- Mantener la regla actual y documentarla (opción actual elegida por el usuario durante EXECUTE).

## Impact if implemented

- Cambia la decisión 6 del SPEC (el SPEC está congelado; registrar la nueva decisión en un plan nuevo).
- Código: `opciones/commissions.py`, posiblemente `opciones/metrics.py` (kinks y extremos).
- Tests: `tests/test_commissions.py`, `tests/test_metrics.py`, `tests/test_catalog.py` (valores de libro con comisión, p. ej. bull call spread −201,95 y breakevens) y las notas de la UI.

## Why deferred

El usuario decidió durante EXECUTE mantener la decisión 6 tal cual para el MVP.

## Nota Etapa B (20-11-26)

La investigación de la Etapa B definió "racional" como abandonar si valor ≤ comisión (P&L continuo, sin salto), patas cortas sin cambio, como interruptor en Ajustes activado por defecto. El usuario ya aceptó estas decisiones para la Etapa B2, que sigue diferida.
