# ADR-012: Políticas de referencia, variantes y sondas

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D12
- **Eje de la bitácora:** Diseño experimental
- **Requisitos relacionados:** §4 y §6 (referencia aleatoria o basada en reglas), §5 (qué comportamientos podría favorecer indebidamente el criterio)

## Contexto

Se necesitan referencias sin aprendizaje para C3, oponentes fijos para entrenar, oponentes
alternativos para medir la generalización y políticas degeneradas para detectar explotaciones.

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| Solo política aleatoria | Referencia débil: la comparación sería un "hombre de paja" |
| Política por reglas con información privilegiada | La comparación mediría información, no el modelo de decisión |
| **Reglas con las mismas entradas que la red, más aleatoria, variantes y sondas** | — |

## Evidencia disponible

Analítica: usar las mismas entradas y el mismo decodificador aísla el efecto del modelo de decisión.

## Criterio de selección

Comparaciones justas y una referencia competente.

## Decisión

Todas las políticas producen la misma salida bruta en [−1, 1]² y comparten el decodificador.
El giro hacia un ángulo α es o₀ = clip(α/ω_max, −1, 1), con φ = atan2(left, forward).

- **Presa por reglas:** si `predator1_proximity` > `p_flee`, gira hacia φ_pred1 + π a velocidad
  máxima; si no, y ve una planta, va hacia ella a velocidad máxima; si no, sigue recta a `u_cruise`.
- **Depredador por reglas:** si ve una presa, va hacia `prey1` a velocidad máxima; si no, sigue
  recto a `u_cruise`.
- `p_flee` y `u_cruise` se ajustan en P1 con una rejilla pequeña y se congelan.
- **Variantes (solo para evaluar, ADR-019):** depredador con `u_cruise` × 0.75 y × 1.25;
  presa con `p_flee` − 0.1 y + 0.1.
- **Aleatoria:** o₀, o₁ ~ U[−1, 1] independientes en cada paso.
- **Sondas (solo diagnóstico):** políticas constantes STILL, SPIN, STRAIGHT_MAX y STRAIGHT_CRUISE.

## Consecuencias

La referencia confirmatoria de C3 es la política por reglas; la aleatoria es descriptiva (ADR-017).

## Verificación

F1: las tres políticas y las sondas ejecutan episodios en todos los escenarios; P1: ajuste y congelamiento.
