# ADR-017: Análisis estadístico de C1 (antes/después) y C3 (frente a la referencia)

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D17
- **Eje de la bitácora:** Diseño experimental
- **Requisitos relacionados:** §6 (comparaciones obligatorias; "las conclusiones deben coincidir con los datos"), §10 (resultados negativos válidos)

## Contexto

Con pocas ejecuciones por escenario, métricas discretas y escenarios deliberadamente distintos,
el análisis debe evitar la pseudorreplicación, los supuestos no justificables y los p-valores
inalcanzables bajo corrección por multiplicidad.

## Alternativas consideradas

| Alternativa | Motivo del descarte |
|---|---|
| Pruebas a nivel de episodio | Pseudorreplicación: los episodios son submuestras de una ejecución |
| Prueba de signo agrupando A, B y C (3R observaciones) | Los escenarios son distintos a propósito; puede ocultar efectos contradictorios (6/6, 6/6 y 2/6 mejoras dan p = 0.031); para generalizar a "escenarios" la n real es 3 |
| Wilcoxon como prueba confirmatoria | Requiere simetría, que el diseño no garantiza (resultados posiblemente bimodales; en C3 la referencia es fija; en C1 antes y después se seleccionan entre conjuntos distintos) |
| Prueba de signo excluyendo ceros | Contrasta p⁺ = p⁻, no la mediana; rompe la dualidad con el IC |
| **Prueba de signo exacta sin condicionar, por escenario, dual con el IC de la mediana** | — |

## Evidencia disponible

Analítica:
- Si m es cualquier mediana poblacional, P(d₍ₖ₎ > m) ≤ P(B ≤ k − 1) con B ~ Bin(n, ½); el
  intervalo cerrado es válido con datos discretos.
- Niveles del IC [d₍ₖ₎, d₍ₙ₋ₖ₊₁₎]: n = 6: [mín, máx] 96.9 %; n = 7: [mín, máx] 98.4 %;
  n = 8: [mín, máx] 99.2 %; n = 9: [d₍₂₎, d₍₈₎] 96.1 %; n = 10: [d₍₂₎, d₍₉₎] 97.9 %.
- Con el mismo k, d₍ₖ₎ > 0 ⇔ k⁺ ≥ n − k + 1 ⇔ la prueba rechaza por el lado positivo al nivel 0.025.

## Criterio de selección

Unidad experimental correcta, supuestos mínimos (solo independencia, garantizada por diseño) y
coherencia exacta entre prueba e intervalo.

## Decisión

- **Unidad experimental:** la ejecución de entrenamiento. Los episodios de prueba se promedian
  por ejecución. Escenario = factor fijo; especie = experimento separado.
- **Métricas primarias por ejecución** como numeradores enteros con denominador común; ceros y
  empates se detectan de forma exacta.
- **Análisis principal (estimación, por escenario):** cada d_r; k⁺, k₀, k⁻; mediana muestral con
  IC exacto por signos (incluye ceros; nivel alcanzado reportado).
- **Confirmatorio, por escenario:** prueba de signo exacta **sin condicionar**, n = R.
  - H₀: P(d > 0) ≤ ½ y P(d < 0) ≤ ½ (0 es una mediana de d).
  - H₁⁺: P(d > 0) > ½ (una ejecución mejora estrictamente con probabilidad mayor que ½).
  - p = mín{1, 2·mín[P(B ≥ k⁺), P(B ≥ k⁻)]}, B ~ Bin(n, ½). Los ceros cuentan contra ambos lados.
- **Holm** con m fijo: C1 = 2 especies × 3 escenarios (m = 6); C3 = frente a la política por
  reglas (m = 6). Se reportan p ajustados p̃₍ᵢ₎ = máx_{j≤i} mín(1, (m − j + 1)·p₍ⱼ₎). Sin mid-p.
- **Viabilidad:** p mínimo de diseño 2/2^R; el confirmatorio exige **R ≥ 8**. Si R < 8, C1 y C3
  son solo estimación (la propuesta no exige p-valores). No existe regla de "no evaluable"
  dependiente de los datos: un cero es un resultado.
- **Sensibilidad (no decide):** Hodges-Lehmann (pseudo-mediano) con IC por inversión de
  Wilcoxon y p de Wilcoxon, bajo supuesto explícito de simetría; ceros excluidos (Wilcox),
  rangos medios como enteros duplicados y permutación exacta de signos. Una discrepancia con la
  prueba de signo se reporta como posible asimetría.
- **Descriptivo:** comparación con la política aleatoria; nivel de episodio (media pareada con BCa);
  generalización (ADR-019).
- El IC es por comparación y sin ajustar; las conclusiones confirmatorias salen solo de Holm.
- Con todos los positivos de una especie rechazados se puede afirmar "mejora en los tres escenarios".

## Consecuencias

Con R = 8, un solo cero o negativo impide superar el primer paso de Holm. Es el costo
conservador de no suponer simetría y se declara.

## Verificación

F3: dualidad prueba-IC con datos enteros aleatorios con ceros y empates (n = 6…12); casos de
referencia: R = 8 con 8 positivos → 2/256; 7 positivos y 1 cero → 18/256; R = 10 con 9 positivos
y 1 cero → 22/1024; 8 positivos y 2 ceros → 112/1024; niveles del IC; monotonía de Holm.
