# ADR-004: Número de ejecuciones independientes de entrenamiento (R)

- **Estado:** Aceptada (valor definitivo pendiente de P3)
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D4
- **Eje de la bitácora:** Diseño experimental
- **Requisitos relacionados:** §6 (varias ejecuciones, variabilidad entre repeticiones)

## Contexto

La unidad experimental es la ejecución de entrenamiento (ADR-017). Hay que fijar cuántas por
configuración, con un presupuesto de cómputo limitado (portátil, proyecto individual).

## Alternativas consideradas

| Alternativa | Ventajas | Inconvenientes |
|---|---|---|
| R = 3–5 | Barato | Con n = 5 el IC exacto de la mediana solo alcanza 93.75 % |
| **R mínimo 6, definitivo por presupuesto medido** | IC exacto ≥ 95 % por escenario; decisión objetiva | R = 6 no permite análisis confirmatorio en C1/C3 |
| R fijo alto (p. ej. 20) | Más precisión | Probablemente inviable en el portátil |
| Simulación de potencia con datos piloto | Formalidad | Con 2–4 ejecuciones piloto la varianza es tan incierta que no informa |

## Evidencia disponible

Analítica (Binomial(n, ½) y distribución nula exacta):

| R | IC de la mediana por signos | Confirmatorio C1/C3 (Holm, m = 6) | IC 95 % de σ entre ejecuciones |
|---|---|---|---|
| 6 | [mín, máx], 96.9 % | No: p mínimo 0.031 > 0.0083 | [0.62σ, 2.45σ] |
| 8 | [mín, máx], 99.2 % | Solo si las 8 ejecuciones mejoran (p = 0.0078) | [0.66σ, 2.04σ] |
| 10 | [d₍₂₎, d₍₉₎], 97.9 % | Solo si las 10 mejoran (9 de 10 da p = 0.021) | [0.69σ, 1.83σ] |

## Criterio de selección

R = 6 es el mínimo con un IC exacto ≥ 95 % por escenario. El valor final depende del
presupuesto real, no de un objetivo de significancia.

## Decisión

- **R = 6** es el mínimo operativo provisional. **No garantiza potencia estadística.**
- **P3 mide:** t_run de las 8 configuraciones (2 especies × 3 escenarios en la red base + 2 de
  la compacta) en carga sostenida ≥ 30 min; costo de evaluación; tasa de fallos (margen m,
  30 % por defecto); dispersión y ganancia de entrenamiento de P2 (solo indicativas); horas
  disponibles H.
- **Regla:** H_req(R) = R · Σ t_run · (1 + m) + H_eval; R_max es el mayor R con H_req ≤ H;
  **R = mín(R_max, 10)**.
- Si R ≥ 8, se hace el análisis confirmatorio de C1 y C3. Si 6 ≤ R < 8, C1 y C3 se
  presentan solo como estimación.
- Si R_max < 6: (1) usar G en el punto de estancamiento sin el margen del 25 %;
  (2) C2 solo para la presa; (3) consultar al autor. El entorno congelado no se modifica.

## Consecuencias

Con R = 6 el intervalo por escenario es el rango de las diferencias y la no inferioridad de C2
probablemente resulte no concluyente. Se declara en el informe.

## Verificación

F6: informe de P3 con las mediciones y el cálculo de R; F7: R pre-registrado.
