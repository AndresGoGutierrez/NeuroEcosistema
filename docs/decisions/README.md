# Bitácora de decisiones técnicas

La propuesta académica (§5 y §7.4) exige una bitácora con al menos seis decisiones relevantes,
cada una con alternativas consideradas, evidencia disponible y criterio de selección. Cada
decisión se registra como un ADR (*Architecture Decision Record*) con la plantilla
[ADR-000](ADR-000-template.md).

- ADR-001 a ADR-024 corresponden uno a uno a las decisiones D1–D24 aprobadas al cerrar el diseño
  (2026-11-15).
- ADR-025 a ADR-030 registran decisiones del diseño consolidado que no tenían número D.
- ADR-031 en adelante registran decisiones tomadas durante la implementación, con aprobación
  del autor.
- Las decisiones de los ejes **Interpretación** y **Mejora** se añadirán con los resultados (F9).
- La evidencia de muchos ADR es todavía analítica; cada uno indica qué evidencia empírica falta
  y en qué fase se obtiene.

## Por eje de §5

### Representación del entorno
*¿Qué información percibe cada agente? ¿Qué variables se excluyeron y por qué?*

| ADR | Decisión |
|---|---|
| [002](ADR-002-toroidal-world.md) | Mundo toroidal sin paredes |
| [003](ADR-003-no-in-episode-reproduction.md) | Sin reproducción dentro del episodio |
| [007](ADR-007-sensor-encoding.md) | Codificación de los sensores (10 y 7 entradas) |
| [008](ADR-008-step-phase-order.md) | Orden de las fases de un paso |
| [009](ADR-009-greedy-matching.md) | Emparejamiento voraz para capturas y alimentación |
| [010](ADR-010-energy-rules.md) | Reglas de energía y condiciones iniciales |
| [011](ADR-011-model-simplifications.md) | Simplificaciones del modelo físico |
| [030](ADR-030-species-asymmetry-and-coherence-constraints.md) | Asimetría entre especies y restricciones de coherencia |

### Diseño de las redes
*¿Por qué esa cantidad de capas, neuronas, activaciones y salidas?*

| ADR | Decisión |
|---|---|
| [025](ADR-025-network-architecture.md) | Arquitectura de las redes |
| [018](ADR-018-network-initialization.md) | Inicialización |

### Aprendizaje
*¿Cómo se modifican los pesos? ¿Qué criterio se optimiza y qué podría favorecer indebidamente?*

| ADR | Decisión |
|---|---|
| [026](ADR-026-fitness-and-evaluation-splits.md) | Funciones de aptitud y separación entrenamiento/validación/prueba |
| [027](ADR-027-genetic-algorithm.md) | Algoritmo de neuroevolución |
| [006](ADR-006-training-stages-and-crossplay.md) | Entrenamiento por especie y juego cruzado |
| [015](ADR-015-early-termination-training.md) | Terminación anticipada en entrenamiento |

### Diseño experimental
*¿Qué variable cambia en cada experimento? ¿Qué condiciones se mantienen constantes?*

| ADR | Decisión |
|---|---|
| [029](ADR-029-scenario-design.md) | Diseño de los escenarios |
| [020](ADR-020-p1-ecological-calibration.md) | Calibración ecológica (P1) |
| [033](ADR-033-p1-operational-definitions.md) | Definiciones operativas de la calibración P1 |
| [012](ADR-012-reference-policies.md) | Políticas de referencia, variantes y sondas |
| [014](ADR-014-metric-definitions.md) | Definición de las métricas |
| [017](ADR-017-c1-c3-statistical-analysis.md) | Análisis de C1 y C3 |
| [013](ADR-013-c2-architecture-comparison-analysis.md) | Análisis de C2 |
| [032](ADR-032-statistical-implementation.md) | Implementación estadística y protocolo de cobertura |
| [005](ADR-005-c2-scenario-a-only.md) | C2 solo en el escenario A |
| [004](ADR-004-number-of-runs.md) | Número de ejecuciones R |
| [019](ADR-019-exploitation-and-generalization-tests.md) | Explotaciones y generalización |
| [028](ADR-028-seed-scheme.md) | Esquema de semillas |

### Interpretación
*¿Qué muestran las métricas? ¿Qué resultados contradicen las expectativas?* — Pendiente (F9).

### Mejora
*¿Qué decisión se modificaría primero y con qué evidencia?* — Pendiente (F9).

### Ingeniería y reproducibilidad

| ADR | Decisión |
|---|---|
| [001](ADR-001-numpy-in-domain.md) | NumPy como única dependencia externa del dominio |
| [016](ADR-016-blas-threads-and-process-start.md) | Hilos de BLAS y arranque de procesos |
| [021](ADR-021-simplified-structure.md) | Estructura simplificada |
| [022](ADR-022-stdlib-dataclasses-config.md) | Configuración con dataclasses |
| [023](ADR-023-csv-results.md) | Resultados en CSV |
| [024](ADR-024-phase-plan-and-gates.md) | Plan de fases y cierres |
| [031](ADR-031-viewer-integration.md) | Integración del visor y registro de la sesión |
