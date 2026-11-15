# ADR-030: Asimetría entre especies y restricciones de coherencia del modelo

- **Estado:** Aceptada (diseño consolidado)
- **Fecha:** 2026-11-15
- **Eje de la bitácora:** Representación del entorno
- **Requisitos relacionados:** §1 (objetivos diferenciados), §4 (energía, movimiento, captura), §10 (especies diferenciadas)

## Contexto

Las reglas de energía, velocidad, percepción, captura y alimentación deben ser compatibles entre
sí; de lo contrario aparecen estrategias triviales, imposibles o artefactos del tiempo discreto.

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| Especies simétricas | La persecución o la evasión podría ser imposible |
| Calibrar sin restricciones explícitas | Riesgo de artefactos (p. ej., "atravesar" a la presa entre pasos) |
| **Asimetría velocidad/agilidad + restricciones verificables** | — |

## Evidencia disponible

Analítica: con desplazamiento relativo por paso L_seg ≤ r, se detecta todo cruce cuya distancia
mínima continua sea ≤ √(r² − L_seg²/4) ≥ 0.87·r.

## Criterio de selección

Que persecución, evasión, búsqueda de alimento y gestión de energía sean todas viables y relevantes.

## Decisión

**Asimetría:** v_max,pred > v_max,prey (la persecución es posible) y ω_max,prey > ω_max,pred
(la evasión es posible).

| ID | Restricción | Tipo |
|---|---|---|
| K1 | r_capture ≥ v_max,pred + v_max,prey | Validador |
| K2 | r_eat ≥ v_max,prey | Validador |
| K3 | R_v^s < L/2 | Validador |
| K4 | v_max,pred > v_max,prey y ω_max,prey > ω_max,pred | Validador |
| K5 | R_v,prey ≳ r_capture + (v_pred + v_prey)·⌈π/ω_max,prey⌉ | Indicador de P1 |
| E1 | E₀/c_basal ∈ [0.4, 0.6]·T_max para ambas especies | Analítica (P1) |
| E2 | c_move ≥ c_basal | Analítica (P1) |
| E3 | Tasa neta de energía de la presa por reglas sin depredadores > 0 en A y ≤ 0 en B | Medida (P1, B4) |
| E4 | El depredador por reglas necesita ≥ 2 capturas para llegar a T_max | Medida (P1, B6) |
| E5 | e_plant ≤ 0.5·E_max,prey | Analítica (P1) |

## Consecuencias

Quedarse inmóvil lleva a la inanición antes de T_max; ninguna planta recarga toda la energía;
una captura no basta para todo el episodio.

## Verificación

F1: el validador rechaza configuraciones que incumplen K1–K4. F4: criterios A1 y B de ADR-020.
