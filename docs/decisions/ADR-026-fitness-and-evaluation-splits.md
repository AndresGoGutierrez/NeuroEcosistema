# ADR-026: Funciones de aptitud y separación entrenamiento/validación/prueba

- **Estado:** Aceptada (diseño consolidado)
- **Fecha:** 2026-11-15
- **Eje de la bitácora:** Aprendizaje
- **Requisitos relacionados:** §5 (qué criterio se optimiza y qué comportamientos podría favorecer indebidamente), §6 (comparación antes y después del entrenamiento)

## Contexto

Cada especie necesita un criterio escalar para la selección. Además, hay que distinguir el
fitness que guía el entrenamiento de la evidencia con la que se sacan conclusiones.

## Alternativas consideradas

| Especie | Alternativa | Riesgo |
|---|---|---|
| Presa | Alimento consumido | Comer de forma temeraria e ignorar a los depredadores |
| Presa | Combinación ponderada | Pesos arbitrarios |
| Presa | **Supervivencia media** | Esconderse o quedarse quieto: mitigado por el toro (ADR-002) y la inanición (ADR-030, E1) |
| Depredador | Capturas + λ·energía final | **Premia quedarse quieto**: descartada |
| Depredador | Capturas − μ·distancia (*shaping*) | Premia perseguir sin capturar |
| Depredador | **Fracción capturada** | Señal escasa al inicio: curriculum condicional |

## Evidencia disponible

Analítica: como la energía decae, sobrevivir obliga a comer; perseguir cuesta energía de forma
cuadrática. Empírica: sondas en P1 y diagnósticos (ADR-019).

## Criterio de selección

Un solo término por especie, sin pesos arbitrarios; el resto de los objetivos se obtiene de la
dinámica del mundo.

## Decisión

- **F_prey** = (1/n_prey)·Σᵢ tᵢ/T_max (tᵢ = paso de muerte o T_max).
- **F_pred** = capturas totales / n_prey inicial.
- Evaluación por equipos clonados: el fitness del genoma es el del equipo.

| Concepto | Semillas | Uso | ¿Debe mejorar siempre? |
|---|---|---|---|
| F_train | TRAIN, nuevas en cada generación y comunes a todos los genomas | Única señal de selección | No |
| F_val | VALIDATION, fijas | Elegir el modelo y medir la brecha de generalización | **No** |
| Rendimiento experimental | TEST, nunca vistas | Conclusiones de C1–C3 (métricas de ADR-014) | — |

- F_train y F_val usan la misma fórmula.
- **Selección del modelo:** checkpoint con mayor F_val; empate → el más temprano. Se reporta
  también el élite de la última generación.
- **Curriculum condicional:** si en P2 más del 80 % de los genomas de depredador tienen fitness
  0 durante las primeras 10 generaciones, el radio de captura de entrenamiento empieza en
  κ·r_capture y baja linealmente hasta r_capture en G_c generaciones. Validación y prueba usan
  siempre el radio nominal. La brecha F_train–F_val solo se analiza tras el curriculum.

## Consecuencias

Los comportamientos indebidos se detectan con ADR-019 y no se corrigen con penalizaciones.

## Verificación

F6: pruebas de las funciones de fitness y de la regla de selección; decisión sobre el curriculum en P2.
