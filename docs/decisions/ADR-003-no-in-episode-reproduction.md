# ADR-003: Sin reproducción dentro del episodio

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D3
- **Eje de la bitácora:** Representación del entorno
- **Requisitos relacionados:** §4 (finalización de episodios, entrenamiento)

## Contexto

Hay que decidir si las poblaciones crecen dentro de un episodio o si el relevo entre
individuos lo hace el algoritmo de entrenamiento.

## Alternativas consideradas

| Alternativa | Ventajas | Inconvenientes |
|---|---|---|
| Reproducción dentro del episodio | Dinámicas poblacionales cíclicas | El fitness depende de la descendencia; episodios no comparables; más reglas |
| **Sin reproducción; relevo generacional por el algoritmo genético** | Evaluación episódica controlada y comparable | No aparecen ciclos poblacionales |

## Evidencia disponible

Analítica: con poblaciones fijas al inicio, cada episodio evalúa una política en condiciones
iniciales comparables, lo que permite semillas comunes entre condiciones (ADR-028).

## Criterio de selección

Comparabilidad y control experimental, que son el 25 % de la rúbrica.

## Decisión

Los agentes no se reproducen. Las poblaciones solo decrecen (capturas e inanición). La
"reproducción" ocurre entre generaciones del algoritmo genético.

## Consecuencias

- Las curvas poblacionales son curvas de supervivencia, no ciclos tipo Lotka-Volterra.
- Limitación declarada en el informe.

## Verificación

F1: prueba de invariante: vivas + capturadas + muertas de hambre = n_prey en cada paso.
