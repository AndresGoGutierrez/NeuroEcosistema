# ADR-015: Terminación anticipada de episodios de entrenamiento

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D15
- **Eje de la bitácora:** Aprendizaje
- **Requisitos relacionados:** §4 (finalización de episodios)

## Contexto

En el entrenamiento de depredadores, si mueren todos, el episodio seguiría simulando presas
sin que el fitness pueda cambiar.

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| Regla única para todos los episodios | Cómputo inútil en entrenamiento |
| Terminar cuando muere cualquier especie | Cambia las métricas de la presa en la prueba |
| **Terminar antes solo si el fitness ya no puede cambiar** | — |

## Evidencia disponible

Analítica: F_pred depende solo de las capturas, y sin depredadores vivos no hay más capturas.

## Criterio de selección

Ahorro de cómputo sin alterar ningún valor medido.

## Decisión

- Episodios de **entrenamiento y validación de depredadores**: terminan también cuando mueren
  todos los depredadores.
- Episodios de **prueba**: siempre la regla completa (T_max o sin presas vivas).

## Consecuencias

Ninguna sobre las métricas reportadas.

## Verificación

F6: prueba que compara el fitness con y sin terminación anticipada en los mismos episodios.
