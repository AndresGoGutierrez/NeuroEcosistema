# ADR-008: Orden de las fases de un paso de simulación

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D8
- **Eje de la bitácora:** Representación del entorno
- **Requisitos relacionados:** §4 (consumo de energía, movimiento, captura, finalización)

## Contexto

El orden en que se aplican movimiento, energía, capturas y alimentación cambia los resultados.
Una actualización secuencial por agente introduce un sesgo a favor de los índices bajos.

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| Actualización secuencial agente por agente | Sesgo de orden; difícil de vectorizar |
| Síncrona con inanición al final | Un agente sin energía podría interactuar en el mismo paso; causa de muerte ambigua |
| **Síncrona por fases, con inanición antes de interactuar** | — |

## Evidencia disponible

Analítica: con fases síncronas todos los agentes deciden sobre el mismo estado S_t y no hay
ventaja por índice.

## Criterio de selección

Ausencia de sesgo de orden, causa de muerte inequívoca y determinismo.

## Decisión

En cada paso t:

1. Observación sobre S_t (solo agentes vivos y plantas activas).
2. Decisión de todas las políticas en lote.
3. Movimiento: primero se gira y luego se avanza, con envoltura toroidal.
4. Metabolismo: e ← e − (c_basal + c_move·(v/v_max)²).
5. Inanición: si e ≤ 0, el agente muere (STARVATION) y no participa en 6–7.
6. Capturas (emparejamiento voraz, ADR-009).
7. Alimentación de las presas que siguen vivas (emparejamiento voraz).
8. Reaparición de plantas cuyo temporizador vence (visibles desde t + 1).
9. Terminación: t + 1 = T_max o no quedan presas vivas.

Todas las ordenaciones son estables; no se usan conjuntos (`set`) en la lógica.

## Consecuencias

Una presa capturada no come en ese paso; una presa que muere de hambre no cuenta como capturada.

## Verificación

F1: pruebas unitarias de cada fase y de su orden; prueba de determinismo DET-1
(catálogo en `docs/architecture.md`).
