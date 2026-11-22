---
name: etapa-d-comparar-guardar SPEC
description: "SPEC (requisitos de producto) de la Etapa D de Laboratorio de Opciones (DISENO.md v3): guardar y cargar estrategias con nombre, y comparar 2 a 4 estrategias superpuestas en un mismo gráfico con una tabla de métricas."
date: 22-11-26
status: draft-para-revisión
---

# SPEC: Etapa D — Comparar y guardar estrategias

**TL;DR:** dos funciones nuevas. (1) **Guardar**: poner nombre a la estrategia del Constructor, guardarla en una carpeta local y/o descargarla como archivo JSON, y luego abrirla otro día. (2) **Comparar**: una pestaña nueva que superpone hasta 4 estrategias (la del Constructor + hasta 3 guardadas) en el mismo gráfico de P&L al vencimiento, con una tabla lado a lado (ganancia máx., pérdida máx., breakevens, comisiones, prima neta, PoP, griegas). Todas se valoran con **un mismo mercado** (el actual de la barra lateral) para que la comparación sea justa. El motor existente no cambia y nada pesado corre sin pulsar un botón o casilla. Los valores marcados "propuestos" se ajustan en la revisión del usuario.

## Summary

Hoy el usuario construye una estrategia y, al cerrar la app, la pierde; tampoco puede ver dos estrategias a la vez. La Etapa D añade: una sección **"💾 Guardar esta estrategia"** al final del Constructor (nombre + botón Guardar + descarga del JSON), una pestaña **"💾 Mis estrategias"** (lista de guardadas con abrir, añadir a la comparación, borrar y subir un JSON) y una pestaña **"⚖️ Comparar"** (curvas superpuestas + tabla). Una estrategia guardada contiene sus patas, su mercado, el modelo y las comisiones. Al abrirla, las primas automáticas se recalculan y las manuales se respetan; las patas con cotización de mercado se convierten en manuales con un aviso de "cotización guardada el <fecha>, puede estar desfasada". Al comparar, las estrategias guardadas aportan **sus patas**, revaloradas con el mercado actual. Los archivos externos se validan con cuidado: un JSON dañado o malicioso nunca rompe la app. Herramienta de estudio, no asesoría.

## User Stories / Jobs To Be Done

| # | Historia |
|---|---|
| D-US1 | Como aprendiz, quiero **poner nombre a mi estrategia y guardarla**, para revisarla mañana. |
| D-US2 | Como usuario, quiero **ver mis estrategias guardadas y abrir una en el Constructor**, con su mercado o solo sus patas, para seguir trabajando donde lo dejé. |
| D-US3 | Como usuario, quiero **descargar una estrategia como archivo y volver a subirlo**, para tener copia de seguridad o pasarla a otro equipo. |
| D-US4 | Como usuario, quiero **superponer 2 a 4 estrategias en un gráfico**, para ver cuál gana más, pierde menos o rompe antes. |
| D-US5 | Como usuario, quiero una **tabla lado a lado** (ganancia/pérdida máx., breakevens, comisiones, prima neta, PoP, griegas), para comparar con números. |
| D-US6 | Como usuario, quiero que la comparación sea **justa** (mismo mercado para todas) y que se me **avise** si una estrategia se guardó con otro mercado. |
| D-US7 | Como usuario, quiero que un **archivo corrupto o ajeno no rompa la app**, y recibir un mensaje claro en español. |
| D-US8 | Como usuario, quiero que **nada pesado corra solo** y que todo lo existente (Constructor, Backtest, modelos) **siga igual**. |

## What The User Wants (Behavioral Outcomes)

