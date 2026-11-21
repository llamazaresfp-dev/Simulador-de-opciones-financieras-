---
domain: plan
iteration: 2
date: 2026-11-21
gaps_found: 4
fail_count: 0
concern_count: 1
applied_count: 4
backlogged_count: 0
saturation_status: ACTIVE
loop_status: CONTINUE
---

# PVL iteración 002 — etapa C1 (datos en directo)

**Entrada:** revalidación tras el ciclo 1: `Gate: CONDITIONAL` (0 FAIL, 1 CONCERN + 2 avisos). C-V1..C-V5 confirmados como resueltos (sonda AppTest SPY→QQQ correcta).

| Gap | Hueco | Corrección (vc-plan-agent, supplement 2) |
|---|---|---|
| C-V6 | El servicio (3c) usaba la caché, que se creaba después (3d) | Reordenado: 3c = caché (`richness`, `is_richer_or_equal`, `write_snapshot`); 3d = FakeProvider + servicio |
| A1 | Faltaban pruebas exactas de los límites 7/120 días | `FakeProvider(today, offsets=(10,17,45,90,150))` + tests 6/7/120/121 |
| A2 | Tras "Cargar datos" no quedaba vencimiento seleccionado | `on_load_data` fija `expiry_choice` (primero ofrecido) y `days`; aserción AppTest en el bloque 5 |
| A3 | Zona horaria del reloj sin definir | Fechas de mercado en `America/New_York`; texto "HH:MM" en la zona local |

**Señal:** `SUPPLEMENT_APPLIED: ... — 4 gap(s) addressed`. Validador de estructura: 0 fallos.
**Siguiente:** re-ejecutar vc-validate-agent desde V1.
