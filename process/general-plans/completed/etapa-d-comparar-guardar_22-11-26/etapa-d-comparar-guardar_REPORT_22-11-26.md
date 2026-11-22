---
phase: etapa-d-comparar-guardar-closeout
date: 2026-11-22
status: COMPLETE_WITH_GAPS
feature: none (general-plans)
plan: process/general-plans/completed/etapa-d-comparar-guardar_22-11-26/etapa-d-comparar-guardar_PLAN_22-11-26.md
---

# Informe de fase: Etapa D, comparar y guardar estrategias (UPDATE PROCESS)

TL;DR: los 7 bloques están verificados, AC-D-1..AC-D-14 cumplidos, suite 3397 passed + 4 skipped (también bajo `unshare -rn`, sin red), checklist manual de 8 puntos pasada por el usuario el 22-11-26 ("Todo bien"). Clasificación: COMPLETE_WITH_GAPS (2 huecos conocidos, ninguno bloquea). Plan archivado en `completed/`.

### What Was Done
- Paquete nuevo de nivel superior `estrategias/` (solo biblioteca estándar, sin Streamlit; puede importar `opciones`, el motor no lo importa):
  - `serialize.py`: `strategy_to_dict`, `prepare_document`, `parse_strategy_json`; esquema versión 1; tope de 256 KB; límites de magnitud (BOUNDS: spot/strike [0,01; 1e7], cantidad [1e-6; 1e5], prima/bid/ask [0; 1e6], vol [MIN_VOL; 5], días [0; 3650], tasa/q [-0,5; 1], comisiones [0; 1e3]); nunca lanza excepción.
  - `store.py`: carpeta `.estrategias/` (inyectable, se lee `DEFAULT_STRATEGIES_DIR` en el momento de la llamada), un JSON por estrategia, nombre de archivo seguro (slug) con sufijo -2/-3, escritura atómica, tope de 100 archivos, omite enlaces simbólicos y FIFOs.
  - `compare.py`: malla común de vencimiento, curva "hoy" en la malla propia de cada estrategia, prima neta, filas de la tabla con PoP "—" a 0 días, try/except por entrada.
- Interfaz: `ui_estrategias.py` (pestaña "💾 Mis estrategias" y sección de guardado al final del Constructor, con descarga y subida de JSON) y `ui_comparar.py` (pestaña "⚖️ Comparar": curvas superpuestas con paleta apta para daltónicos, tabla lado a lado, "hoy" y griegas tras casilla). `app.py` pasa a 6 pestañas: ["📊 Catálogo", "🛠️ Constructor", "⚖️ Comparar", "💾 Mis estrategias", "⚙️ Ajustes", "📈 Backtest"]; `open_saved_strategy(slug, with_market)` escribe claves simples y de widget.
- Tests nuevos: test_estrategias_serialize, test_estrategias_store, test_estrategias_compare, test_estrategias_isolation, test_app_estrategias, test_app_comparar; `tests/conftest.py` con fixture autouse que redirige `estrategias.store.DEFAULT_STRATEGIES_DIR`; `.gitignore` añade `.estrategias/`. Tests existentes editados solo en etiqueta/índice/nombre de pestaña.
- Commits: SPEC 9b586ba; plan a94186e (suplementos PVL S-1..S-5); bloques dd11666 (1 serialización), d3bfb6f (2 almacén + .gitignore + conftest), 30ebd5f (3 comparación), f3b9860 (4 aislamiento), 19dacc9 (5 seis pestañas, sección de guardado, Mis estrategias), eabb898 (6 callbacks de abrir, avisos, subida), 62599cf (7 pestaña Comparar); fila EVL bc12d4c.
- INNOVATE omitido (el "cómo" quedó resuelto por la investigación), registrado en el plan.
- PVL: 2 ciclos de suplemento (S-1 claves `*_input` de widgets al cargar, S-2 límites de magnitud con try/except, S-3 prueba de aislamiento por recorrido ast, S-4 "hoy" en mallas propias, S-5 pisos positivos spot/strike >= 0,01 y cantidad >= 1e-6); Gate PASS en el ciclo 2. EVL: sin ciclos de arreglo (`results.tsv` filas 0-5 en esta carpeta).
- Tiempos: comparar sin cálculo pesado 0,045 s; pesado ("hoy" + griegas) 4 iron condors en frío 1,2-1,5 s.
- Ejecución manual del usuario (22-11-26): checklist de 8 puntos, "Todo bien". El usuario aceptó los 9 valores propuestos del SPEC.

### What Was Skipped/Deferred
- Etapa B2 (comisión de cierre racional): sigue en backlog `process/general-plans/backlog/close-fee-rational-close_20-11-26.md`.
- Etapa C3 (opciones históricas de pago): opcional, no planificada.
- Posible trabajo futuro: comparación con VIX, repetición de estrategias, asistente de DISEÑO v4 (sugerencias de estrategias); sin plan.

