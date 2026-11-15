# ADR-027: Algoritmo de neuroevolución

- **Estado:** Aceptada (diseño consolidado; valores numéricos pendientes de P2)
- **Fecha:** 2026-11-15
- **Eje de la bitácora:** Aprendizaje
- **Requisitos relacionados:** §4 (procedimiento de entrenamiento real; evidencia de cambios en los parámetros), §5 (cómo se modifican los pesos)

## Contexto

Las redes tienen topología fija (ADR-025) y se entrenan sin ejemplos etiquetados.

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| NEAT | Cambia la topología; complica el requisito de "≥ 2 capas ocultas" documentadas |
| Estrategias evolutivas (CMA-ES, OpenAI-ES) | Más difíciles de explicar línea por línea |
| Aprendizaje supervisado a partir de ejemplos (permitido por §4), p. ej. imitando la política por reglas | El desempeño quedaría acotado por el del maestro y C3 compararía la red con su propio maestro (ver nota) |
| **Algoritmo genético con codificación directa, implementado en NumPy** | Escala peor con la dimensión |

> **Nota, pendiente de revisión del autor:** la elección de neuroevolución está aprobada, pero el
> motivo para descartar el aprendizaje supervisado que figura en la tabla no se discutió durante el
> diseño. Se registra como justificación provisional.

## Evidencia disponible

Analítica: la codificación directa conserva la topología; una implementación propia es
completamente explicable. Empírica: problema de juguete y curvas de entrenamiento (F6).

## Criterio de selección

Capacidad de explicar y defender cada paso en la sustentación (§8, §9).

## Decisión

- Genoma: vector de todos los pesos y sesgos. Interfaz *ask/tell*.
- Inicialización: ADR-018 (flujo GA_INIT).
- Evaluación: equipo clonado frente al oponente por reglas; E episodios con semillas comunes por
  generación; fitness = media.
- Elitismo de k individuos, **reevaluados** en cada generación.
- Selección por torneo de tamaño t.
- Mutación gaussiana aditiva sobre todos los pesos con σ propio de cada arquitectura (P2b).
- **Sin cruce** en la línea base (problema de permutación de las redes).
- G fijo, sin parada temprana. Validación y checkpoint cada k_val generaciones.
- Registro por generación: fitness máximo, medio, mediano y desviación; diversidad; ‖w‖ y
  ‖w − w₀‖; saturación (ADR-018).
- N, E, V, G, σ, k y t se fijan en P2 (k = 2 y t = 3 por defecto; se cambian solo si se pierde diversidad).

## Consecuencias

‖w − w₀‖ y los checkpoints de la generación 0 y final son la evidencia de cambio en los
parámetros que exige §4.

## Verificación

F6: élites conservados, torneo determinista, σ de mutación correcto, mejora en un problema de
juguete (función esfera), curvas registradas.
