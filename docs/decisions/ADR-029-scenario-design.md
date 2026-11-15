# ADR-029: Diseño de los escenarios experimentales

- **Estado:** Aceptada (diseño consolidado; valores numéricos pendientes de P1)
- **Fecha:** 2026-11-15
- **Eje de la bitácora:** Diseño experimental
- **Requisitos relacionados:** §6 (escenarios: (a) recursos suficientes y pocos depredadores; (b) escasez de alimento; (c) aumento de la presión de depredación u obstáculos)

## Contexto

§6 exige tres escenarios con diferencias medibles y permite elegir entre más presión de
depredación u obstáculos para el tercero.

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| Escenario C con obstáculos | Más sensores, reglas y riesgo |
| Escenarios que cambian varios factores a la vez | Efectos confundidos |
| **A de referencia; B y C cambian un único factor respecto de A** | — |

## Evidencia disponible

Analítica: un diseño de un factor por vez permite atribuir las diferencias al factor manipulado.

## Criterio de selección

Interpretabilidad de las diferencias entre escenarios.

## Decisión

| Variable | A: abundancia | B: escasez | C: presión de depredación |
|---|---|---|---|
| Densidad de plantas (N_plants) | alta | **baja** | alta (= A) |
| n_predators | bajo | bajo (= A) | **alto** |
| Resto (n_prey, τ_regrow, T_max, especies, reglas) | constante | constante | constante |

Los valores se calibran en P1 (ADR-020) y se congelan antes de entrenar redes.

## Consecuencias

El fitness del depredador no es comparable entre escenarios (más depredadores o menos presas
disponibles); entre escenarios se usan métricas por capita y ajustadas por exposición (ADR-014).

## Verificación

F4: criterios A6 y B4–B5 de ADR-020.
