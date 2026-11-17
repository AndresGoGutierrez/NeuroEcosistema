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

## F4: P1, calibración ecológica

- **Inicio:** 2026-11-15, con autorización expresa del autor limitada a T0; después, T0b, T1, T2,
  T3, T3b, T3c y T4 (en los incrementos I1–I4), cada una autorizada por separado.
- **Estado:** 🔄 En curso. T0, T0b, T1, T2, T3 y T3b aprobadas por el autor (T2, T3 y T3b tras
  una auditoría, con observaciones); T3c (correcciones de la auditoría de T3b) completada y
  validada en las comprobaciones automáticas (CI `43797566961` de `bb82864`, correcto en Ubuntu y
  Windows). T4 (evaluación de criterios, comando `pilot p1-criteria` y selección de P1-17)
  completada y validada en las comprobaciones automáticas (CI `43807682418` de `85c42af`,
  correcto en Ubuntu y Windows, 802 pruebas), pendiente de la revisión del autor. T4b
  (verificador de la secuencia, D-T4b-1 a D-T4b-4) completada (CI `43810435648` de `42bce95`,
  correcto, 836 pruebas). T4c (rondas de ajuste de las reglas, A_rev e integración del
  verificador en `pilot p1`, D-T4c-1 a D-T4c-6) completada en C1–C3 (CI `43818450043` de
  `eaf128b`, correcto en Ubuntu y Windows, 885 pruebas). La auditoría de T4–T4c no encontró
  hallazgos críticos; sus hallazgos importantes se resuelven en T4d (autorizada, en curso). T5 y
  la ejecución de episodios reales de P1 no están autorizadas.
- **Criterio de cierre (ADR-024):** criterios de ADR-020 (clase A completa en la confirmación;
  cada B cumplido o aceptado mediante ADR; cada C investigado y documentado), `p_flee` y
  `u_cruise` ajustados y congelados (ADR-012) y etiqueta `env-frozen-v1`.
- **Fuera del alcance:** redes, ablación y activaciones (F5); optimizaciones O1 y O4, P0b y
  algoritmo genético (F6); variantes de oponentes como evaluación y diagnósticos X2 (F7, F8).
- **Restricciones:** sin redes en P1; sin cambios en el comportamiento del núcleo de F1, en las
  métricas ni en el esquema de semillas; sin dependencias nuevas ni cambios en `uv.lock`; sin
  modificar ADR aprobados; semillas, tamaños, tolerancias y umbrales fijados antes de ver datos;
  ningún episodio descartado; única excepción en código cerrado: la prueba de P1-2 (cualquier
  otra prueba cerrada que falle al congelar obliga a detenerse y consultar, P1-23).

**Decisiones (detalle en [ADR-033](decisions/ADR-033-p1-operational-definitions.md)):**

