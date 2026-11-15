# ADR-011: Simplificaciones del modelo físico

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D11
- **Eje de la bitácora:** Representación del entorno
- **Requisitos relacionados:** §4 (reglas de movimiento), §11 (demostrar con evidencia qué decisiones funcionan)

## Contexto

Cada regla física adicional añade parámetros, posibles explotaciones y explicaciones necesarias
en la sustentación.

## Alternativas consideradas

| Regla | Incluirla aporta | Decisión |
|---|---|---|
| Colisiones entre agentes | Realismo espacial | **No**: los agentes pueden solaparse |
| Oclusión de la visión | Realismo perceptivo | **No**: no hay obstáculos (ADR-002) |
| Inercia o aceleración | Dinámica más realista | **No**: la velocidad se aplica de inmediato |
| Costo energético de girar | Penalizar giros | **No** |
| Carroña | Energía de presas muertas de hambre | **No** |
| Enfriamiento tras capturar | Tiempo de manipulación | **No**, más allá de una captura por paso (ADR-009) |

## Evidencia disponible

Analítica: ninguna de estas reglas es exigida por la propuesta. Girar en círculos (riesgo
de no tener costo de giro) se vigila con la sonda SPIN y el diagnóstico `turn_saturation` (ADR-019).

## Criterio de selección

Mínima complejidad compatible con los requisitos y con la capacidad de explicar el modelo.

## Decisión

Se adoptan todas las simplificaciones de la tabla.

## Consecuencias

Limitaciones de realismo declaradas en el informe; posibles propuestas de mejora.

## Verificación

P1 (F4): sondas degeneradas; F8: diagnósticos de comportamiento.
