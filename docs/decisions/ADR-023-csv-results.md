# ADR-023: Resultados en CSV

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D23
- **Eje de la bitácora:** Ingeniería y reproducibilidad
- **Requisitos relacionados:** §7.5 (evidencia experimental que permita revisar las conclusiones)

## Contexto

Las métricas de generación y de episodio deben persistirse para el análisis y para la revisión externa.

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| Parquet (pyarrow) | Dependencia pesada; no se abre directamente en una hoja de cálculo |
| **CSV con tipos explícitos** | Archivos algo más grandes |

## Evidencia disponible

Analítica: el volumen esperado es del orden de miles de filas por experimento; no se almacenan
trayectorias paso a paso (se re-simulan gracias al determinismo).

## Criterio de selección

Facilidad de revisión por terceros con el menor número de dependencias.

## Decisión

Métricas en CSV con columnas y tipos documentados; modelos en `.npz` con metadatos JSON.
Se elimina pyarrow de las dependencias.

## Consecuencias

`analysis` lee CSV con pandas especificando tipos.

## Verificación

F8: `analyze` regenera las tablas de forma idéntica a partir de los CSV.
