# Registro de cierre de fases

Regla (ADR-024): ninguna fase empieza sin que la anterior haya cerrado aquí sobre un commit
limpio. Las excepciones requieren aprobación explícita del autor y se registran.

## F0: Fundaciones

- **Inicio:** 2026-11-15, tras la aprobación del diseño (decisiones D1–D24).
- **Cierre:** 2026-11-15.
- **Estado:** ✅ Cerrada. Todos los criterios de aceptación cumplidos.
- **Repositorio:** https://github.com/AndresGoGutierrez/NeuroEcosistema (privado, rama `main`).
- **Commit verificado:** `36377fd` (`chore: initialize NeuroEcosistema project structure`), autor
  único `AndresGoGutierrez`.
- **CI:** ejecución `43739617067` del workflow `ci`: `checks (ubuntu-latest)` success y
  `checks (windows-latest)` success.

| Criterio | Evidencia | Estado |
|---|---|---|
| `uv sync --frozen` funciona en un clon limpio | Copia del árbol sin `.venv`, `.git` ni cachés: instalación desde `uv.lock` con Python 3.12.14 | ✅ |
| `ruff check` y `ruff format --check` en verde | Repositorio y copia limpia | ✅ |
| `lint-imports` en verde | 3 contratos cumplidos (capas; núcleo sin dependencias externas salvo numpy; `analysis` aislado) | ✅ |
| `pytest` en verde | 10 pruebas (humo, arquitectura, semilla del proyecto) | ✅ |
| Los contratos detectan violaciones | Módulo temporal en `domain` con `import yaml`, `import random` e importación relativa a `infrastructure`: fallan import-linter, la prueba AST y ruff (TID251) | ✅ |
| Semilla del proyecto fijada | `configs/base.yaml`, 128 bits, generada con `secrets.randbits(128)` | ✅ |
| ADR de las decisiones aprobadas | `docs/decisions/`: ADR-001 a ADR-030 e índice por ejes de §5 | ✅ |
| README con instrucciones de instalación | `README.md` | ✅ |
| CI en verde | `.github/workflows/ci.yml`, ejecución `43739617067`: Ubuntu y Windows en success | ✅ |
| Commit limpio | `36377fd` publicado en `origin/main`; árbol de trabajo limpio | ✅ |
| Documento de la propuesta excluido | `Propuesta_Proyecto_Final_*.docx` ignorado por `.gitignore`; no figura en el repositorio | ✅ |

**Incidencias durante el cierre:**

- El primer push fue rechazado porque el token de GitHub no tenía el permiso `workflow`. El autor
  actualizó el token y el push se repitió.
- Por decisión del autor, el primer repositorio se eliminó y se creó de nuevo para retirar la
  línea de coautoría de la IA del commit inicial. El contenido del commit no cambió.

**Revisión posterior al cierre (completada, 2026-11-15):** el autor revisó la justificación
provisional de ADR-027 (descarte del aprendizaje supervisado). Se mantiene la decisión de usar
un algoritmo genético con codificación directa; la justificación se precisó y la nota
provisional se eliminó. No afecta a los criterios de cierre de F0.

## F1: Núcleo de simulación + P0

- **Inicio:** 2026-11-15, con autorización expresa del autor tras revisar el plan.
- **Cierre:** 2026-11-15.
- **Estado:** ✅ Cerrada. El criterio de rendimiento se cumple por la alternativa prevista en
  ADR-024: P0 da FAIL y existe un plan de optimización documentado y aprobado por el autor.
- **Último commit de código y evidencia:** `99c1b2a` (`docs(pilot): record P0 results and
  optimization plan`), autor único `AndresGoGutierrez`; CI `43745456173`: Ubuntu y Windows en
  success. Cada tarea T0–T14 se publicó en commits propios (T14 en tres: código, corrección de la
  procedencia y evidencia), todos con CI en verde.
- **Fuera del alcance:** visor (F2), estadística (F3), calibración (F4), red neuronal y ablación
  (F5), algoritmo genético, fitness, ejecución en paralelo y threadpoolctl (F6), variantes de
  oponentes y diagnósticos X2 (F7–F8).

**Decisiones de planificación aprobadas:**

