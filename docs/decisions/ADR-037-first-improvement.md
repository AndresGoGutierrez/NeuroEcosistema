# ADR-037: Primera mejora: presupuesto y oponentes de entrenamiento de la presa

- **Estado:** Propuesta (no ejecutada en este proyecto)
- **Fecha:** 2026-11-18
- **Eje de la bitácora (§5 de la propuesta):** Mejora
- **Requisitos relacionados:** ADR-027, ADR-035, ADR-036

## Contexto

La presa entrenada queda por debajo de la política por reglas en A y C (ADR-036). ¿Qué decisión
se modificaría primero y con qué evidencia?

## Alternativas consideradas

| Alternativa | Evidencia a favor | Inconvenientes |
|---|---|---|
| Red de presa más grande | — | C2 no muestra que la capacidad limite (compacta ≈ base) |
| Más sensores (otras presas, más plantas) | Plausible | Cambia el entorno congelado; requiere recalibrar (P1) |
| **Más generaciones y oponentes variados (M0/M1/M2) para la presa** | Curvas crecientes en G = 70; modelo seleccionado al final; desventaja concentrada en oponentes deterministas | Más cómputo (≈ 2× para la presa) |
| Cruce en el algoritmo genético | — | Sin evidencia en este proyecto |

## Evidencia disponible

Curvas de validación (`validation_curves.png`); generaciones de selección en
`results/experiments/f8/runs/*/summary.json`; matriz de generalización (ADR-019).

## Decisión

Primera mejora: G ≥ 150 para la presa, con la regla de estancamiento de ADR-035 medida sobre R
ejecuciones (no 2), y entrenamiento frente a una mezcla de M0, M1 y M2. Criterio de éxito:
C3 de la presa con IC que incluya o supere 0 en A y C. Después, para C2 de la presa, aumentar R
o fijar Δ con un criterio sustantivo.

## Consecuencias

Exigiría un nuevo protocolo prerregistrado y nuevas semillas formales; no modifica los
resultados de F8.
