# ADR-006: Entrenamiento por especie frente a un oponente fijo y juego cruzado

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D6
- **Eje de la bitácora:** Aprendizaje
- **Requisitos relacionados:** §4 (decisiones generadas por redes; entrenamiento real), §10 (al menos una población neuronal; especies diferenciadas)

## Contexto

Ambas especies usan redes neuronales independientes. Entrenarlas a la vez (coevolución) hace
que el fitness de cada una dependa de la otra.

## Alternativas consideradas

| Alternativa | Ventajas | Inconvenientes |
|---|---|---|
| Coevolución simultánea desde el inicio | Interacción entre aprendices | Objetivo no estacionario; ciclos y olvido; fitness no comparable entre generaciones |
| **Etapa 1: cada especie frente a un oponente por reglas fijo; juego cruzado descriptivo** | Evidencia limpia antes/después y frente a la referencia | La generalización a otros oponentes debe medirse aparte (ADR-019) |
| Coevolución alternada con Hall of Fame | Mitiga ciclos | Más complejidad; no es obligatoria |

## Evidencia disponible

Analítica y bibliográfica: la coevolución competitiva presenta dinámicas de "Reina Roja" y
ciclos que dificultan medir el progreso sin oponentes de referencia fijos.

## Criterio de selección

Garantizar resultados válidos para las comparaciones obligatorias antes de añadir riesgo.

## Decisión

- Etapa 1 (obligatoria para los resultados): presa frente a depredador por reglas y
  depredador frente a presa por reglas, por escenario.
- Ecosistema completo: juego cruzado entre redes entrenadas, descriptivo y para la demo.
- Coevolución alternada: opcional, solo después del cierre de F8 y sin bloquear F9.

## Consecuencias

Ambas especies son neuronales en la demo y en el juego cruzado, sin depender de la coevolución.

## Verificación

F6–F8: entrenamientos por especie; juego cruzado en la matriz de generalización (ADR-019).
