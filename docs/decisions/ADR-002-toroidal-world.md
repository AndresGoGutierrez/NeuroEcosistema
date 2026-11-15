# ADR-002: Mundo toroidal sin paredes

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D2
- **Eje de la bitácora:** Representación del entorno
- **Requisitos relacionados:** §4 (entorno 2D, reglas de movimiento), §5 (qué percibe cada agente)

## Contexto

El entorno 2D necesita una topología de bordes. Los bordes condicionan la percepción, las
estrategias posibles y el número de entradas de las redes.

## Alternativas consideradas

| Alternativa | Ventajas | Inconvenientes |
|---|---|---|
| Mundo con paredes | Más "ecológico"; permite acorralar presas | Esquinas que favorecen esconderse; efectos de borde; requiere sensores de pared |
| **Toro (los bordes se conectan)** | Sin refugios ni efectos de borde; percepción homogénea; menos entradas | Menos realista |
| Paredes con obstáculos | Riqueza de comportamiento | Más sensores, más reglas y más riesgo; la propuesta permite usar más depredadores en lugar de obstáculos (§6) |

## Evidencia disponible

Analítica: en un toro todas las posiciones son equivalentes; no existe un rincón que una
política pueda explotar para sobrevivir sin evadir ni alimentarse.

## Criterio de selección

Minimizar estrategias degeneradas que no dependan de la percepción y reducir decisiones
arbitrarias en el diseño de sensores.

## Decisión

Mundo toroidal de lado L. Distancias y vectores relativos con la convención de imagen mínima.
Restricción: el radio de visión de cada especie cumple R_v < L/2 (ADR-030).

## Consecuencias

- No hay sensores de pared ni variables de posición absoluta.
- Limitación declarada: no se estudian estrategias que dependan de bordes u obstáculos.

## Verificación

F1: pruebas de geometría (envoltura de posiciones, distancia de imagen mínima) y del validador
de configuración (R_v < L/2).