| ID | Decisión |
|---|---|
| A1 | Las pruebas de determinismo se llaman DET-1…DET-6; catálogo en `docs/architecture.md` |
| A2 | K1–K4 son invariantes rígidas; E1, E2 y E5 se evalúan con una función de comprobación (ADR-022) |
| A3 | P0 en F1 mide la simulación en un solo proceso (percepción, decisión, reglas); P0b en F6 mide el forward de la red y la aceleración en paralelo |
| A4 | Umbral de 500 µs verificado con **50 presas, 8 depredadores** y 40 plantas (prueba de esfuerzo, por encima de cualquier escenario experimental); se mantiene la rejilla completa n_prey ∈ {10, 25, 50} × n_pred ∈ {3, 8}; c_step = mediana de 5 repeticiones independientes del tiempo medio por paso |
| A5 | Parámetros provisionales anteriores a P1 (cumplen K1–K4, E1, E2 y E5); P1 los sustituye |
| A6 | `EpisodeRecord` registra lo que piden ADR-014 y ADR-020; los campos de X2 se añadirán sin modificar los existentes |
| A7 | Escritor CSV y procedencia mínimos para la evidencia de P0 |
| — | Un commit por tarea, con verificaciones, push y CI; autor único del repositorio |

**Tareas:** T0 documentación · T1 parámetros · T2 semillas · T3 geometría · T4 estado ·
T5 reglas · T6 interacciones · T7 percepción y acciones · T8 políticas · T9 simulador y
registros · T10 métricas y evaluación · T11 cargador y configuraciones · T12 DET-1, DET-2,
DET-5 · T13 punto de entrada y CLI `run` · T14 P0 · T15 cierre.

| Criterio de cierre (ADR-024) | Evidencia | Estado |
|---|---|---|
| Pruebas de cada regla (movimiento, metabolismo, inanición, emparejamiento, capturas, alimentación, reaparición, terminación) | `tests/unit/domain/test_rules.py`, `test_interactions.py`, `test_state.py` (cola de reaparición) y `test_simulator.py` (terminación y fin anticipado) | ✅ |
| Sensores: continuidad, rangos, longitud 10/7 | `tests/unit/domain/test_perception.py`: esquemas de 10 y 7 entradas, continuidad en el borde de la visión, rangos de las observaciones completas | ✅ |
| Políticas de referencia y sondas ejecutan episodios en A, B y C | `test_simulator.py` (reglas, aleatoria y las cuatro sondas en A, B y C) y `tests/integration/test_cli.py` (`neuroeco run` en A, B y C) | ✅ |
| Métricas, con la identidad vivas + capturadas + muertas de hambre = n | `tests/unit/application/test_metrics.py` y `test_simulator.py` (la identidad en cada paso de cada episodio) | ✅ |
| DET-1, DET-2, DET-5 | `tests/determinism/test_determinism.py`, más una prueba de que la huella del estado detecta diferencias | ✅ |
| c_step ≤ 500 µs con 50 presas y 8 depredadores, o plan de optimización | P0: c_step = 833.0 µs → FAIL (`results/pilots/p0/`); plan de optimización aprobado en `docs/pilot_report.md` | ✅ (por el plan) |
| Comprobaciones generales | `ruff check`, `ruff format --check`, `lint-imports` (3 contratos) y `pytest` (209 pruebas) en verde | ✅ |

**Decisiones del autor en el cierre (2026-11-15):**

- **A4 se mantiene:** la referencia sigue siendo 50 presas y 8 depredadores con el límite de
  500 µs. El criterio no se modifica después de conocer los resultados. La celda 25/8 (escenario C
  provisional, 460.4 µs) es información complementaria y no sustituye a la referencia.
- **Plan de optimización:** O1 aprobada (condicionada a demostrar equivalencia bit a bit con
  pruebas de referencia y DET-1, DET-2 y DET-5); O2 descartada (cambia los valores numéricos);
  O3 aplazada (solo si una medición demuestra beneficio y se garantiza la equivalencia); O4
  aprobada como mejora de la medición, sin cambiar A4 ni su criterio.
- **Momento:** las optimizaciones aprobadas se realizarán antes de P0b (F6). En F1 no se
  incorporan cambios de comportamiento ni ampliaciones de alcance.

**Incidencias durante F1:**

- La procedencia de la primera ejecución de P0 registraba `git_dirty` después de escribir los
  resultados. Se corrigió (`d1b6e57`), se añadió una prueba y P0 se repitió; la ejecución
  anterior no se usa como evidencia, solo como dato de variabilidad.
- La medición de P0 varía mucho entre ejecuciones en la misma máquina (574.3 frente a 833.0 µs en
  la referencia con episodios idénticos). El veredicto no depende de ello.
