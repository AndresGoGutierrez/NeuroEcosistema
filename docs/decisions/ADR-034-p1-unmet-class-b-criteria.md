# ADR-034: Criterios de clase B no cumplidos en P1 (B3 en C y B4 (ii))

- **Estado:** Aceptada
- **Fecha:** 2026-11-17
- **Eje de la bitácora (§5 de la propuesta):** Diseño experimental
- **Requisitos relacionados:** ADR-020 (criterios de P1), ADR-030 (E3), ADR-033 (P1-18, D12)

## Contexto

La calibración P1 terminó con la confirmación (grupos 20/21/22, 1750 episodios): toda la clase A
se cumple, ninguna alerta C y ninguna violación A2. Dos criterios de clase B no se cumplen ni en
la evaluación de entrada ni en la confirmación. P1-18 exige decidirlos por ADR antes del
congelamiento. Valores congelados: iteración 007 (`plant_energy` 30.0, `regrow_delay` 50,
`n_plants` 40 en A y C y 4 en B, `n_predators` 3 en A y B y 5 en C, `p_flee` 0.2,
`u_cruise` 0.3 de la presa y 0.7 del depredador).

| Criterio | Entrada | Confirmación |
|---|---|---|
| B3 en C: fracción de depredadores con t_i ≥ T_max/2 ≥ 1/2 | 37/75 = 0.493 | 62/125 = 0.496 |
| B4 (ii): tasa neta media de `no_predators` > 0 en A y ≤ 0 en B | A −0.042, B −0.140 | A −0.041, B −0.140 |

## Alternativas consideradas

| Alternativa | Ventajas | Inconvenientes |
|---|---|---|
| Otra iteración C con n_pred,C = 4 para B3 | Podría alcanzar 1/2 | Es el último valor permitido (> 3); pone en riesgo A4 (d), de clase A (702 frente a 654 capturas en la iteración 7); P1-18 no permite iterar para alcanzar un umbral |
| Cambiar la etapa A para B4 (ii) | Atacaría la causa | Prohibido por la regla de no retorno (P1-18) |
| Redefinir B3 o B4 (ii) | Los haría pasar | Cambiar un criterio después de ver los datos (prohibido) |
| **Aceptar ambos incumplimientos, documentados, y congelar** | Respeta P1-18 y D12; la clase A está confirmada con semillas nuevas | Dos propiedades secundarias del entorno quedan por debajo de lo deseado |

## Evidencia disponible

Empírica (`results/pilots/p1/`, `docs/pilot_report.md`):

- **B3 en C.** El déficit es de un depredador en 75 (entrada) y de menos de uno en 125
  (confirmación). La tendencia con n_pred,C (8 → 6 → 5: 2/15, 43/180, 37/75) muestra que la
  causa es el agotamiento de las presas, que termina los episodios antes de T_max/2; con 5
  depredadores la mediana de pasos ya es 898.
- **B4 (ii).** La parte de A falla con valores negativos y estables (−0.042 y −0.041). Es la
  situación prevista en D12: la tasa neta exige que la energía final media supere
  E₀ = 0.8·E_max, y una población sostenible con energía final menor que E₀ da una tasa ≤ 0.
  La parte de B (≤ 0) y B4 (i) sí se cumplen: el mecanismo de escasez de B funciona.

## Criterio de selección

P1-18: un incumplimiento de clase B solo justifica una iteración si tiene una causa paramétrica
identificable dentro de la etapa, nunca para alcanzar un tamaño del efecto, y desde B o C no se
vuelve a A.

## Decisión

- Se aceptan B3 en C y B4 (ii) como incumplimientos documentados. Los valores de la iteración 007
  se congelan (`env-frozen-v1`).
- E3 (ADR-030) se mantiene sin cambios, como establece D12.
- El informe final declara ambos incumplimientos. B3 en C: la presión de predación de C acorta
  algunos episodios. B4 (ii): en A, sin depredadores, la energía media de las presas no supera E₀.
- Decisiones del proceso: 1 (B4 (ii) al pasar a C), 2 y 3 (repetir C), 4 (B3 al pasar a la
  entrada) y 5 (revisión de la entrada). Las decisiones 4 y 5 y este ADR los tomó Claude por
  delegación expresa del autor (2026-11-17). El autor autorizó y ejecutó la confirmación y
  autorizó el congelamiento.

## Consecuencias

- Los experimentos formales usan un entorno cuya clase A está confirmada con semillas no vistas.
- En C, los depredadores aprendidos se evalúan con algunos episodios más cortos que T_max; la
  métrica de supervivencia del depredador debe interpretarse con esa censura.
- La interpretación de B4 (ii) queda como limitación declarada (D12), sin efecto en C1–C3.

## Verificación

`results/pilots/p1/confirmation/evaluation/criteria.csv`; la prueba de P1-2 fija los valores
congelados; etiqueta `env-frozen-v1`.
