# Declaración de uso de IA generativa

La propuesta académica (§8) exige declarar qué herramientas de IA generativa se usaron, para
qué, qué recomendaciones se aceptaron o rechazaron y qué validaciones se hicieron. Este archivo
se mantiene como registro durante todo el proyecto; la versión resumida irá en el informe (F9).

## Herramientas

| Herramienta | Uso |
|---|---|
| Claude Code (modelo Claude Opus 5.5, Anthropic) | Análisis de la propuesta, diseño de arquitectura y metodología, redacción de ADR, andamiaje del repositorio |

## Registro

### 2026-11-15: análisis y diseño (antes de F0)

**Uso:** análisis de la propuesta académica; propuesta de arquitectura, diseño de redes,
algoritmo de entrenamiento, metodología experimental y estadística; cinco rondas de revisión.

**Recomendaciones corregidas o rechazadas a partir de la revisión del autor:**

| Propuesta inicial de la IA | Problema señalado por el autor | Resolución |
|---|---|---|
| `spawn_key=(1, r, "evo")` | `SeedSequence` solo admite enteros no negativos | Claves de 6 enteros (ADR-028) |
| Sensores (p, sin φ, cos φ) | Discontinuidad en el borde de la visión | (p, p·sin φ, p·cos φ) (ADR-007) |
| Variables de entorno de BLAS antes de crear el pool | No tienen efecto si NumPy ya se importó | threadpoolctl + `spawn` + verificación (ADR-016) |
| `N(0, 1/fan_in)` sin precisar | Ambigüedad entre varianza y desviación estándar | Varianza 1/fan_in y prueba I1 (ADR-018) |
| R = 6 presentado como suficiente | No garantiza potencia | Regla de P3 y limitaciones explícitas (ADR-004) |
| Prueba de signo agrupando A, B y C | Posible pseudorreplicación y ocultamiento de efectos | Análisis por escenario (ADR-017) |
| Umbrales fijos δ ≥ 0.33 en P1 | Forzarían parámetros por ruido muestral | Criterios en clases A/B/C (ADR-020) |
| "Con R = 10 se admiten dos rangos negativos" | El p depende de los rangos, no del número de negativos | Decisión por p exacto y Holm (ADR-017) |
| Cobertura del IC por signos con n = 7 del 99.2 % | Error de cálculo | 98.4 % (ADR-017) |
| Prueba de signo excluyendo ceros para H₀: mediana = 0 | No contrasta la mediana con datos discretos | Prueba sin condicionar, dual con el IC (ADR-017) |

**Errores detectados por la propia IA durante las revisiones:** Holm con R = 6 hacía imposibles
los rechazos en C1/C3; Kaplan-Meier ignoraba el riesgo competitivo de inanición; errores de
dependencia en el plan de fases; empates en G_θ.

**Validaciones:** revisión crítica del autor en cada ronda; verificación de los cálculos
combinatorios y binomiales.

### 2026-11-15: F0 (andamiaje del repositorio)

**Uso:** generación de `pyproject.toml`, configuración de ruff, pytest e import-linter, pruebas
de arquitectura, CI, README y ADR.

**Validaciones:** `ruff`, `lint-imports` y `pytest` ejecutados localmente; los contratos de
arquitectura se comprobaron inyectando importaciones prohibidas en el dominio (los tres
mecanismos fallaron como se esperaba). Durante esa comprobación se detectó y corrigió que la
prueba AST fallaba con archivos guardados con BOM.