- La primera versión del informe de P0 afirmaba que O2 no cambiaba ningún resultado. Una
  comprobación numérica mostró que era falso en coma flotante; el informe se corrigió en el
  cierre.
- El autor revisó una posible discrepancia en A4 (referencia 25/8 frente a 50/8). La revisión
  confirmó que el plan aprobado fija 50/8 por ajuste expreso del autor; no hubo cambio de
  criterio.
- Un push falló por un corte de red (resolución de DNS) y se repitió; desde entonces el proceso
  se detiene si el push falla.

**Pendiente para fases posteriores:** O1 y O4 antes de P0b (F6); la fecha de entrega y las horas
de cómputo disponibles, necesarias para P3 (F6).

## F2: Visualización

- **Inicio:** 2026-11-15, con autorización expresa del autor tras revisar el plan.
- **Cierre:** 2026-11-15, tras la verificación visual del autor en su equipo.
- **Estado:** ✅ Cerrada. Todos los criterios de ADR-024 y las condiciones del autor cumplidos.
- **Último commit de código:** `08eeba7` (`feat(cli): add view command with HUD, inspector and
  session record`), autor único `AndresGoGutierrez`; CI `43752395964`: Ubuntu y Windows en
  success, 273 pruebas en cada sistema, sin omitidas.
- **Fuera del alcance:** estadística (F3), activaciones en el inspector y política neuronal
  (F5), `RunStore` y manifest de ejecuciones formales (F6), figuras (F3, F8).
- **Restricciones:** sin cambios en el comportamiento del simulador de F1, en `domain`, en
  `application/evaluation` ni en las métricas; sin dependencias nuevas; DET-1…DET-6 intactos.

**Decisiones aprobadas (detalle en [ADR-031](decisions/ADR-031-viewer-integration.md)):**

| ID | Decisión |
|---|---|
| V1 | El visor es un observador síncrono sobre `on_step`; recibe copias de solo lectura |
| V2 | Registro JSON por sesión en `runs/view/<fecha-hora UTC>-<id>/session.json`, fuera de git, escrito antes de empezar y completado al terminar, también si se interrumpe |
| V3 | `--set` se registra en `view`; `run` no cambia |
| V4 | Variables del inspector según ADR-031; activaciones en F5 |
| V5 | Contenido del HUD según ADR-031 |
| V6 | Controles: pausa, avance de un paso, velocidad, selección por clic y salida con Esc; sin cambios de parámetros durante la sesión |
| V7 | S₀ se reconstruye con flujos independientes de la misma identidad de semillas |
| V8 | Contrato de import-linter: pygame solo en `presentation` |
| V9 | Las capturas de comprobación no se versionan |

**Tareas:** T0 documentación · T1 datos de sesión · T2 inspector y selección · T3 visor ·
T4 registro de la sesión · T5 comando `view` · T6 verificación visual · T7 cierre.

**Commits:**

| Tarea | Commit | CI (Ubuntu y Windows) |
|---|---|---|
| T0 documentación, ADR-031 y contrato V8 | `879c461` | `43750657089` ✅ |
| T1 datos de sesión | `4f8d5c7` | `43750925887` ✅ |
| T2 inspector y selección | `6bba2c8` | `43751202616` ✅ |
| T3 visor | `eedf548` | `43751820194` ✅ |
| T4 registro de la sesión | `ed34f15` | `43752086288` ✅ |
| T5 comando `view` | `08eeba7` | `43752395964` ✅ |
| T6 verificación visual | Sin commit (capturas no versionadas, V9) | — |