| ID | Decisión | Estado |
|---|---|---|
| P1-1 | Clave de semilla del bootstrap calculada por la aplicación y registrada en CSV; `analysis` reconstruye el generador | Aprobada |
| P1-2 | Sustitución, en el congelamiento, de la prueba de F1 que fija los valores provisionales | Aprobada |
| P1-3 | Definición operativa de A4 | Aprobada |
| P1-4 | Rejillas `p_flee` ∈ {0.2, 0.3, 0.4, 0.5} y `u_cruise` ∈ {0.3, 0.5, 0.7}; todas las combinaciones registradas; empates por un orden fijo | Aprobada |
| P1-5 | 30 episodios por escenario en calibración; confirmación con 50 semillas nuevas | Aprobada |
| P1-6 | Etapa A: `plant_energy` y `regrow_delay`, después `n_plants`; sin cambiar geometría ni especies | Aprobada |
| P1-7 | B2: diferencia media pareada reglas − aleatoria > 0; BCa descriptivo | Aprobada |
| P1-8 | Lotes con `n_predators = 0` en A y B | Aprobada |
| P1-9 | C4: menos de una captura media por episodio | Aprobada |
| P1-10 | `application/calibration.py` y `analysis/calibration.py` | Aprobada |
| P1-11 | Valores congelados en un ADR nuevo | Aprobada |
| P1-12 | `env-frozen-v1` solo al final y con autorización expresa | Aprobada |
| P1-13 | `seed_group` 10–12 (calibración), 20–22 (confirmación), 30–32 (segunda confirmación); claves completas en cada fila; pruebas con grupos ≥ 1000; confirmación protegida por una opción explícita | Aprobada (T0b, D16) |
| P1-14 | 35 condiciones por bloque (reglas, aleatorias, 8 sondas, sin depredadores) | Aprobada (T0b) |
| P1-15 | Criterios sin escenario nombrado: en cada escenario; A3 con las dos métricas primarias | Aprobada (T0b, D5) |
| P1-16 | Fórmula exacta de cada criterio A, B y C; reglas de agregación; A4 b1 y b2; A6 con IC degenerado; B3 con censura; B5 literal; B6 con `steps` = t_max | Aprobada (T0b, D1–D4, D6, D12, D14) |
| P1-17 | Rejilla por especie, objetivos y orden de desempate | Aprobada (T0b) |
| P1-18 | Máquina de estados (lectura L1): iteraciones de un parámetro, ≤ 5 por etapa, ≤ 3 rondas, ≤ 3 alternancias, sin retorno desde B o C | Aprobada (T0b, D7–D10) |
| P1-19 | Registro previo de cada iteración, publicado antes de ejecutarla; código de evaluación congelado | Aprobada (T0b) |
| P1-20 | Claves del bootstrap; evaluación de entrada con `run = 0`; claves ANALYSIS 10, 20 y 30 reservadas | Aprobada (T0b, D15) |
| P1-21 | Confirmación con autorización expresa; repetición solo por fallo de infraestructura | Aprobada (T0b, D11, D18) |
| P1-22 | Comprobador A2 con S₀ reconstruido (V7) y prueba de hashes por paso | Aprobada (T0b) |
| P1-23 | Pruebas cerradas que fallen al congelar: detenerse y consultar | Aprobada (T0b, D13) |
| P1-24 | `run` y `view` solo con el grupo 0; observaciones citadas en el registro previo | Aprobada (T0b, D17) |

**Procedimiento de calibración** (máquina de estados de ADR-033, P1-18):
K → A_eval ⇄ A_ajuste → T (rondas) ⇄ A_rev → T_fin → B_eval → C_eval → E → AUT → CONF.
No se vuelve de B o C a A; agotar un presupuesto detiene F4 y obliga a consultar al autor.

**Tareas previstas:** T0 documentación · T0b corrección de ADR-033 tras la auditoría · T1
especificación y cargador de P1 · T2 comprobador A2 y ejecución por bloques · T3 comando
`pilot p1` · **T3b correcciones de la auditoría de T3** · **T3c correcciones de la auditoría de
T3b** · T4 evaluación de criterios desde CSV · **T4b verificador de la secuencia de calibración** · **T4c ejecución de las rondas de la rejilla** · T5… iteraciones de calibración ·
confirmación (con autorización expresa) · congelamiento (P1-2, ADR de valores, etiqueta) · cierre.

**T4c (decisión T3-2 del autor; implementada en C1–C3):** ejecución de las rondas de ajuste de las reglas
(P1-17): la rejilla de la presa, la selección de su ganador con los objetivos y el orden de
desempate de P1-17 a partir de los CSV (lo que implementa T4), la rejilla del depredador con ese
ganador y la reevaluación A_rev. Va después de T4 porque necesita la selección sobre resultados;
T3 no ejecuta rondas.

Decisiones del autor para T4c (aprobadas antes de implementar; incrementos C1 rejillas, C2
A_rev, C3 verificador e integración):

| ID | Decisión del autor |
|---|---|
| D-T4c-1 | A_rev no tiene `bootstrap_keys.csv`: P1-20 no define una clave para A_rev. B2 conserva su veredicto (suma pareada, P1-7) y su BCa descriptivo figura como no calculado. ADR-033 no cambia |
| D-T4c-2 | Sin `rounds/RR_rev.yaml`: los valores de A_rev se derivan automáticamente de los ganadores publicados de las dos rejillas (la anterioridad la dan `RR.yaml` y el commit de las rejillas) |
| D-T4c-3 | Las rondas son un modo aditivo de `pilot p1` (`--round RR --phase prey\|predator\|reevaluation`) que reutiliza todas las protecciones de T3–T3c |
| D-T4c-4 | En la rejilla de la presa se vuelve a ejecutar la combinación vigente y sus filas deben coincidir con las de `rules` en A de la evaluación anterior; cualquier discrepancia detiene la ronda |
| D-T4c-5 | El verificador de T4b se integra en las comprobaciones previas de `pilot p1` en C3: ninguna ejecución empieza si la secuencia no lo permite |
| D-T4c-6 | Se mantiene el esquema `/1` con los valores nuevos de `stage` `round_prey`, `round_predator` y `A_rev` (cambio aditivo, Mn-8), comprobando la compatibilidad con los consumidores existentes |

