# Arquitectura

Este documento resume la arquitectura aprobada al cierre del diseño (2026-11-15). Las razones
de cada decisión están en la [bitácora de decisiones](decisions/README.md).

## Capas y regla de dependencias

```
presentation (cli, viewer, inspector)
        │
launcher → bootstrap (composition root) ──instancia──► infrastructure
        │                                              (config_loader, storage, executors,
        ▼                                               runtime_env, provenance)
application (ports, configs, seeding, metrics,                 │ implementa los puertos
             training, evaluation, session) ◄──────────────────┘
        │
        ▼
domain  [solo biblioteca estándar + numpy]

analysis (stats, report) ── solo lee ──► results/*.csv
```

| Capa | Puede importar | Responsabilidad |
|---|---|---|
| `domain` | stdlib, `numpy`, `neuroeco.domain` | Reglas del ecosistema, percepción, acciones, políticas, red neuronal, algoritmo genético, fitness |
| `application` | lo anterior y `neuroeco.application` | Casos de uso (entrenar, evaluar, sesión interactiva), puertos, política de semillas, métricas |
| `infrastructure` | capas inferiores y bibliotecas de E/S | Implementación de los puertos: YAML, CSV, `.npz`, JSON, pool de procesos, control de hilos BLAS, procedencia |
| `presentation` | todas las anteriores | CLI y visor de solo lectura |
| `analysis` | bibliotecas científicas; **no** importa el núcleo | Pruebas estadísticas, tablas y figuras a partir de archivos de resultados |

`launcher.py` y `bootstrap.py` se crean en F1, cuando exista el primer punto de entrada.

## Verificación automática de la arquitectura

| Mecanismo | Qué comprueba |
|---|---|
| `lint-imports`, contrato *layers* | `presentation → infrastructure → application → domain`, sin dependencias hacia arriba |
| `lint-imports`, contrato *forbidden* | `domain` y `application` no importan `yaml`, `pandas`, `scipy`, `matplotlib`, `pygame`, `typer` ni `threadpoolctl` |
| `lint-imports`, contrato *forbidden* | `analysis` no importa `domain`, `application`, `infrastructure` ni `presentation` |
| `tests/architecture/test_layer_imports.py` | Lista blanca estricta: cualquier importación de `domain` o `application` que no sea stdlib, `numpy` o un paquete interno permitido hace fallar la prueba (incluye importaciones relativas) |
| `ruff` (TID251, NPY002) | Prohíbe el módulo `random` y la API global heredada `np.random.*` en todo el código |

## Estructura prevista

```
src/neuroeco/
  __init__.py   vacío a propósito (ADR-016)
  launcher.py   fija el entorno numérico antes de importar numpy (F1)
  bootstrap.py  composition root (F1)
  domain/       params, geometry, state, rules, interactions, perception, actions,
                policies, neural, evolution, fitness, simulator, records
  application/  ports, configs, seeding, metrics, training, evaluation, session
  infrastructure/ config_loader, storage, executors, runtime_env, provenance
  analysis/     stats, report
  presentation/ cli, viewer, inspector
```

Los módulos se crean en la fase que los necesita (ADR-024).

## Interfaces principales

| Interfaz | Capa | Contrato |
|---|---|---|
| `Policy` (protocolo) | domain | `act(observations[n, d_in], rng) → raw_actions[n, 2]` en [−1, 1]. Implementaciones: aleatoria, por reglas, constante (sondas), neuronal y envoltorio de ablación de entradas |
| `TaskExecutor` (puerto) | application | `map(fn, tasks)` devuelve los resultados en el orden de entrada |
| `RunStore` (puerto) | application | Ciclo de vida de una ejecución: manifest, checkpoints, filas de métricas |
| `ModelStore` (puerto) | application | Guardar y cargar modelos; rechaza modelos con un esquema de entradas distinto |

Solo `Policy` es un protocolo dentro del dominio porque es la única abstracción con varias
implementaciones; el resto son clases y funciones concretas (ADR-021).

## Flujos de ejecución

1. **Entrenamiento:** configuración → registro de la ejecución → por generación: `ask` →
   evaluación en paralelo con semillas comunes → `tell` → métricas → cada k generaciones,
   validación y checkpoint → selección del modelo por F_val.
2. **Experimento:** condiciones × escenarios × semillas de prueba → CSV en `results/` →
   `analysis` genera tablas, figuras, intervalos y pruebas.
3. **Demostración:** visor con HUD e inspector de entradas, activaciones y acciones; los
   cambios de parámetros se hacen al lanzar (`--set`) y quedan registrados.
4. **Reproducción:** `uv sync --frozen` → pruebas → entrenamientos → experimentos → análisis.
