# ADR-036: Interpretación de los resultados de F8

- **Estado:** Aceptada
- **Fecha:** 2026-11-18
- **Eje de la bitácora (§5 de la propuesta):** Interpretación
- **Requisitos relacionados:** ADR-013, ADR-017, ADR-019, ADR-026, ADR-035

## Contexto

F8 terminó (80 ejecuciones, `results/experiments/f8/analysis/tables.md`). Hay que decidir qué
afirmaciones sostienen los datos y cuáles no, sin reinterpretar el protocolo prerregistrado.

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| Informar solo los contrastes significativos tras Holm | Oculta la estimación (p. ej. el depredador en B) y la asimetría entre especies |
| Reinterpretar C3 de la presa como fracaso de la red | Las curvas de validación indican entrenamiento insuficiente, no un límite de capacidad |
| **Informar cada familia completa (estimación + contraste) y separar lo confirmado de lo exploratorio** | Más extenso |

## Evidencia disponible

- C1: 10/0/0 en las 6 familias, p Holm = 0.012.
- C3: depredador +0.008/+0.026/+0.007 (A/B/C; B con IC [0.017, 0.056], p Holm = 0.086);
  presa −0.029/−0.006/−0.021 (A y C con p Holm = 0.012).
- C2: depredador no inferior (IC [−0.020, 0.016], Δ = 0.084); presa inconclusa
  (IC [−0.042, 0.016], Δ = 0.010).
- Generalización: la presa supera a las reglas solo frente a M3 (aleatorio).
- Curvas de validación: la presa compacta sigue mejorando en la generación 70.

## Decisión

Se afirma: C1 confirmada en ambas especies y escenarios; el depredador entrenado es equivalente
en la práctica a las reglas (ventaja en B solo como estimación); la presa entrenada es inferior
a las reglas en A y C; la red compacta del depredador es no inferior. Se declara inconclusa la
no inferioridad de la presa compacta. La inferioridad de la presa se atribuye, como hipótesis a
verificar, a presupuesto de entrenamiento y a especialización frente al oponente determinista.

## Consecuencias

El informe (§5–§6) separa resultados confirmatorios (Holm) y estimaciones. La hipótesis sobre
la presa motiva ADR-037.