**Modificación expresamente autorizada de una prueba de una fase cerrada (T4c, alternativa (a)
del autor):** `tests/architecture/test_pilot_p1_imports.py` (T3) prohibía que `pilot_p1.py`
importara `neuroeco.analysis`. D-T4c-5 (verificar la secuencia antes de ejecutar) y D-T4c-2 (la
selección de P1-17 en las rondas) necesitan esa dependencia, así que la prueba solo conserva la
prohibición de pygame. El comando sigue sin calcular criterios mientras se ejecutan los
episodios. Ninguna otra prueba ni contrato de arquitectura cambia.

**Alcance de la puerta de D-T4c-5 (decisión del autor en C3, alternativa (a)).** Integrar el
verificador siempre activo habría invalidado 22 pruebas aprobadas de T3–T3c
(`test_pilot_p1_command.py` y `test_pilot_p1_protections.py`), que ejecutan cadenas sintéticas
sin criterios y con transiciones que P1-18 prohíbe (A → B sin ronda) para probar las
protecciones. El autor decidió:

- La puerta es **obligatoria** en toda especificación con algún grupo de semillas menor que
  1000, incluidos los reales de P1-13 (10–32); solo están exentas las especificaciones
  sintéticas de las pruebas, con todos sus grupos ≥ 1000 (D16), que conservan el comportamiento
  de T3–T3c. Las 22 pruebas no cambian.
- No existe ninguna opción para saltarla; cada episodio toma su grupo de la especificación y el
  plan se comprueba de forma independiente, así que no se puede eludir cambiando la
  especificación.

Implementación (C3):

- `pilot p1` construye los pasos como `pilot p1-sequence` y exige que el bloque sea el paso
  pendiente con una transición `allowed`. La puerta va después de la secuencia estática y antes
  de las demás comprobaciones de resultados. Un rechazo queda en la fase `preflight`, con
  `P1RefusalError` y `failure.json`, sin episodios. La verificación se registra en el campo
  aditivo `sequence_gate` de la procedencia, y los archivos leídos entran en `input_files`.
- La confirmación exige la secuencia completa con la entrada publicada y la clase A cumplida
  (`author_authorization_required`), además de `--author-authorized`. La segunda confirmación
  se rechaza siempre, porque P1-18 no tiene ese estado sin un flujo de recalibración aprobado
  (Mn-7, que ya la declaraba inalcanzable).
- *(Sustituido en T4d por las decisiones de D-T4d-3; la opción ya no existe.)* `pilot p1`
  aceptaba `--d9-confirmed N`: la misma confirmación de la vía E5 de D9 que D-T4b-4 ya
  aprobó para `pilot p1-sequence`. Sin ella la vía E5 sería inalcanzable en un experimento
  real. Solo afecta a esa regla y no omite ninguna otra comprobación.
- D-T4b-1 queda cumplida: el verificador está integrado antes de T5. D-T4b-2 queda superada: lo
  que sigue a una ronda ya se verifica y el veredicto "no verificable" desapareció.

**T4d (resolución de la auditoría de T4–T4c, antes de T5).** La auditoría no encontró ningún
camino para ejecutar un paso real no permitido, pero sí cuatro huecos del proceso (I-1 a I-4).
Decisiones del autor:

| ID | Decisión del autor |
|---|---|
| D-T4d-1 | Con grupos no sintéticos, una violación A2, una `InitializationError`, un intento sin registro reconocible o un directorio parcial en cualquier destino de P1 producen **STOP definitivo** desde la herramienta mientras no exista un procedimiento de recuperación aprobado. Se conservan `failure.json`, la procedencia fallida y su registro de A2; los CSV de un bloque fallido se siguen borrando (T3-4). Los fallos de infraestructura siguen siendo repetibles. El texto correspondiente de T3c en el diccionario de datos se precisa con autorización expresa |
| D-T4d-2 | Todas las iteraciones comparten la misma versión del código de simulación, del código de análisis y del entorno (huellas SHA-256, sin datos personales ni identidad física de la máquina); cualquier diferencia es STOP. La versión del sistema operativo forma parte del entorno: las actualizaciones se pausan durante P1. El procedimiento de reevaluación de P1-19 (versiones nuevas de criterios en directorios nuevos, sin sobrescribir los originales, procesando todos los bloques y con autorización previa) queda **aprobado pero aplazado**: mientras no se implemente, un cambio del código de análisis después de la primera iteración es STOP |
| D-T4d-3 | Las decisiones del autor se registran en `configs/pilots/p1_decisions/NNN.yaml` (esquema estricto `neuroeco.p1-decision/1`), vinculadas por SHA-256 al paso que autorizan y al bloque y criterios que juzgan: `b_criteria` (continuar o repetir la etapa con criterios B incumplidos, D-T4b-3), `entry_review` (una decisión por **cada** fila B y C de la evaluación de entrada) y `d9_e5` (vía E5 de D9). Sustituyen a `--d9-confirmed`, que desaparece (cambia el mecanismo de D-T4b-4, con autorización del autor); las dos pruebas de T4c que lo usaban se sustituyen por otras más estrictas |
| D-T4d-4 | `results/pilots/p1/RESERVED.json` declara la raíz de resultados reales, fija el SHA-256 de la especificación aprobada y las huellas de referencia, y se crea en T5-0. Bajo esa raíz solo se admite la tabla aprobada, comprobado antes de escribir nada. `neuroeco view` y `pilot p0` (F1–F2, cerradas) no se modifican: no pueden sobrescribir ningún archivo de P1, y lo que añadan se detecta (árbol limpio o contenido inesperado). La prueba de T4c que llega a la ejecución con grupos reales crea un marcador en su directorio temporal |
| D-T4d-5 | Incrementos con push y CI correcto en Ubuntu y Windows antes de continuar. La prueba de extremo a extremo sustituye solo el veredicto S_X en la prueba, sin alterar filas. M-2 se incorpora; M-5 se aplaza |

**T4 (evaluación de los criterios desde los CSV; detalle en
[p1_data_dictionary.md](p1_data_dictionary.md)).** `analysis/calibration.py` (P1-10) lee un
bloque publicado, verifica su integridad (SHA-256 de `result_files`, bloque completo sin
violación A2, claves de P1-13 y P1-20, recuentos coherentes) y calcula todos los criterios de
P1-16 con aritmética exacta (D14), solo para los escenarios ejecutados (P1-18), además de S_A,
S_B, S_C y la clase A completa. A6 usa el BCa sin emparejar con la regla {−1} de D1 y B2 un BCa
solo descriptivo, ambos con el generador reconstruido de `bootstrap_keys.csv`, idéntico al de
`SeedRegistry`. `analysis` no importa otras capas: el contrato de archivos se replica y una
prueba lo mantiene igual al de `application` y del comando.

| ID | Decisión del autor |
|---|---|
| D1 | Subcomando independiente `neuroeco pilot p1-criteria --result <dir>`, que escribe `criteria.csv` y `criteria_provenance.json` dentro del bloque; mismas comprobaciones de git que `pilot p1`, con los archivos del bloque evaluado como únicos sin versionar admitidos (resultados y criterios en un solo commit, P1-19); sin sobrescritura salvo salida idéntica |
| D2 | En C4, "Σ muertes" son solo las de presas: capturadas más muertas de inanición |
| D3 | El BCa descriptivo de B2 usa las métricas primarias de ADR-014: diferencia de supervivencia (presa) y de fracción capturada (depredador) |
| D4 | La selección del ganador de P1-17 forma parte de T4 como función pura (`select_prey`, `select_predator`); su ejecución corresponde a T4c |
| D5 | Un commit por incremento; publicación y CI solo en los hitos I2 e I4 |

Selección de P1-17: objetivo entero (Σ numeradores de supervivencia de la presa; Σ capturas del
depredador) sobre los episodios `rules` de A con un solo grupo de semillas; se registran los
totales de todas las combinaciones (P1-4); empates exactos: combinación vigente, menor
`u_cruise`, menor `p_flee`. Una rejilla incompleta, con episodios duplicados o distintos entre
combinaciones, con valores fuera de la rejilla o con otros parámetros cambiados detiene la
selección.

