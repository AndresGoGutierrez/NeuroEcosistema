# ADR-028: Esquema de semillas

- **Estado:** Aceptada (diseño consolidado)
- **Fecha:** 2026-11-15
- **Eje de la bitácora:** Diseño experimental / Ingeniería y reproducibilidad
- **Requisitos relacionados:** §4 (semillas de aleatoriedad), §6 (ejecuciones con semillas registradas y condiciones comparables)

## Contexto

Toda la aleatoriedad debe ser reproducible, los flujos deben ser independientes entre sí y las
condiciones comparadas deben compartir entornos cuando corresponda.

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| Semillas enteras ad hoc por ejecución | Riesgo de solapamiento y difícil de auditar |
| `SeedSequence` con claves de longitud variable o con texto | `spawn_key` solo admite enteros no negativos; longitudes variables son ambiguas |
| **`SeedSequence(project_seed, spawn_key=(6 enteros))`** | — |

## Evidencia disponible

Analítica: `numpy.random.SeedSequence` mezcla entropía y clave con un hash de alta calidad;
claves distintas producen flujos estadísticamente independientes.

## Criterio de selección

Reproducibilidad, independencia y trazabilidad.

## Decisión

`spawn_key = (purpose, seed_group, run, generation, item, stream)`; campos que no aplican = 0.

| Campo | Valores |
|---|---|
| `purpose` | 1 PILOT · 2 TRAIN · 3 VALIDATION · 4 TEST · 5 ANALYSIS |
| `seed_group` | Entero declarado explícitamente en cada configuración; el cargador rechaza duplicados |
| `stream` | 1 GA_INIT · 2 GA_VARIATION · 3 ENV_INIT · 4 ENV_DYNAMICS · 5 POLICY_PREY · 6 POLICY_PREDATOR · 7 BOOTSTRAP |

- `project_seed`: entero de 128 bits generado una sola vez en F0 y guardado en `configs/base.yaml`.
- Un flujo genético por generación (permite reanudar sin guardar el estado del RNG).
- VALIDATION y TEST no dependen de `seed_group` ni de `run`: todas las condiciones se evalúan
  en los mismos entornos (números aleatorios comunes).
- `seed_group` distinto para cada condición → ejecuciones independientes por construcción.
- Cada episodio separa entorno inicial, dinámica (cola de reaparición de plantas) y ruido de
  cada política: cambiar la política no altera el entorno.
- Se registran las claves en `seeds.json` de cada ejecución.
- Prohibidos el módulo `random` y la API global `np.random.*` (reglas TID251 y NPY002 de ruff).

## Consecuencias

Las conclusiones son condicionales a los conjuntos fijos de validación y prueba.

## Verificación

F0: `tests/test_project_seed.py`. F1: claves de 6 enteros en [0, 2³²), propósitos disjuntos,
re-derivación idéntica, pruebas D1, D2 y D5.
