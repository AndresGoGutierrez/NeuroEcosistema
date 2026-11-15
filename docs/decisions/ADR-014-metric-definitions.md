# ADR-014: Definición operativa de las métricas

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D14
- **Eje de la bitácora:** Diseño experimental
- **Requisitos relacionados:** §6 (supervivencia media, alimento consumido, capturas, energía final, tiempo hasta captura, variabilidad)

## Contexto

§6 enumera métricas sin definirlas. Varias admiten lecturas distintas que cambian los resultados.

## Alternativas consideradas

| Métrica | Alternativa descartada | Motivo |
|---|---|---|
| Tiempo hasta captura | Kaplan-Meier tratando la inanición como censura | La inanición es un **riesgo competitivo**: sobrestima la captura, sobre todo en escasez |
| Tiempo hasta captura | Media entre presas capturadas | Sesgo por condicionar a la captura |
| Tiempo hasta la primera captura | — | No es obligatorio y también sufre riesgos competitivos: eliminado |
| Efecto por episodio | Mediana de diferencias con bootstrap | Inestable con métricas discretas |

## Evidencia disponible

Analítica: en los episodios de prueba no hay censura antes de T_max (todas las presas se siguen
hasta morir o hasta T_max). Con riesgos competitivos y censura solo al final, el estimador de
Aalen-Johansen se reduce a la proporción empírica acumulada.

## Criterio de selección

Ausencia de sesgo y correspondencia exacta con lo que se mide.

## Decisión

| Métrica (§6) | Definición |
|---|---|
| Supervivencia media de las presas | Media de t_muerte/T_max (T_max si sobrevive) y fracción de presas vivas en T_max |
| Alimento consumido | Plantas comidas por episodio y por presa |
| Capturas | Total por episodio, por depredador y tasa ajustada por exposición (capturas / Σ pasos-presa vivos) |
| Energía final | (a) Media entre supervivientes; (b) media poblacional con los muertos como 0 |
| Tiempo hasta captura | Incidencia acumulada empírica de captura y de inanición: CIF_captura(t) = capturadas hasta t / n_prey; se reportan las curvas apiladas, CIF_captura(T_max) y la mediana del tiempo de captura entre las capturadas (condicional, etiquetada) |
| Variabilidad | Desviación estándar e IQR entre semillas y entre ejecuciones |

Métricas primarias: supervivencia media (presa) y fracción capturada (depredador). Las métricas
primarias por ejecución se almacenan como numeradores enteros con denominador común (ADR-017).
Efecto por episodio (descriptivo): diferencia **media** pareada con IC BCa.

## Consecuencias

En cada t: vivas + capturadas + muertas de hambre = n_prey.

## Verificación

F1: pruebas de las métricas sobre registros sintéticos, incluida la identidad anterior.