- **Guardar (en el Constructor, al final):** campo de nombre (máx. 60 caracteres), botón "Guardar" y botón de descarga del JSON. Sin patas o con datos inválidos, mensaje en español y no se guarda. Si el nombre ya existe, hay que marcar una casilla "sobrescribir" para reemplazarlo (valor propuesto).
- **Qué se guarda:** las patas (tipo, lado, cantidad, strike, precio, si la prima es manual o automática; para patas de mercado también bid/ask/vencimiento), el mercado (subyacente, spot, vol, días, tasa, dividendos, modelo), las comisiones y, como texto informativo, el ticker. **No** se guarda el snapshot ni la cadena de opciones.
- **Dónde:** (a) una carpeta local del proyecto (ignorada por git), un archivo por estrategia, hasta 100 estrategias; y (b) descarga/subida de JSON. Ambas vías disponibles (valor propuesto).
- **Pestaña "💾 Mis estrategias":** lista de guardadas (nombre, fecha, nº de patas) con tres acciones por fila: **"Abrir con su mercado"**, **"Abrir solo las patas"** (mantiene el mercado actual), **"Añadir a la comparación"**, y borrar (con confirmación). Un cuadro para subir un JSON y guardarlo en la lista.
- **Al abrir:** las primas manuales se respetan; las automáticas las recalcula la app; las patas de mercado pasan a manuales con la prima guardada y el aviso "cotización guardada el <fecha>, puede estar desfasada". "Abrir con su mercado" restaura también mercado, modelo y comisiones; limpia el ticker/snapshot cargado, que ya no corresponde.
- **Pestaña "⚖️ Comparar":** selector múltiple con las guardadas (+ la estrategia actual del Constructor, siempre presente). Máximo 4 en total. Un solo mercado común: el de la barra lateral. Si una guardada tenía otro mercado, aviso visible ("se guardó con spot X / vol Y; aquí se usa el actual"). Si se borra una guardada que estaba seleccionada, la selección se limpia sola.
- **Gráfico:** curvas de P&L al vencimiento superpuestas (siempre), paleta apta para daltónicos (azul = la del Constructor, naranja, verde azulado, magenta) con estilos de línea distintos y breakevens en el color de su curva; información al pasar el cursor unificada. Casilla opcional para añadir las curvas "hoy" (T+0).
- **Tabla lado a lado:** ganancia máxima, pérdida máxima, breakevens, comisiones totales, prima neta (débito/crédito), PoP exacta ("—" si quedan 0 días) y griegas de la posición. Las griegas y la curva "hoy" van detrás de una casilla/botón "Calcular comparación" (con modelo binomial pueden tardar).
- **Seguridad de archivos:** tamaño máximo 256 KB (valor propuesto), máximo 10 patas, valores fuera de las listas permitidas = error (no se corrigen en silencio), versión de esquema desconocida o ausente = mensaje claro. Nunca se ejecuta código del archivo.
- **Sin cambios:** motor, Catálogo, Constructor (salvo la sección nueva), Backtest, C1 y modelos funcionan igual.

## Flow / State Diagram

```
[Constructor: patas + mercado]
   |-- "Guardar" (nombre) --> {¿válido?} no --> [mensaje ES]
   |                              | sí --> {¿nombre existe?} sí, sin "sobrescribir" --> [aviso]
   |                                           | no / sobrescribir
   |                                           v
   |                          [carpeta local (escritura atómica)]
   |-- "Descargar JSON" ----------------------> [archivo en el equipo]

[Mis estrategias]  <-- "Subir JSON" --> [límite 256 KB -> JSON -> versión -> tipos -> motor valida]
   |                                         | error --> [mensaje ES, nada se guarda]
   |                                         | ok --> [carpeta local]
   |-- "Abrir con su mercado" / "Abrir solo las patas" --> [Constructor]
   |        (manuales se respetan; automáticas se recalculan; mercado -> manual + aviso)
   |-- "Añadir a la comparación" --> [Comparar]
   |-- "Borrar" (confirmar) --> [lista] --> [Comparar limpia su selección]

[Comparar: actual + hasta 3 guardadas]
   |
   v
[mercado común = barra lateral] --> [patas guardadas revaloradas] --> {¿mercado guardado distinto?} sí --> [aviso]
   |
   v
[curvas al vencimiento superpuestas + tabla (sin cálculo pesado)]
   |
   v
{¿casilla "hoy"/griegas o botón "Calcular comparación"?} sí --> [curvas T+0 + griegas]
```

