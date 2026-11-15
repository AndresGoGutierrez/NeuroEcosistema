# ADR-013: Análisis de la comparación de arquitecturas (C2)

- **Estado:** Aceptada (Δ y θ numéricos pendientes de P2)
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D13
- **Eje de la bitácora:** Diseño experimental
- **Requisitos relacionados:** §6 (comparación entre dos arquitecturas, con hipótesis, controles, tabla o gráfica, análisis y conclusión)

## Contexto

C2 compara la red base [16, 16] con la compacta [8, 8] en el escenario A (ADR-005). Hay que
definir qué significa "comparable" y cómo se mide la eficiencia, sin p-valores engañosos con R pequeño.

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| Wilcoxon pareado por índice de ejecución | El emparejamiento sería arbitrario: las ejecuciones no comparten aleatoriedad |
| Prueba t | Supuestos de normalidad no verificables con R pequeño |
| **Ejecuciones independientes; Mann-Whitney exacto; no inferioridad por IC; eficiencia en generaciones** | El IC con R = 6 es ancho; "no concluyente" es plausible |

## Evidencia disponible

Analítica: con 6 contra 6 ejecuciones, el p mínimo bilateral de Mann-Whitney es 2/924 ≈ 0.0022
y el IC exacto de Hodges-Lehmann al 95.9 % es [D₍₆₎, D₍₃₁₎] de las 36 diferencias entre pares.

## Criterio de selección

Validez del supuesto de independencia por construcción y una regla de decisión fijada antes de ver datos.

## Decisión

- **Independencia:** cada arquitectura tiene su propio `seed_group` (ADR-028).
- **Presupuesto común:** N, E, G, V y k_val iguales; σ de mutación propio de cada arquitectura,
  ajustado en P2b con la misma rejilla, semillas y número de ejecuciones.
- **Rendimiento final (no inferioridad):** δ = compacta − base por Hodges-Lehmann con IC exacto [L, U].
  Margen Δ = 0.10 × ganancia de entrenamiento de la red base medida en P2 (escenario A),
  fijado numéricamente antes de F7.
  - Superior: L > 0. No inferior: L > −Δ. Inferior: U < −Δ. En otro caso: no concluyente.
- **Eficiencia:** θ = F₀ + 0.9·(F_base − F₀), con F₀ y F_base tomados de P2 y fijados antes de F7.
  G_θ,r = primera generación evaluada con F_val ≥ θ; si no se alcanza, censurada en G + k_val.
  Comparación por **permutación exacta** de las 924 particiones con rangos medios (hay empates
  porque G_θ es discreto y puede estar censurado). Métrica complementaria: área bajo la curva de validación.
- Se reportan siempre el δ de Cliff y todos los puntos. Si los rangos intercuartílicos de los
  dos brazos difieren más del doble, la no inferioridad se informa "condicionada al modelo de desplazamiento".
- Familia de Holm de C2: G_θ de presa y de depredador (m = 2).
- Medida principal de eficiencia: generaciones (evaluaciones); el tiempo de reloj es secundario.

## Consecuencias

El F_val del élite tiene un sesgo optimista por selección que afecta por igual a ambos brazos.

## Verificación

F3: pruebas de la permutación exacta con empates, del IC de Hodges-Lehmann y de la regla de no
inferioridad; F7: Δ y θ pre-registrados.