**Decisiones de T3 (aprobadas por el autor; detalle en
[p1_data_dictionary.md](p1_data_dictionary.md)):**

| ID | Decisión |
|---|---|
| T3-1 | Modos `--iteration`, `--entry-evaluation`, `--confirmation` y `--second-confirmation`; la evaluación de entrada y las confirmaciones toman los valores con `--values-from` de la última iteración registrada, de la etapa C |
| T3-2 | Las rondas de la rejilla quedan fuera de T3 (tarea T4c) |
| T3-3 | `results/pilots/p1/<bloque>/<iteration_NNN \| entry \| evaluation>/`, sin sobrescritura |
| T3-4 | Un error deja `<destino>.failed-<UTC>-<id>/` con `failure.json` y, si ya existía, `provenance.json`; ningún CSV parcial ni resultado definitivo |
| T3-5 | Árbol de git limpio obligatorio, sin opción para saltarlo; las pruebas simulan el resultado de la comprobación |
| T3-6 | Validación estática de la secuencia y estado K antes de cualquier episodio |
| T3-7 | Diccionario de datos en `docs/p1_data_dictionary.md` |
| T3-8 | Comando en `presentation/pilot_p1.py`; en `cli.py`, `storage.py` y `provenance.py` solo añadidos |
| T3-9 | `--author-authorized`, más la comprobación independiente de los grupos de semillas del bloque |

**T3b (correctiva, autorizada por el autor tras la auditoría de T3; detalle en
[p1_data_dictionary.md](p1_data_dictionary.md)):**

| ID | Decisión |
|---|---|
| I-1 | Todo lo que lee el comando (`p1.yaml`, `p0.yaml`, `base.yaml`, `scenarios.yaml`, `baselines.yaml`, especificaciones registradas y resultados exigidos) y `--output-root` deben estar dentro del repositorio y versionados, comprobado con git |
| T3b-1 | Si la especificación declara algún grupo real (10–32), la tabla completa debe coincidir con P1-13 y con los tamaños de P1-5 (30/50/50); los grupos sintéticos ≥ 1000 quedan exentos |
| I-2 | Orden de ejecución: iteración N exige 1 … N−1 completas; la evaluación de entrada, la cadena completa; la confirmación, la evaluación de entrada; la segunda confirmación, una primera confirmación completa con valores de una iteración anterior. Identidad de cada especificación por SHA-256. Ningún criterio se evalúa (T4b) |
| M-1 | `HEAD` igual a su rama remota (`@{u}`), sin `git fetch` |
| M-2 | El plan coincide exactamente (orden, condiciones, `item` y overrides) con el esperado |
| M-4, M-5, M-6 | Procedencia de un fallo sin episodios publicados; git y modo en todo `failure.json`; intentos anteriores registrados; D18 en las confirmaciones |
| M-7 | Pruebas de Ctrl+C e `InitializationError` a través del comando |
| M-8, M-9 | Recuperación de directorios parciales y acreditación de A2, documentadas |
| M-10 | Hasta 5 reintentos del renombrado ante `PermissionError`; en el registro solo `NNN.yaml` y `RR.yaml` |
| T3b-2 | Se mantienen `neuroeco.p1-provenance/1` y `neuroeco.p1-failure/1`: cambios aditivos, sin datos reales previos |

**Procedimiento ante un rechazo en el estado K (P1-18: la candidata rechazada no consume
iteración).** El comando rechaza la candidata antes de ejecutar ningún episodio y deja
`iteration_NNN.failed-…/failure.json` con los valores rechazados, su SHA-256 y el commit. Para
proponer otra candidata:

1. Se confirma (commit) ese registro de fallo.
2. Se modifica el **mismo** `configs/pilots/p1/iterations/NNN.yaml` con la nueva candidata y el
   motivo, en un commit propio, y se publica (push).
3. Se ejecuta de nuevo `--iteration` con ese archivo. El número no cambia y el intento rechazado
   queda en `previous_attempts` y en la historia de git.

Mientras el resultado de NNN no exista, su especificación se puede reemplazar así; una vez
publicado un resultado completo, su SHA-256 queda fijado y cualquier cambio posterior del archivo
impide ejecutar los pasos siguientes.

