---
domain: tests
iteration: 1
date: 2026-11-21
gaps_found: 1
fail_count: 1
concern_count: 0
applied_count: 1
backlogged_count: 0
saturation_status: ACTIVE
loop_status: CONTINUE
---

# EVL iteración 001 — etapa C1 (bloque 3c, caché)

**Contexto:** puertas del bloque 3c en verde (203 / 2560 passed). El orquestador sospechó un fallo de diseño en la regla parcial-vs-rico; vc-tester lo confirmó con un prototipo.

| Gap | Defecto | Corrección |
|---|---|---|
| F1 (alto, AC-C1-10) | `write_snapshot` compara recuentos brutos (vencimientos, cotizaciones). Una carga completa al día siguiente con un vencimiento caducado (3 → 2) se rechaza y la caché queda anclada a datos viejos | El snapshot lleva `complete: bool` (lo fija el servicio: False si se paró por 429 o hubo errores); una carga completa siempre se escribe; una parcial solo si es más rica que la guardada, comparando ambas con la ventana y reglas de hoy; test de regresión del caso |

**Siguiente:** vc-execute-agent (supplement) y re-ejecución de vc-tester.