| Criterio de cierre (ADR-024 y condiciones del autor) | Evidencia | Estado |
|---|---|---|
| Hash con visor = hash sin visor, por paso | `tests/determinism/test_viewer_noninterference.py`: visor real (driver `dummy`) en A, B y C con políticas por reglas y aleatoria; hash SHA-256 del estado idéntico en cada paso y métricas idénticas | ✅ |
| Dibujar no modifica el estado | `test_drawing_does_not_modify_the_state` (hash del mundo antes y después de dibujar con un agente seleccionado) | ✅ |
| Pausar y avanzar pasos no alteran la trayectoria | Prueba de hashes con una secuencia guionizada: pausa en S₀, avances de un paso, reanudación, nueva pausa y cambios de velocidad | ✅ |
| Seleccionar agentes no interfiere con la simulación | La misma prueba, con clics en una presa, en un depredador y en una zona vacía durante el episodio | ✅ |
| Las políticas aleatorias conservan exactamente sus resultados | La misma prueba con la política aleatoria en ambas especies | ✅ |
| `view` y `run` producen los mismos hashes y métricas con la misma configuración | `tests/integration/test_view_command.py`: los comandos reales `run` y `view` con los mismos argumentos dan hashes por paso idénticos y las mismas métricas | ✅ |
| Inspector = traza, respetando S_t (observaciones) y S_t+1 (estado tras el paso) | `tests/unit/application/test_session.py`: comparación exacta, agente por agente y paso a paso, de entradas con nombre, salida, acción decodificada, energía, posición, rumbo y aplicación de la acción (incluye muertos en el mismo paso y muertos antes) | ✅ |
| `--set` registrado: sobrescrituras literales, hash de configuración, semillas y procedencia | `tests/unit/presentation/test_view_record.py` y `test_view_command.py`: registro con estado `running` antes del primer paso, procedencia capturada antes de escribir nada, JSON estricto y escritura atómica | ✅ |
| Una sesión cerrada anticipadamente queda registrada | `test_view_command.py`: estados `closed` (con el paso alcanzado), `interrupted` y `error` | ✅ |
| Las 209 pruebas de F1 siguen pasando; visor comprobado con el driver `dummy` en Ubuntu y Windows | 273 pruebas en verde en ambos sistemas (CI `43752395964`); el código de F1 (`domain`, `application/evaluation`, métricas, semillas, `launcher`, `bootstrap`) y `uv.lock` no cambiaron desde `9344ee2` | ✅ |
| Verificación visual manual del autor | Escenarios A, B y C comprobados por el autor en su equipo (2026-11-15): pausa, avance, velocidad, selección, inspector, HUD, salida y registro. Antes, revisión de capturas de A (S₀ y paso 80), B (paso 120) y C (paso 60) generadas con el driver `dummy` | ✅ |
| Comprobaciones generales | `ruff check`, `ruff format --check`, `lint-imports` (4 contratos) y `pytest` (273 pruebas, 13 de determinismo) en verde | ✅ |

**Sensibilidad de las pruebas:** se comprobó fuera del repositorio que la prueba de hashes falla
si los fotogramas compartieran memoria con el estado y el dibujo escribiera en él (1e-9 en una
posición), y que el contrato V8 detecta un módulo temporal de `infrastructure` que importa
pygame.

**Incidencias durante F2:**

- Una prueba de T2 contenía una aserción vacía (`... or True`); se detectó al revisar y se
  sustituyó por una comprobación real antes del commit.
- Dos defectos de formato del panel detectados por las pruebas antes del commit: la línea de
  aplicación de la acción se confundía con las entradas y la ayuda no cabía en el panel.
- Ningún fallo de push ni de CI.

**Observación para fases posteriores:** el inspector muestra `-0.0000` cuando una componente es
un cero negativo (p·cos φ con p = 0); se conserva porque reproduce la traza tal cual.

## F3: Estadística

- **Inicio:** 2026-11-15, con autorización expresa del autor tras revisar el plan.
- **Cierre:** 2026-11-15.
- **Estado:** ✅ Cerrada. Todos los criterios de ADR-024 y las condiciones del autor cumplidos.
- **Último commit de código:** `09563e3` (`test(analysis): add Monte Carlo coverage protocol of
  ADR-032`), autor único `AndresGoGutierrez`; CI `43765852368`: Ubuntu y Windows en success,
  438 pruebas en cada sistema, sin omitidas.
- **Fuera del alcance:** lectura de CSV, tablas y figuras (`analysis/report.py`, F8); regla de
  uso del confirmatorio según R y redacción de conclusiones (F7, F8); generalización y
  diagnósticos (F8); Δ y θ numéricos (F6, F7); área bajo la curva de validación (F6).
- **Restricciones:** `analysis` aislada (no importa `domain`, `application`, `infrastructure`
  ni `presentation`); sin cambios en el código de F1 y F2 ni en `uv.lock`; sin dependencias nuevas.

**Decisiones aprobadas (detalle en [ADR-032](decisions/ADR-032-statistical-implementation.md)):**

