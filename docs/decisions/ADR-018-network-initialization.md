# ADR-018: Inicialización de las redes

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D18
- **Eje de la bitácora:** Diseño de las redes
- **Requisitos relacionados:** §4 (activaciones y parámetros documentados), §5 (por qué esas activaciones)

## Contexto

La inicialización determina si las redes aleatorias de la generación 0 están saturadas,
inertes o en un régimen útil. Nuestras entradas valen 0 a menudo, así que E[x²] es menor que 1.

## Alternativas consideradas

| Alternativa | Valoración |
|---|---|
| Glorot: Var = 2/(fan_in + fan_out) | Equilibra la varianza de los gradientes hacia atrás; en neuroevolución no hay gradientes |
| **LeCun: Var = 1/fan_in** | Criterio de propagación hacia delante, coherente con tanh |
| Inicialización dependiente de los datos | Solo si la prueba de inercia falla |

## Evidencia disponible

- Analítica (LeCun et al., 1998): con entradas de varianza unitaria, la preactivación tiene
  varianza 1 y tanh opera en su zona casi lineal.
- Empírica: pendiente (prueba I2 en F5).

## Criterio de selección

Evitar la saturación y la inercia iniciales.

## Decisión

- **w ~ Normal(media 0, varianza 1/fan_in)**, es decir, desviación estándar 1/√fan_in. Sesgos en 0.
- Desviaciones resultantes: fan_in 7 → 0.378; 8 → 0.354; 10 → 0.316; 16 → 0.250.
- Ganancia g = 1 (σ = g/√fan_in); solo cambia, con un nuevo ADR, si falla S3.
- **I1 (unitaria):** 10⁶ pesos con fan_in = 16 → varianza muestral 1/16 ± 2 %.
- **I2 (saturación inicial):** conjunto de observaciones de referencia tomado de episodios con
  políticas por reglas en A, B y C (semillas PILOT, una de cada 10 muestras), guardado en `.npz`
  con hash; 100 genomas aleatorios.
  - S1: fracción de pares (muestra, neurona) con |a| > 0.95: mediana ≤ 10 % por capa.
  - S2: neuronas saturadas en ≥ 90 % de las muestras: mediana ≤ 5 %.
  - S3: desviación estándar de cada salida: mediana ≥ 0.1.
- S1 y S2 del élite se monitorizan en cada checkpoint sobre el mismo conjunto.

## Consecuencias

El conjunto de referencia es un artefacto versionado y reproducible.

## Verificación

F5: I1 e I2 como criterios de cierre de fase.
