# ADR-021: Estructura simplificada para un proyecto individual

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D21
- **Eje de la bitácora:** Ingeniería y reproducibilidad
- **Requisitos relacionados:** §8 (comprender y explicar todo componente), §9 (sustentación y dominio individual)

## Contexto

La primera propuesta tenía unos 60 archivos, subcarpetas por concepto y protocolos con una sola
implementación: demasiado para un único desarrollador que debe explicar cada pieza.

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| Estructura extensa con un protocolo por concepto | Costo de mantenimiento y de explicación |
| **Módulos planos y cohesionados; un solo protocolo en el dominio; tres puertos** | — |

## Evidencia disponible

Analítica: Clean Architecture exige inversión de dependencias entre capas, no dentro del dominio;
un protocolo con una sola implementación no aporta.

## Criterio de selección

Mínima estructura que conserva la regla de dependencias, la reproducibilidad y los requisitos.

## Decisión

- Dominio con 13 módulos planos (params, geometry, state, rules, interactions, perception,
  actions, policies, neural, evolution, fitness, simulator, records).
- `Policy` es el único protocolo del dominio (aleatoria, por reglas, constante, neuronal y ablación).
  MLP, algoritmo genético y fitness son clases o funciones concretas.
- Puertos: `TaskExecutor`, `RunStore` y `ModelStore`.
- Fuera de la estructura inicial: coevolución, notebooks, comando `verify-determinism`
  (se usa `pytest -m determinism`) y `benchmark` como caso de uso.
- Visor mínimo: dibujo, HUD de texto e inspector.

## Consecuencias

Unos 30 archivos de código fuente. Los módulos se crean en la fase que los necesita.

## Verificación

Revisión de estructura al cierre de cada fase; contratos de import-linter.