**T3c (correctiva, autorizada por el autor tras la auditoría de T3b; detalle en
[p1_data_dictionary.md](p1_data_dictionary.md)):**

| ID | Decisión |
|---|---|
| IA-1 | El contenido ejecutado es el del commit: se rechazan las marcas assume-unchanged y skip-worktree, los filtros `clean`/`process` configurados y las referencias `refs/replace/`; **todo** archivo versionado (código incluido) se compara con el árbol real de HEAD mediante `git hash-object`; el paquete `neuroeco` que se ejecuta debe estar en el repositorio; la procedencia registra el SHA-256 de cada archivo leído |
| IA-2 | `failure.json` y la procedencia fallida (con `a2_violation`) se escriben dentro del directorio parcial antes de renombrarlo; el aviso se imprime antes de registrar; un intento con A2 declarada en cualquiera de los dos registros nunca se clasifica como interrumpido |
| IA-3 | `config_files` (SHA-256 de p1.yaml, p0.yaml, base.yaml, scenarios.yaml y baselines.yaml) idénticos en toda la cadena; con los grupos reales, rutas canónicas `configs/pilots/p1.yaml`, `configs/` y `results/pilots/p1` |
| Mn-1 | La rama remota debe estar bajo `refs/remotes/` y su remoto tener URL; la URL se registra sin credenciales |
| Mn-3 | Se rechaza un destino cuyos archivos de resultado o de fallo ignore git |
| Mn-4 | SHA-256 de `episodes.csv` y `bootstrap_keys.csv` en la procedencia, verificados junto con la identidad de cada fila al usarlos como prerrequisito |
| Mn-5 | Salida de git decodificada en UTF-8 (rutas no ASCII en Windows); el `_git` de F1 no cambia |
| Mn-6 | Ninguna iteración nueva si existe la evaluación de entrada o cualquier resultado o intento de confirmación |
| Mn-8 | Los esquemas siguen en `/1` (cambios aditivos); cualquier cambio incompatible futuro sube la versión |

**Decisión operativa Mn-7 (confirmada por el autor en T3c; precisa P1-21 sin modificar
ADR-033):**

- La segunda confirmación requiere una primera confirmación completada.
- Debe usar valores de una iteración posterior a la de la primera confirmación; nunca repite la
  primera con las mismas semillas y valores.
- Una violación A2 impide la segunda confirmación.
- No se permite recalibrar ni repetir la evaluación de entrada después de iniciar la
  confirmación mientras no exista un flujo metodológico expresamente aprobado. Por eso, hoy la
  segunda confirmación es inalcanzable: requiere aprobar antes ese flujo.

**Aspectos del flujo todavía no definidos (requieren decisión del autor antes de usarse):**

- **Flujo de recalibración tras una confirmación (P1-21).** La máquina de estados de P1-18 no
  permite volver de B o C a A, la validación estática rechazaría iteraciones de etapa A después
  de la etapa C y `calibration/entry` no se sobrescribe. El comando bloquea cualquier iteración
  nueva (Mn-6) hasta que el autor apruebe ese flujo.
- **Después de una violación A2** el procedimiento es STOP y consulta al autor (P1-18, P1-22); el
  comando no permite repetir la confirmación afectada ni usarla para una segunda confirmación.

**Riesgos residuales documentados (T3c):**

- **Mn-2, referencia remota local.** Sin `git fetch`, la sincronización se comprueba contra la
  referencia de seguimiento local; moverla a mano (`git update-ref`) haría pasar un commit no
  publicado. Se verifica después: el CI del SHA registrado en `git_commit` debe existir y ser
  anterior a `timestamp_utc`.
- **Remoto propio.** Un remoto con URL local pasa la comprobación; la URL queda registrada en
  `git_checks.remote_url` para revisarla.
- **Ventana de A2 sin registro.** Si el proceso muere entre detectar una violación A2 y escribir
  `failure.json`, el intento parecería interrumpido; el aviso de consola se imprime antes.
- **Entorno de Python.** Se comprueba que el código de `neuroeco` es el del commit, no las
  dependencias instaladas; sus versiones y el SHA-256 de `uv.lock` quedan en la procedencia, y
  `uv.lock` es un archivo versionado comparado con HEAD.