### Test Gate Outcomes
- `.venv/bin/pytest -q`: 3397 passed, 4 skipped (EVL final, vc-tester), también bajo `unshare -rn`.
- 4 skips: 2 de binomial (IV) + 2 en vivo opcionales (C1 y C2, requieren `LIVE_DATA=1`).
- Diff de `opciones/`, `datos/` y `requirements.txt` vacío; huella de `.cache_datos` sin cambios; `.estrategias/` ausente tras la suite; `git check-ignore` correcto; revisión de seguridad puntual limpia.

### Plan Deviations
- Los botones de abrir se cablearon en el bloque 6 (no en el 5); el multiselect se añadió en el bloque 5.
- AppTest 1.67 SÍ soporta `file_uploader` y `download_button`: se añadieron pruebas reales (el plan las daba por no automatizables).
- Cuadro de subida en un expander sobre la lista.
- Nombres tipo ruta (`../x`) se aceptan como texto y se convierten a slug dentro de la carpeta; NUL, demasiado largo o vacío se rechazan.
- Mensajes de callbacks vía `sv_message`; valores de widgets escritos en `session_state` antes de crearlos (sin `value=`); griegas en una sola columna; formato con punto decimal.
- Peor P&L de la call larga -251,30 (la comisión de cierre aparece justo por encima del strike).

### Test Infra Gaps Found
- Sin pruebas visuales del gráfico (hueco heredado): revisión manual del usuario.
- Los `number_input` de la barra lateral no tienen min/max (hueco 1).

### SPEC Achievement
AC-D-1..AC-D-14: todos **met** (Fully-Automated por gates pytest verdes; Hybrid por gates automáticos más la checklist manual de 8 puntos). Ninguno unmet ni basado solo en Known-Gap.

## SPEC Gaps
Ninguno de criterios. Huecos conocidos: (1) los `number_input` de la barra lateral no tienen mínimo/máximo, así que un spot absurdo escrito a mano (1e-300) aún puede romper el Constructor (comportamiento del MVP, no relacionado con archivos); (2) `.estrategias/` es almacenamiento local por máquina, no apto para un despliegue compartido (la descarga/subida de JSON cubre la portabilidad). Sin stubs de seguimiento.

### Closeout Packet
1. Plan seleccionado: `process/general-plans/completed/etapa-d-comparar-guardar_22-11-26/etapa-d-comparar-guardar_PLAN_22-11-26.md` (antes en `active/`).
2. Clasificación: COMPLETE_WITH_GAPS (gates verdes; known_gaps: 2; follow_up_stubs: 0).
3. Qué se terminó: ver What Was Done.
4. Verificado vs no verificado: todo verificado salvo el aspecto visual (solo manual).
4b. Validate-contract: Gate PASS tras 2 ciclos de PVL.
5. Limpieza: contexto actualizado, plan cerrado, carpeta archivada.
6. Siguiente estado válido: B2 (backlog), C3 opcional, comparación con VIX / repetición de estrategias / asistente v4.
7. Commit: commits de código ya hechos; cierre de proceso en un commit aparte.
8. Regresión: plan único; suite completa 3397 passed + 4 skipped.
9. SPEC achievement: 14/14 met.

### Lessons
- Cuando un callback restaura estado, escribir tanto la clave simple como la clave del widget (`*_input`); si no, los widgets conservan valores viejos.
- Los validadores del motor solo comprueban finitud: las entradas de archivos necesitan límites de magnitud, incluidos pisos positivos.
- Leer las carpetas por defecto de nivel de módulo en el momento de la llamada para que los tests puedan redirigirlas.
- AppTest 1.67 soporta `file_uploader` y `download_button`.

### Forward Preview

#### Test Infra Found
Fixture autouse en `tests/conftest.py` que redirige `estrategias.store.DEFAULT_STRATEGIES_DIR` a una carpeta temporal; prueba de aislamiento por recorrido ast.

#### Blast Radius Changes
Paquete nuevo `estrategias/`, `ui_estrategias.py`, `ui_comparar.py`; `app.py` con 6 pestañas y nuevos callbacks; `.gitignore`; motor y `datos/` intactos.

#### Commands to Stay Green
`.venv/bin/pytest -q` (3397 passed + 4 skipped); `LIVE_DATA=1 .venv/bin/pytest tests/test_datos_live.py -q` (opcional, requiere red).

#### Dependency Changes
Ninguno.

### Context Audit
- `process/context/all-context.md`: actualizado (estructura, 6 pestañas, comportamientos de la etapa D, lecciones, abiertos, metadatos, `.estrategias/`).
- `process/context/tests/all-tests.md`: actualizado (archivos nuevos, 3397 + 4, fixture autouse, índices de pestañas, huecos).
- `process/context/planning/all-planning.md`: revisado, sin cambios.