## Acceptance Criteria (Testable Outcomes)

Escenarios según `process/context/tests/all-tests.md`: pytest sobre código puro y carpetas temporales (nunca la carpeta real ni `.cache_datos/`); AppTest para las pestañas (corre todos los cuerpos, por eso nada pesado sin clic); AppTest 1.67 **no** soporta el cuadro de subida de archivos, así que la subida es revisión manual.

**Guardado, formato y validación**
- **AC-D-1:** Una estrategia se convierte a un documento con versión de esquema 1 (nombre, fecha, patas sin id ni IV de Yahoo, mercado, comisiones, ticker informativo) y se reconstruye igual: ida y vuelta sin pérdida para patas manuales, automáticas y de mercado.
  proven by: serializa-ida-y-vuelta + campos-de-mercado-solo-en-patas-de-mercado + sin-snapshot-ni-id (tests puros)
  strategy: Fully-Automated
- **AC-D-2:** La validación de un documento nunca lanza excepción: tamaño > 256 KB, JSON inválido, no-objeto, versión ausente/mayor, tipos erróneos, valores fuera de listas (tipo, lado, fuente de prima, modelo), más de 10 patas, nombre vacío o > 60 caracteres devuelven un mensaje en español; el mercado y las patas pasan además por la validación existente del motor; no hay `eval` ni `pickle`.
  proven by: tabla-de-entradas-malas-parametrizada + versión-futura-mensaje + sin-coerción-silenciosa + reusa-validación-del-motor + sin-eval-ni-pickle (tests puros)
  strategy: Fully-Automated
- **AC-D-3:** La carpeta local guarda un JSON por estrategia con nombre de archivo seguro (solo `a-z 0-9 _ -`, ≤ 60, sin punto inicial, sufijo -2/-3 si colisiona), el nombre original dentro del JSON, escritura atómica, ruta resuelta siempre dentro de la carpeta (un nombre como `../../x` no escapa), lista ordenada, borrado, máx. 100 estrategias; la carpeta es inyectable para pruebas.
  proven by: slug-seguro + colisión-sufijo + escritura-atómica + path-traversal-bloqueado + lista-y-borra + límite-100 + carpeta-inyectable (tests con carpeta temporal)
  strategy: Fully-Automated
- **AC-D-4:** Un archivo corrupto en la carpeta se omite (con aviso) sin romper la lista; los tests nunca tocan la carpeta real; la carpeta de estrategias está en `.gitignore`.
  proven by: archivo-corrupto-omitido + tests-usan-tmp_path + carpeta-ignorada-por-git
  strategy: Fully-Automated

**Abrir en el Constructor**
- **AC-D-5:** "Abrir con su mercado" restaura patas, mercado, modelo y comisiones; "Abrir solo las patas" mantiene el mercado y las comisiones actuales. En ambos: manuales intactas, automáticas recalculadas, patas de mercado → manuales con la prima guardada y aviso con la fecha; se limpian ticker/snapshot/vencimiento cargados.
  proven by: abrir-con-mercado + abrir-solo-patas + premium-manual-respetada + auto-recalculada + mercado-a-manual-con-aviso + datos-cargados-limpiados (AppTest, con carpeta temporal)
  strategy: Fully-Automated
- **AC-D-6:** Guardar desde el Constructor: sin patas o con datos inválidos muestra error y no escribe; nombre duplicado sin "sobrescribir" avisa y no escribe; con "sobrescribir" reemplaza; el botón de descarga entrega el mismo JSON que se guardaría.
  proven by: guardar-ok + guardar-sin-patas-error + duplicado-sin-sobrescribir + duplicado-con-sobrescribir + descarga-igual-a-serialización (AppTest + tests puros)
  strategy: Fully-Automated