**Pendiente de decisión separada (M-3, no autorizada en T3b ni en T3c):** `plant_energy: 30` y
`plant_energy: 30.0` dan el mismo candidato y la misma física, pero distinto `config_hash`, porque
el hash se calcula sobre el árbol YAML antes de normalizar los tipos y los overrides de T1 usan
`repr` del valor tal como se escribió. La corrección propuesta (escribir los overrides con
`float(...)`) toca código de T1. Mientras tanto, las especificaciones reales deben escribir
`plant_energy` siempre con decimales (por ejemplo, `30.0`).

**T4b (decisión T1-2 del autor):** verificador de las restricciones de la máquina de
estados que dependen de resultados, ejecutado antes de autorizar cada iteración: que S_A, S_B o
S_C se cumplieron o no en la evaluación anterior, las iteraciones "infructuosas" de D9, las
alternancias provocadas por una reevaluación A_rev fallida y que las reglas cambien solo a los
valores ganadores de una ronda. T1 cubre únicamente las comprobaciones estáticas, que no
necesitan resultados.

Implementado en `analysis/sequence.py` y el comando de solo lectura `neuroeco pilot
p1-sequence` (detalle en [p1_data_dictionary.md](p1_data_dictionary.md)), con las decisiones del
autor:

| ID | Decisión del autor |
|---|---|
| D-T4b-1 | Comando independiente; `pilot_p1.py` no cambia. **Antes de autorizar T5 es obligatorio integrar este verificador en las comprobaciones previas de `pilot p1`** |
| D-T4b-2 | Se verifican todas las transiciones posibles con los datos actuales; tras una A con S_A cumplido y r < 3 se exige una ronda; lo que sigue a una ronda (sus resultados, A_rev, las alternancias que provoque y que las reglas cambien a los ganadores) se declara no verificable hasta T4c y nunca se acepta en silencio |
| D-T4b-3 | Con S_B o S_C cumplido y algún criterio B incumplido se admiten otra iteración de la etapa (causa paramétrica) o la etapa siguiente (decisión documentada); el informe indica que es un juicio del autor, no una comprobación automática |
| D-T4b-4 | D9: `n_plants` solo tras dos iteraciones A **consecutivas** infructuosas (S_A incumplido) que cambiaron `plant_energy` o `regrow_delay`; la vía E5 no se deduce y requiere la confirmación explícita y documentada del autor (`--d9-confirmed`; desde T4d, una decisión `d9_e5`, D-T4d-3) |

Los resultados se usan solo si pertenecen a su especificación registrada (SHA-256 de
`values_source`) y si su `criteria.csv` coincide byte a byte con los criterios recalculados.

**Decisiones de T1 (aprobadas por el autor):**

| ID | Decisión |
|---|---|
| T1-1 | Dataclasses de la especificación en `application/calibration.py`; sin cambios en `application/configs.py` |
| T1-2 | Validación estática en T1; la dependiente de resultados, en la tarea T4b |
| T1-3 | Cada especificación de iteración es una instantánea completa de los 8 valores; el validador exige que cambie exactamente el parámetro declarado |
| T1-4 | `configs/pilots/p1.yaml`, `configs/pilots/p1/iterations/NNN.yaml` y `configs/pilots/p1/rounds/RR.yaml` |
| T1-5 | Catálogo de condiciones, presupuestos, límites y parámetros del bootstrap como constantes de código protegidas por pruebas |
| T1-6 | Constructores de claves de episodios (P1-13) y del bootstrap (P1-20) y estado K en T1 |
| T1-7 | Registro en este documento dentro del commit de T1 |

**Commits:**

