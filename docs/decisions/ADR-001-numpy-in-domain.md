# ADR-001: NumPy como única dependencia externa del dominio

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D1
- **Eje de la bitácora:** Ingeniería y reproducibilidad
- **Requisitos relacionados:** §3 (redes multicapa), §4 (entrenamiento real, experimentación), §9 (desarrollo funcional)

## Contexto

Clean Architecture exige que el dominio no dependa de detalles externos. Las reglas del
ecosistema (percepción, energía, capturas) y la red neuronal son el núcleo del problema, y
la experimentación exige ejecutar del orden de cientos de episodios por generación.

## Alternativas consideradas

| Alternativa | Ventajas | Inconvenientes |
|---|---|---|
| Dominio en Python puro | Pureza estricta | Lento: hace inviables los experimentos en un portátil |
| Reglas vectorizadas en infraestructura | Dominio libre de NumPy | Invierte la arquitectura: la lógica del negocio quedaría en un "detalle" |
| **NumPy permitido en el dominio como única dependencia externa** | Rendimiento y reglas en el dominio | Requiere justificar la excepción y verificarla |

## Evidencia disponible

- **Analítica (estimación):** un paso con unos 30 agentes costaría 3–5 ms en Python puro
  frente a 0.1–0.2 ms con NumPy vectorizado (30–50 veces más). Con unos 400 episodios por
  generación, Python puro supondría unos 25 minutos por generación.
- **Empírica:** pendiente; P0 (F1) mide el costo real por paso.

## Criterio de selección

Viabilidad computacional del plan experimental, manteniendo las reglas del negocio en el dominio.

## Decisión

El dominio y la aplicación solo pueden importar la biblioteca estándar y `numpy`. NumPy se
trata como el lenguaje numérico del dominio: no hace E/S, no impone un framework ni inversión
de control y no es una tecnología que el proyecto vaya a sustituir. El RNG
(`numpy.random.Generator`) siempre se inyecta.

## Consecuencias

- Las firmas del dominio usan `numpy.ndarray`.
- Cualquier otra biblioteca (yaml, pandas, scipy, matplotlib, pygame, typer, threadpoolctl)
  queda confinada a `infrastructure`, `analysis` o `presentation`.

## Verificación

- `uv run lint-imports`: contratos *layers* y *forbidden*.
- `tests/architecture/test_layer_imports.py`: lista blanca estricta (stdlib + numpy).
- Comprobado en F0 inyectando importaciones prohibidas: ambos mecanismos fallan como se espera.
