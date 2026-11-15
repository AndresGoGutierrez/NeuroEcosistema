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