| Tarea | Commit | CI (Ubuntu y Windows) |
|---|---|---|
| T0 ADR-033 (P1-1 a P1-22), plan y estado | `deb2ac4` | `43771573602` ✅ |
| T0b corrección de ADR-033 tras la auditoría (D1–D18, P1-23, P1-24) | `50c8a1d` | `43774119505` ✅ |
| T0b precisión de P1-13 (columnas de clave) | `e3dcd13` | `43775574419` ✅ |
| T0b precisión de P1-16 (remisión a P1-13) | `38e1803` | `43776616239` ✅ |
| T1 especificación y cargador de P1 | `1bd2c4d` | `43778824799` ✅ |
| T2 comprobador A2 y ejecución por bloques | `85509b0` | `43780607071` ✅ |
| T3 comando `pilot p1` y CSV de episodios y claves | `b53f547` | `43783541818` ✅ |
| T3b correcciones de la auditoría de T3 | `8daa461` | `43790449030` ✅ |
| T3c correcciones de la auditoría de T3b | `e4900ba` | `43795462046` ❌ (Windows; Ubuntu ✅) |
| T3c corrección de la prueba de fin de línea | `bb82864` | `43797566961` ✅ (693 pruebas en Ubuntu y en Windows) |
| T4-I1 criterios deterministas | `17818b5` | Publicado con I2 (`43804513444` ✅) |
| T4-I2 bootstrap, A6 y BCa descriptivo de B2 | `fa8b076` | `43804513444` ✅ (776 pruebas) |
| T4-I3 comando `pilot p1-criteria` | `1b7f786` | Publicado con I4 (`43807682418` ✅) |
| T4-I4 selección de P1-17 y registro de T4 | `85c42af` | `43807682418` ✅ (802 pruebas en Ubuntu y en Windows) |
| T4 cierre documental | `64a4454` | `43808611612` ✅ |
| T4b verificador de la secuencia | `42bce95` | `43810435648` ✅ (836 pruebas) |
| T4c-C1 rejillas de una ronda | `0a0bc02` | Publicado con C2 (`43815758642` ✅) |
| T4c-C2 A_rev | `1446161` | `43815758642` ✅ (847 pruebas en Ubuntu y en Windows) |
| T4c-C3 transiciones tras una ronda (parte 1) | `4f991ca` | Publicado con la parte 2 (`43818450043` ✅) |
| T4c-C3 puerta de la secuencia en `pilot p1` (parte 2) | `eaf128b` | `43818450043` ✅ (885 pruebas en Ubuntu y en Windows) |

**Incidencias durante F4:**

- La auditoría metodológica pedida por el autor tras T0, antes de cualquier dato, encontró tres
  errores en las propuestas: A6 habría fallado con separación completa (el BCa no es estimable
  cuando δ̂ = −1, comprobado con datos sintéticos); B3 se habría aprobado artificialmente, porque
  la métrica de F1 `predator_survival` cuenta como supervivientes a los depredadores vivos en un
  final anticipado; y B6 confundía "vivo al final" con "vivo en T_max". También detectó una
  justificación errónea para limitar A4 (b) a la presa, una redefinición no autorizada de B5 y
  tres lecturas posibles de la alternancia. Todo se corrigió en T0b con las decisiones D1–D18 del
  autor.
- La auditoría independiente de T3 (sondas sin episodios reales) encontró que una especificación
  o configuración fuera del repositorio permitía usar las semillas de confirmación en calibración
  sin que la comprobación del árbol limpio lo detectara, y que el comando no exigía la evaluación
  de entrada antes de la confirmación ni el orden de las iteraciones. Se corrigió en T3b junto con
  los hallazgos menores; M-3 quedó pendiente de una decisión separada.
- La auditoría independiente de T3b encontró que las marcas skip-worktree y assume-unchanged
  ocultaban cambios a `git status`, que una violación A2 podía perder su registro si fallaba el
  renombrado y repetirse como interrupción, y que la configuración podía cambiar entre
  iteraciones. Al corregirlo en T3c, una revisión propia encontró dos vías más para disfrazar un
  contenido modificado como el de HEAD (un filtro `clean` configurado solo en `.git` y la
  sustitución del commit con `git replace`), que también quedaron bloqueadas.
- El CI de `e4900ba` falló solo en Windows, en la prueba de conversión de fin de línea: el CI
  extrae el proyecto con CRLF (`core.autocrlf=true`) y la prueba guardaba esos CRLF en el
  repositorio temporal, de modo que la premisa (LF en HEAD) no se cumplía. El código de
  producción era correcto: detectaba que esos archivos no eran el contenido de HEAD. El commit
  correctivo `bb82864` renormaliza los blobs en la prueba, comprueba explícitamente sus finales
  de línea y añade el caso contrario (blob CRLF bajo un atributo `text`), para que no dependa del
  sistema operativo; su CI `43797566961` pasó en Ubuntu y en Windows (693 pruebas en cada uno).
  El repositorio real no tiene blobs con CRLF.
