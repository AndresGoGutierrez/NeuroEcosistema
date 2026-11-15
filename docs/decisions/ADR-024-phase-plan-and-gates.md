# ADR-024: Plan de fases F0–F9 con cierres obligatorios

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D24
- **Eje de la bitácora:** Ingeniería y reproducibilidad
- **Requisitos relacionados:** §7 (productos de entrega), §9 (rúbrica)

## Contexto

El plan F0–F8 inicial tenía errores de dependencia: la política por reglas usa los sensores
(previstos en F3) y P1 necesita la estadística (prevista al final). Tampoco probaba el pipeline
completo antes de los experimentos formales.

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| Plan F0–F8 original | No ejecutable en ese orden |
| **F0–F9 reordenado, con ensayo general en F7 y cierres obligatorios** | — |

## Evidencia disponible

Analítica: grafo de dependencias entre componentes.

## Criterio de selección

Cada fase solo depende de fases cerradas.

## Decisión

Ninguna fase empieza sin que la anterior haya cerrado en `docs/phase_gates.md` sobre un commit
limpio. Las excepciones requieren aprobación explícita del autor y quedan registradas.

| Fase | Depende de | Criterios de cierre |
|---|---|---|
| F0 Fundaciones | Aprobación del diseño | `uv sync --frozen` en clon limpio; `ruff`, `lint-imports` y `pytest` en verde; CI en verde; ADRs |
| F1 Núcleo de simulación + P0 | F0 | Pruebas de cada regla, sensores (continuidad, rangos, 10/7), políticas de referencia y sondas, métricas (identidad vivas + capturadas + muertas de hambre = n), D1, D2, D5; c_step medido (≤ 500 µs o plan de optimización) |
| F2 Visualización | F1 | Hash con visor = hash sin visor; inspector = traza; `--set` registrado |
| F3 Estadística | F1 | Pruebas de ADR-013, ADR-017 y ADR-014 en verde (incluidas las lentas de cobertura) |
| F4 P1 Calibración | F2, F3 | Criterios de ADR-020; etiqueta `env-frozen-v1` |
| F5 Redes | F4 | `NetworkSpec` rechaza < 2 capas ocultas; parámetros 482/178/434/154; I1 e I2; ablación de pesos; D4; rechazo de esquema distinto |
| F6 Neuroevolución + P2, P3 | F5 | Pruebas del algoritmo genético; problema de juguete; D3; un hilo de BLAS; N, E, V, G, σ, k_val, curriculum, Δ, θ y R fijados |
| F7 Protocolo | F6 | `experimental_protocol.md` completo; ensayo general en miniatura que produce todas las tablas y figuras; etiqueta `protocol-v1` |
| F8 Experimentos formales | F7 | Ejecuciones completas o fallos documentados; manifests limpios; tablas regenerables; desviaciones registradas |
| F9 Entregables | F8 | Informe ≤ 10 páginas (§7.3); bitácora ≥ 6 decisiones (§7.4); declaración de IA (§8); reproducción en clon limpio; ensayo de la demo |
| Opcional: coevolución | F8 | No bloquea F9 |

## Consecuencias

El progreso es más lento pero cada fase deja evidencia verificable.

## Verificación

`docs/phase_gates.md`.
