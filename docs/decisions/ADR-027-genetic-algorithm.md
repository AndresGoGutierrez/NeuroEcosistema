# ADR-027: Algoritmo de neuroevolución

- **Estado:** Aceptada (diseño consolidado; valores numéricos pendientes de P2)
- **Fecha:** 2026-11-15
- **Eje de la bitácora:** Aprendizaje
- **Requisitos relacionados:** §2 (pregunta orientadora: mejora frente a estrategias sin aprendizaje), §4 (procedimiento de entrenamiento real; evidencia de cambios en los parámetros), §5 (cómo se modifican los pesos; qué criterio se optimiza)

## Contexto

Hay que decidir cómo se modifican los pesos de las redes, que tienen topología fija (ADR-025).
La propuesta exige un procedimiento de entrenamiento real y admite, entre otros, "neuroevolución
o aprendizaje supervisado a partir de ejemplos" (§4). La elección es libre: ningún método es
obligatorio, y el descarte de las alternativas es una decisión de diseño, no un requisito.

## Alternativas consideradas

| Alternativa | Ventajas | Inconvenientes |
|---|---|---|
| NEAT | Adapta la topología al problema | Cambia la topología; complica el requisito de "≥ 2 capas ocultas" documentadas |
| Estrategias evolutivas (CMA-ES, OpenAI-ES) | Robustas en espacios continuos | Más difíciles de explicar línea por línea |
| Aprendizaje supervisado a partir de ejemplos (permitido por §4), p. ej. imitando la política por reglas (*behavioral cloning*) | Eficiente (descenso de gradiente); entrenamiento estable; curva de pérdida fácil de interpretar | Ver el análisis siguiente |
| Aprendizaje por refuerzo con gradiente (p. ej. *policy gradient*) | Optimiza directamente el desempeño; aprovecha la información de cada paso del episodio | **No evaluado en profundidad.** Mayor complejidad para un proyecto individual: asignación de crédito temporal, alta varianza de los estimadores y más hiperparámetros |
| Híbrido: preentrenamiento supervisado y posterior neuroevolución | Podría acelerar el inicio partiendo de una política competente | Reintroduce la dependencia de la política de referencia. **Fuera del alcance actual;** candidato al eje "Mejora" |
| **Algoritmo genético con codificación directa, implementado en NumPy** | Optimiza directamente el criterio ecológico; no requiere maestro ni diferenciabilidad; explicable línea por línea | Costo computacional alto (muchos episodios por generación); fitness ruidoso; riesgo de explotación del criterio (ADR-019); escala peor con la dimensión |

### Análisis del aprendizaje supervisado

1. **Optimiza un objetivo indirecto:** minimiza el error al imitar las acciones de una política de
   referencia, en lugar de optimizar directamente el desempeño ecológico (supervivencia o
   capturas, ADR-026).
2. **No incorpora por sí mismo un mecanismo explícito para descubrir estrategias que superen al
   maestro.** En determinadas condiciones la red imitadora puede obtener mejores resultados que
   la referencia (por ejemplo, por diferencias de generalización), pero ese resultado no es algo
   que el método persiga.
3. **Puede sufrir desplazamiento de distribución:** cuando la red visita estados distintos de los
   observados durante el entrenamiento, sus errores pueden acumularse (Ross, Gordon y Bagnell, 2011).
4. **Introduce una dependencia de la calidad y las limitaciones de la política de referencia:**
   sus sesgos y defectos se trasladan a los datos de entrenamiento.
5. **Dificultaría estudiar de forma independiente la pregunta orientadora (§2):** si la red se
   entrena para parecerse a la política por reglas, la comparación con estrategias sin
   aprendizaje (C3) deja de ser una evaluación independiente, porque la referencia también sería
   el maestro.

## Evidencia disponible

- **Analítica:** el resultado de un episodio depende de eventos discretos (capturas, muertes), por
  lo que el criterio ecológico no es diferenciable respecto de los pesos; la neuroevolución lo
  optimiza sin gradientes. La codificación directa conserva la topología y una implementación
  propia es completamente explicable.
- **Bibliográfica:** desplazamiento de distribución en el aprendizaje por imitación (Ross, Gordon
  y Bagnell, 2011, *A Reduction of Imitation Learning and Structured Prediction to No-Regret
  Online Learning*).
- **Empírica:** pendiente; problema de juguete y curvas de entrenamiento (F6).

## Criterio de selección

1. Coherencia con la pregunta orientadora (§2): optimizar directamente el desempeño ecológico,
   de forma independiente de las políticas sin aprendizaje con las que se compara.
2. Capacidad de explicar y defender cada paso en la sustentación (§8, §9).

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

- ‖w − w₀‖ y los checkpoints de la generación 0 y final son la evidencia de cambio en los
  parámetros que exige §4.
- No se necesitan retropropagación, optimizadores de gradiente ni dependencias adicionales.
- **Limitación:** las conclusiones experimentales corresponden al algoritmo genético seleccionado
  y no pueden generalizarse automáticamente a otros métodos de entrenamiento, que no se comparan.

## Verificación

F6: élites conservados, torneo determinista, σ de mutación correcto, mejora en un problema de
juguete (función esfera), curvas registradas.
