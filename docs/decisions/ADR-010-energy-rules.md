# ADR-010: Reglas de energía y condiciones iniciales

- **Estado:** Aceptada (valores numéricos pendientes de P1)
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D10
- **Eje de la bitácora:** Representación del entorno
- **Requisitos relacionados:** §1 (presas buscan alimento; depredadores administran energía), §4 (consumo de energía)

## Contexto

La dinámica energética define qué comportamientos son viables y debe especificarse por
completo antes de implementar.

## Alternativas consideradas

| Aspecto | Alternativas | Elegida |
|---|---|---|
| Costo de moverse | Lineal o cuadrático en la velocidad | **Cuadrático**: un sprint cuesta mucho más, lo que crea un compromiso real |
| Consumo de plantas | Parcial o entero | **Entero**; el exceso sobre E_max se pierde |
| Ganancia por captura | Proporcional a la energía de la presa o fija | **Fija** (`e_prey`): recompensa estacionaria |
| Energía inicial | Aleatoria o fija | **Fija** por especie: menos varianza |

## Evidencia disponible

Analítica: con costo cuadrático, ir a v_max cuesta cuatro veces el término de movimiento de ir
a v_max/2. Las restricciones de coherencia (ADR-030) se verifican en P1.

## Criterio de selección

Mínimo número de reglas que hace inviables las estrategias degeneradas y mantiene el
significado de "administrar la energía".

## Decisión

- Costo por paso: c_basal + c_move·(v/v_max)².
- Invariante: todo agente vivo cumple 0 < e ≤ E_max.
- Planta: aporta `e_plant`, se consume entera, tope en E_max.
- Captura: aporta `e_prey` fijo al depredador, tope en E_max. Sin carroña.
- Inanición: e ≤ 0 tras el metabolismo (ADR-008).
- Energía inicial: E₀ = ρ₀·E_max, igual para todos los individuos de una especie.
- Posiciones iniciales uniformes; cada depredador a distancia ≥ d_safe = R_v,prey de cada
  presa, por muestreo con rechazo determinista con tope de intentos (error de configuración
  si se supera); orientaciones uniformes en [0, 2π).
- Plantas: N_plants ranuras activas en t = 0; una planta comida reaparece tras τ_regrow pasos
  fijos en la siguiente posición de una cola generada desde el flujo ENV_DYNAMICS (ADR-028).

## Consecuencias

La reaparición no consume números aleatorios según el comportamiento de los agentes.

## Verificación

F1: pruebas de metabolismo, tope, inanición, `d_safe` y cola de reaparición; P1 (F4): restricciones E1–E5.