**Importar/exportar y lista**
- **AC-D-7:** La función pura de importación acepta los bytes de un archivo y devuelve estrategia o mensaje de error; la pestaña "Mis estrategias" lista, abre, añade a la comparación y borra (con confirmación). El **cuadro de subida** real se prueba a mano.
  proven by: importar-bytes-ok-y-errores (tests puros) + lista-abre-borra (AppTest); subida-real-de-archivo (revisión manual)
  strategy: Hybrid

**Comparar**
- **AC-D-8:** Las métricas por estrategia (ganancia máx., pérdida máx., breakevens, comisiones, prima neta, PoP, griegas) coinciden con las existentes del motor para esa estrategia sola; la prima neta tiene un ayudante puro nuevo con oráculo manual (débito/crédito, cantidad × multiplicador); PoP = "—" si días = 0.
  proven by: métricas-iguales-a-motor-individual + prima-neta-oráculo + pop-guion-con-0-días (tests puros)
  strategy: Fully-Automated
- **AC-D-9:** Las curvas se calculan en una malla común (unión de las mallas de cada estrategia) y cada curva en esa malla coincide con su P&L al vencimiento individual; máximo 4 estrategias (la 5ª se rechaza con mensaje); las guardadas se revaloran con el mercado actual (automáticas recalculadas, manuales intactas); aviso si su mercado guardado difiere.
  proven by: malla-común-unión + curva-igual-a-individual + límite-4 + revaloración-con-mercado-actual + aviso-mercado-distinto (tests puros + AppTest)
  strategy: Fully-Automated
- **AC-D-10:** La pestaña "Comparar" muestra el gráfico superpuesto y la tabla sin cálculo pesado; "hoy" y griegas solo con la casilla/botón; con solo la estrategia actual y nada seleccionado muestra una guía amable; si se borra una guardada seleccionada, la selección se limpia sin error.
  proven by: comparar-sin-clic-no-es-pesado + hoy-y-griegas-tras-clic + sin-selección-guía + selección-limpiada-al-borrar (AppTest, tiempos con cota holgada)
  strategy: Fully-Automated
- **AC-D-11:** Aspecto del gráfico: colores distinguibles (paleta apta para daltónicos), estilos de línea distintos, breakevens en el color de su curva, hover unificado, legible en tema claro y oscuro.
  proven by: revisión visual manual; paleta-y-estilos-por-índice (test puro)
  strategy: Hybrid

**Interfaz y arquitectura**
- **AC-D-12:** Existen las pestañas "⚖️ Comparar" y "💾 Mis estrategias" en el orden propuesto; los tests que listan las pestañas se actualizan (solo etiquetas); las claves de widgets son estables (derivadas del nombre seguro) y los textos de los selectores no leen estado ni reloj.
  proven by: pestañas-existen-en-orden + claves-estables (AppTest)
  strategy: Fully-Automated
- **AC-D-13:** La lógica de guardado vive en un paquete nuevo de nivel superior (conversión y validación puras; carpeta y archivos aparte); puede importar el motor pero **el motor no lo importa**; `import` del paquete no carga Streamlit; `opciones/` y `datos/` sin diff; solo biblioteca estándar.
  proven by: aislamiento-sin-streamlit + motor-no-importa-paquete (tests en subproceso) + opciones-y-datos-sin-diff + requirements-sin-diff (revisión de diff)
  strategy: Hybrid
- **AC-D-14:** Los **3029 tests existentes (+ 4 omitidos)** siguen en verde sin conexión; los nuevos corren sin red y sin tocar `.estrategias/` ni `.cache_datos/`.
  proven by: suite-completa-sin-red + tests-no-tocan-carpetas-reales
  strategy: Fully-Automated

## Locked Decisions

Las decisiones del MVP, A, B1, C1 y C2 siguen vigentes. Nuevas (derivadas de la intención del usuario y la investigación):

