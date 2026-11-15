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
- **Estado:** en curso.
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

| Criterio de cierre (ADR-024) | Estado |
|---|---|
| Pruebas de cada regla (movimiento, metabolismo, inanición, emparejamiento, capturas, alimentación, reaparición, terminación) | ⏳ |
| Sensores: continuidad, rangos, longitud 10/7 | ⏳ |
| Políticas de referencia y sondas ejecutan episodios en A, B y C | ⏳ |
| Métricas, con la identidad vivas + capturadas + muertas de hambre = n | ⏳ |
| DET-1, DET-2, DET-5 | ⏳ |
| c_step ≤ 500 µs con 50 presas y 8 depredadores, o plan de optimización | ⏳ |
