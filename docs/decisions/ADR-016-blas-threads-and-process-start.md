# ADR-016: Hilos de BLAS, arranque de procesos y alcance del determinismo

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D16
- **Eje de la bitácora:** Ingeniería y reproducibilidad
- **Requisitos relacionados:** §4 (reproducibilidad), §9 (documentación y reproducibilidad)

## Contexto

Los resultados de BLAS pueden depender del número de hilos. Fijar variables de entorno después
de importar NumPy no tiene efecto, y con `fork` los procesos hijos heredan el estado ya inicializado.

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| Variables de entorno antes de crear el pool | El proceso principal ya importó NumPy; no funciona con `fork` ni en pytest o notebooks |
| **Control en tiempo de ejecución con threadpoolctl + `spawn` + variables tempranas + verificación** | Una dependencia de infraestructura adicional |
| `NPY_DISABLE_CPU_FEATURES` / `OPENBLAS_CORETYPE` para igualar máquinas | Cuesta rendimiento y no garantiza igualdad |

## Evidencia disponible

Analítica: `threadpool_limits` modifica los pools de bibliotecas ya cargadas (OpenBLAS, MKL, BLIS).

## Criterio de selección

Mecanismo válido sin importar el orden de importación, y verificable.

## Decisión

1. `threadpoolctl.threadpool_limits(1)` en el proceso principal (al hacer bootstrap) y en el
   *initializer* de cada worker. Es el mecanismo que manda.
2. Contexto `multiprocessing` con `spawn` en todos los sistemas operativos.
3. Complemento: un lanzador fija `OMP`, `OPENBLAS`, `MKL`, `BLIS`, `VECLIB` y `NUMEXPR_NUM_THREADS=1`
   antes de cualquier importación; `neuroeco/__init__.py` queda vacío a propósito.
4. `threadpool_info()` se registra en el manifest; los experimentos formales se abortan si
   algún pool tiene más de un hilo.

## Consecuencias

- Reproducibilidad bit a bit: misma máquina y mismo `uv.lock`. Entre máquinas: estadística.
- La forma del lote puede cambiar el kernel de BLAS y el último bit de una salida; las pruebas
  que comparan lotes de forma distinta usan tolerancia.

## Verificación

F6: prueba D3 (secuencial = 1 worker = 4 workers, bit a bit) y verificación de un hilo en el manifest.