| # | Decisión |
|---|---|
| D-1 | Etapa D = **guardar/cargar con nombre + comparar** (DISENO.md v3). |
| D-2 | Se guarda un **formato JSON versionado** (esquema 1); nunca snapshot ni cadena de opciones; sin id de pata ni IV de Yahoo. |
| D-3 | Importar es **no confiable por defecto**: tope de tamaño antes de leer, validación estricta, sin `eval`/`pickle`, sin corrección silenciosa. |
| D-4 | Las primas **manuales se respetan; las automáticas se recalculan**; las patas de mercado pasan a manuales con aviso de cotización antigua. |
| D-5 | La comparación usa **las patas** de las guardadas, revaloradas con el **mercado común actual**. |
| D-6 | Curvas **al vencimiento** siempre; "hoy" y griegas, detrás de casilla/botón (el binomial es lento en frío). |
| D-7 | El motor y `datos/` **no cambian**; nuevo paquete aparte que el motor no importa. |
| D-8 | Todo en UI en español; identificadores en inglés; nada pesado sin clic. |

### Valores propuestos, ajustables en la revisión del usuario

| # | Parámetro | Valor propuesto |
|---|---|---|
| 1 | Mercado de la comparación | Uno común (el actual); aviso si el guardado difiere |
| 2 | Almacenamiento | Ambos: carpeta local `.estrategias/` + descarga/subida de JSON |
| 3 | Máx. estrategias comparadas | 4 (Constructor + 3 guardadas) |
| 4 | Contenido guardado | Patas + mercado + comisiones; automáticas recalculadas, manuales respetadas, mercado → manual con aviso |
| 5 | Abrir | Dos botones: "Abrir con su mercado" y "Abrir solo las patas" |
| 6 | Interfaz y orden de pestañas | Pestañas propias "⚖️ Comparar" y "💾 Mis estrategias" + sección de guardado en el Constructor. Orden: Catálogo, Constructor, Comparar, Mis estrategias, Ajustes, Backtest |
| 7 | Contenido de la comparación | Curvas al vencimiento siempre; "hoy" y griegas tras casilla; tabla con las métricas listadas |
| 8 | Límites | Nombre ≤ 60 car.; archivo ≤ 256 KB; ≤ 10 patas; ≤ 100 guardadas; sobrescribir = casilla de confirmación |
| 9 | Paleta | Azul #2a78d6 (Constructor), naranja #eb6834, verde azulado #009e73, magenta #cc79a7, con estilos de línea distintos |

## Out Of Scope

- Sincronización en la nube, cuentas de usuario, compartir por enlace.
- Guardar el snapshot/cadena de opciones o resultados de Monte Carlo/Backtest.
- Comparar con **mercados distintos** por estrategia, o más de 4 estrategias.
- Comparar resultados de Monte Carlo (queda para después) y recomendar la "mejor" estrategia.
- Edición de la estrategia guardada dentro de la pestaña "Mis estrategias" (se abre en el Constructor).
- Migración entre versiones de esquema (solo existe la 1; versiones mayores se rechazan con mensaje).
- Importar formatos de otros programas; cifrado de archivos.
- Cambios en el motor, en `datos/`, o dependencias nuevas.
- Operar, órdenes, bróker; asesoría de inversión.

## Constraints

- **Usuario:** nivel básico de Python; código sencillo; explicaciones cortas; UI en español con términos de opciones en inglés; uso personal.
- **Proceso:** cálculo en módulos puros; la app solo dibuja; identificadores en inglés, comentarios/UI en español; tests con `.venv/bin/pytest`; floats con `pytest.approx`; suite sin red; el estado de widgets solo se cambia mediante callbacks (como `open_template`).
- **Técnico:** Python 3.12; `requirements.txt` sin cambios (solo `json`, `os`, `re`, `tempfile`, `datetime`); `opciones/` y `datos/` sin diff; `.estrategias/` añadida a `.gitignore`; carpeta inyectable por `st.session_state["strategies_dir"]` para tests; escribir `underlying` desde otro callback no dispara su callback propio, así que al abrir hay que limpiar ticker/snapshot/vencimiento a mano; AppTest 1.67 no soporta la subida de archivos.
- **Rendimiento (medido):** curvas al vencimiento ~0,1 ms; métricas ~1,6 ms; PoP ~2 ms; binomial en frío ~0,78 s (en caliente ~2 ms) → lo pesado, detrás de clic.
- **Regresión:** 3029 tests (+ 4 omitidos) en verde sin conexión.