| ID | Decisión |
|---|---|
| S1 | De ADR-014, F3 implementa BCa de la media pareada, desviación estándar e IQR |
| S2 | Prevalecen los ADR sobre la ronda de diseño B4.4: prueba de signo sin condicionar, por escenario; sin rank-biserial |
| S3 | δ de Cliff con IC BCa sin emparejar (ADR-020 A6) |
| S4 | Protocolo Monte Carlo de cobertura: 32 configuraciones confirmatorias y 9 informativas; N = 10 000 (id 41: N = 2 000, informativa); umbral L − 3·SE |
| S5 | Numeradores enteros, p-valores `Fraction`, Holm exacto |
| S6 | BCa con 9999 remuestreos por defecto, 95 %, generador proporcionado por quien llama |
| S7 | IQR con cuantiles lineales (tipo 7); desviación estándar con `ddof=1` |
| S8 | θ y G_θ en F3; área bajo la curva en F6 |
| S9 | Registro en ADR-032 |

**Tareas:** T0 documentación · T1 datos por ejecución · T2 signo, IC y Holm · T3 Wilcoxon y
Hodges-Lehmann de una muestra · T4 dos muestras · T5 reglas de C2 · T6 bootstrap y variabilidad ·
T7 cobertura · T8 cierre.

**Commits:**

| Tarea | Commit | CI (Ubuntu y Windows) |
|---|---|---|
| T0 ADR-032, plan y estado | `cbcfcd1` | `43763385687` ✅ |
| T1 datos por ejecución | `fc327ff` | `43763618490` ✅ |
| T2 signo, IC y Holm | `6085a82` | `43763857994` ✅ |
| T3 Wilcoxon y Hodges-Lehmann de una muestra | `fc23efe` | `43764078291` ✅ |
| T4 dos muestras | `5cd83bd` | `43764327137` ✅ |
| T5 reglas de C2 | `a9b039b` | `43764559573` ✅ |
| T6 bootstrap y variabilidad | `fb0a489` | `43764960630` ✅ |
| T7 cobertura | `09563e3` | `43765852368` ✅ |

| Criterio de cierre (ADR-024 y condiciones del autor) | Evidencia | Estado |
|---|---|---|
| Pruebas de ADR-017 | `tests/unit/analysis/test_sign_and_holm.py`: p exactos 2/256, 18/256, 22/1024 y 112/1024 (igualdad de `Fraction`); niveles del IC n = 6…10; dualidad prueba-IC con datos enteros con ceros y empates, n = 6…12 (14 000 casos); acuerdo con scipy; Holm (ejemplo de libro, monotonía, m fijo). `test_one_sample_sensitivity.py`: Wilcoxon exacto (scipy sin empates, enumeración ingenua con empates y ceros), Hodges-Lehmann de una muestra (niveles, equivariancia, dualidad). `test_run_data.py`: rechazo de `run_id` repetidos | ✅ |
| Pruebas de ADR-013 | `test_two_sample.py`: separación total 6×6 → 2/924; scipy sin empates y enumeración ingenua con empates y censura; [D₍₆₎, D₍₃₁₎] al 443/462; equivariancia, antisimetría y dualidad; δ de Cliff (±1, antisimetría, 2U/mn − 1). `test_c2_rules.py`: tabla de no inferioridad con fronteras, aviso de IQR, θ y G_θ con censura | ✅ |
| Pruebas de ADR-014 y δ de Cliff con BCa (S1, S3) | `test_bootstrap.py`: BCa de la media pareada idéntico a scipy, misma semilla → mismo IC, datos constantes "no estimable" sin excepciones ni avisos, δ de Cliff por rangos igual a la definición por pares (con empates), desviación estándar con ddof = 1; IQR tipo 7 en `test_c2_rules.py` | ✅ |
| Cobertura confirmatoria (id 1–32) ≥ L − 3·SE | `tests/stats/test_coverage.py`: las 32 configuraciones por encima de su umbral (tabla siguiente) | ✅ |
| Cobertura informativa (id 33–41) documentada | Tabla siguiente | ✅ |
| Pruebas anteriores intactas; CI en Ubuntu y Windows | 438 pruebas en verde (las 273 previas, sin cambios); sin cambios en `domain`, `application`, `infrastructure`, `presentation`, `launcher`, `bootstrap`, `configs`, `pyproject.toml` ni `uv.lock` desde `2458885` | ✅ |

**Resultados de cobertura** (primera ejecución del protocolo de ADR-032, en local; N = 10 000
salvo id 41). En CI las mismas pruebas pasaron en Ubuntu y Windows; el log no muestra los valores
porque pytest captura la salida:

| id | Configuración | n = 6 | n = 7 | n = 8 | n = 9 | n = 10 |
|---|---|---|---|---|---|---|
| | Nivel L del IC por signos | 0.96875 | 0.98438 | 0.99219 | 0.96094 | 0.97852 |
| | Umbral L − 3·SE | 0.96353 | 0.98065 | 0.98955 | 0.95513 | 0.97417 |
| 1–5 | Signos, Normal(0.4, 1) | 0.96720 | 0.98510 | 0.99320 | 0.95850 | 0.97860 |
| 6–10 | Signos, Exponencial(1) | 0.96990 | 0.98490 | 0.99180 | 0.96060 | 0.97790 |
| 11–15 | Signos, round(Normal(0.3, 2)) | 0.98820 | 0.99510 | 0.99710 | 0.98900 | 0.99430 |
| 16–20 | Signos, Poisson(3) − 3 | 0.99120 | 0.99770 | 0.99930 | 0.99250 | 0.99700 |
| | Nivel L de Hodges-Lehmann (una muestra) | 0.96875 | 0.95312 | 0.96094 | 0.96094 | 0.95117 |
| | Umbral L − 3·SE | 0.96353 | 0.94678 | 0.95513 | 0.95513 | 0.94471 |
| 21–25 | Hodges-Lehmann, Normal(0.5, 1) | 0.96840 | 0.94980 | 0.96520 | 0.95550 | 0.95110 |
| 26–30 | Hodges-Lehmann, Laplace(0.5, 1) | 0.96930 | 0.95260 | 0.96330 | 0.95940 | 0.94910 |
| 33–37 | *Informativa:* Hodges-Lehmann, Uniforme{−2, …, 4} | 0.98940 | 0.97610 | 0.97850 | 0.98280 | 0.97980 |

| id | Configuración | Nivel L | Umbral | Cobertura | SE | Resultado |
|---|---|---|---|---|---|---|
| 31 | Hodges-Lehmann 6×6, Normal, Δ = 0.7 | 0.95887 | 0.95292 | 0.95910 | 0.00199 | ✅ |
| 32 | Hodges-Lehmann 6×6, Exponencial, Δ = 0.7 | 0.95887 | 0.95292 | 0.95900 | 0.00199 | ✅ |
| 38 | *Informativa:* Hodges-Lehmann 6×6, Poisson, Δ = 1 | 0.95887 | — | 0.98690 | 0.00199 | Documentada |
| 39 | *Informativa:* BCa media pareada, Normal(0.3, 1), n = 50 | 0.95 | — | 0.94230 | 0.00218 | Documentada |
| 40 | *Informativa:* BCa media pareada, Exponencial − 0.7, n = 50 | 0.95 | — | 0.93300 | 0.00218 | Documentada |
| 41 | *Informativa:* BCa δ de Cliff, 50×50, N = 2 000 | 0.95 | — | 0.95600 | 0.00487 | Documentada |

Las 32 confirmatorias superan su umbral. Con datos discretos, el IC por signos y Hodges-Lehmann
resultan conservadores, como se esperaba. El BCa de la media pareada cubre algo menos del
nominal con n = 50 (0.942 y 0.933 con asimetría); es informativo y no decide, pero conviene
tenerlo presente al interpretar los intervalos de nivel de episodio (F8).

**Duración de las pruebas** (`pytest` completo, 438 pruebas): local 3 min 22 s; CI Ubuntu
3 min 26 s; CI Windows 5 min 56 s (antes de F3: unos 12 s y 23 s). El id 41 tardó 119 s en
local, más que los ≈ 80 s estimados en ADR-032; no cambia ningún parámetro del protocolo.

**Incidencias durante F3:**

- El plan afirmaba que el paquete `analysis` no existía; existía su `__init__.py` desde F0. Se
  conservó intacto y T1 solo añadió `stats.py`.
- Antes del commit de T0 se corrigieron dos fracciones de ADR-032 (colas de Hodges-Lehmann
  para n = 8 y 9) verificadas por enumeración; los niveles decimales ya eran correctos.
- Las pruebas de cobertura generaban dos avisos de pytest (generadores en `parametrize`); se
  convirtieron en listas tras la primera ejecución, sin cambiar parámetros, semillas ni
  resultados (comprobado con una segunda ejecución idéntica).
- Ningún fallo de pruebas, push ni CI.
