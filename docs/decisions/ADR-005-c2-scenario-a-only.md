# ADR-005: Comparación de arquitecturas (C2) solo en el escenario A

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D5
- **Eje de la bitácora:** Diseño experimental
- **Requisitos relacionados:** §6 (comparación entre dos arquitecturas o configuraciones)

## Contexto

§6 exige al menos una comparación entre dos arquitecturas o configuraciones. No exige
repetirla en cada escenario. Cada brazo adicional cuesta R ejecuciones por especie.

## Alternativas consideradas

| Alternativa | Ventajas | Inconvenientes |
|---|---|---|
| C2 en A, B y C | Permite estudiar interacción arquitectura × escenario | Unas 24 ejecuciones más (con R = 6) |
| **C2 solo en A (escenario de referencia)** | Cumple §6 con un costo acotado | No permite conclusiones sobre esa interacción |

## Evidencia disponible

Analítica: con R = 6, 2 especies y 2 escenarios adicionales, el ahorro es 2 × 2 × 6 = 24 ejecuciones.

## Criterio de selección

Cumplir el requisito con el menor costo que no comprometa la validez interna de la comparación.

## Decisión

C2 compara la red base [16, 16] con la compacta [8, 8] únicamente en el escenario A, para
ambas especies (ADR-013, ADR-025).

## Consecuencias

No se harán afirmaciones sobre si la ventaja de una arquitectura depende del escenario.

## Verificación

F7: protocolo pre-registrado; F8: ejecuciones de C2 en A.