## Open Questions

None bloqueantes. Los 9 valores propuestos se aprueban o ajustan en la revisión del usuario (owner: user). Un detalle de nivel PLAN (next-phase): cómo organizar los archivos de tests nuevos y el cambio de etiquetas en los tests de pestañas.

## Background / Research Findings

- **Estado actual:** las patas viven en `st.session_state["legs"]` como diccionarios (id, tipo, lado, cantidad, strike, precio, prima manual, fuente de prima, bid/ask, IV de Yahoo, vencimiento); el mercado y las comisiones se copian desde widgets mediante callbacks; `open_template` es el modelo de "cargar en el constructor"; las primas automáticas se recalculan en cada ejecución.
- **Validación del motor reutilizable:** `validate_legs` y `validate_market`; el nuevo código solo añade validación de forma/tipo del archivo.
- **Pestañas actuales:** Catálogo, Constructor, Ajustes, Backtest (la lista y su desempaquetado en `main()` cambian).
- **Rendimiento medido:** ver Constraints. AppTest ejecuta el cuerpo de todas las pestañas: nada pesado sin clic.
- **Diseño visual:** seguir el rediseño del usuario (etiquetas con emoji, divisor de subheader, sistema de colores, colores seguros para tema claro/oscuro).
- **Patrón de aislamiento ya probado:** `datos/` con `test_datos_isolation` y escritura atómica de `datos/cache.py`.
- Fuentes: `DISENO.md` (v3), `process/context/all-context.md`, `process/context/tests/all-tests.md`, SPEC de C2, investigación de vc-research-agent (22-11-26).

### Known gaps / Risks

| # | Riesgo o hueco | Tratamiento |
|---|---|---|
| D-G1 | **Archivos manipulados** (JSON enorme, tipos raros, `../` en el nombre). | Tope de tamaño, validación estricta, slug seguro y ruta contenida (AC-D-2, AC-D-3). |
| D-G2 | **Cotizaciones de mercado guardadas desfasadas.** | Pasan a manuales con aviso y fecha (AC-D-5). |
| D-G3 | **Mercado guardado distinto del actual** distorsiona la comparación. | Mercado común + aviso (AC-D-9). |
| D-G4 | **Cálculo pesado (binomial en frío ~0,78 s)** al comparar. | Detrás de casilla/botón (AC-D-10). |
| D-G5 | **Subida de archivos no automatizable en AppTest 1.67.** | Función pura probada aparte + revisión manual (AC-D-7). |
| D-G6 | **Selección obsoleta** si se borra una estrategia comparada. | Limpieza automática de la selección (AC-D-10). |
| D-G7 | **Tests tocando carpetas reales.** | Carpeta inyectable + `tmp_path` (AC-D-4, AC-D-14). |
| D-G8 | **Sin tests visuales** (hueco heredado). | Revisión manual del gráfico (AC-D-11). |
| D-G9 | **Cambio de pestañas rompe tests que las listan.** | Actualización solo de etiquetas (AC-D-12). |

## Definition of Done (Etapa D)

- Los 14 criterios AC-D-1…AC-D-14 se cumplen; los Hybrid pasan además la revisión manual del usuario (subida de JSON, aspecto del gráfico).
- Los 3029 tests existentes (+ 4 omitidos) siguen en verde **sin conexión**; los nuevos corren sin red y con carpetas temporales.
- La app arranca con `.venv/bin/streamlit run app.py`: se puede guardar, abrir (con mercado o solo patas), descargar/subir, y comparar 2 a 4 estrategias con curvas y tabla.
- `opciones/` y `datos/` sin diff; `requirements.txt` sin cambios; `.estrategias/` en `.gitignore`.
- Valores propuestos aprobados o ajustados por el usuario al revisar el SPEC.
