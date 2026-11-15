# ADR-009: Emparejamiento voraz determinista para capturas y alimentación

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D9
- **Eje de la bitácora:** Representación del entorno
- **Requisitos relacionados:** §4 (captura, consumo de energía)

## Contexto

Varios depredadores pueden estar en el radio de la misma presa, y varias presas en el radio
de la misma planta. La resolución debe ser determinista y explicable.

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| Recorrer agentes por índice | Sesgo por índice |
| Emparejamiento óptimo (algoritmo húngaro) | Maximiza capturas, que no es un criterio ecológico; difícil de explicar |
| Resolución aleatoria | Introduce aleatoriedad dependiente del comportamiento |
| **Voraz por (distancia, i, j)** | — |

## Evidencia disponible

Analítica: el procedimiento es determinista, independiente del orden de recorrido y de costo
O(m log m) con m pares candidatos, que es pequeño.

## Criterio de selección

Determinismo, prioridad por cercanía y facilidad de explicación.

## Decisión

1. Candidatos: pares (consumidor i, recurso j) con distancia toroidal d_ij ≤ r
   (r_capture o r_eat).
2. Orden estable por (d_ij, i, j).
3. Se recorren en ese orden y se empareja el par si ninguno de los dos está emparejado.

Cada depredador captura como máximo una presa por paso; cada presa come como máximo una
planta por paso; cada recurso tiene un solo consumidor y la energía no se reparte.

## Consecuencias

Tiempo de manipulación implícito de un paso, sin enfriamiento adicional.

## Verificación

F1: pruebas con empates de distancia, conflictos múltiples y prioridad de captura sobre alimentación.
