# Arquitectura

Este documento resume la arquitectura aprobada al cierre del diseño (2026-11-15). Las razones
de cada decisión están en la [bitácora de decisiones](decisions/README.md).

## Capas y regla de dependencias

```
launcher (fija el entorno numérico y arranca la CLI)
        │
        ▼
presentation (cli, viewer, inspector)
        │
        ▼
bootstrap (composition root) ──instancia──► infrastructure
        │                                   (config_loader, storage, executors,
        ▼                                    runtime_env, provenance)
application (ports, configs, seeding, metrics,          │ implementa los puertos
             training, evaluation, session) ◄───────────┘
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
| `bootstrap` | `infrastructure`, `application`, `domain` | Raíz de composición: carga la configuración, crea el `SeedRegistry` y construye las políticas por nombre |
| `presentation` | todas las anteriores | CLI y visor de solo lectura |
| `launcher` | `presentation` | Punto de entrada `neuroeco`: fija las variables de hilos antes de importar numpy (ADR-016) |
| `analysis` | bibliotecas científicas; **no** importa el núcleo | Pruebas estadísticas, tablas y figuras a partir de archivos de resultados |

Ejecución exploratoria: `uv run neuroeco run --scenario A --prey rules --predator rules`. Usa
semillas del propósito PILOT con el `seed_group` 0, **reservado para ejecuciones exploratorias**;
los pilotos formales declaran su propio `seed_group` (ADR-028).

## Verificación automática de la arquitectura

| Mecanismo | Qué comprueba |
|---|---|
| `lint-imports`, contrato *layers* | `launcher → presentation → bootstrap → infrastructure → application → domain`, sin dependencias hacia arriba |
| `lint-imports`, contrato *forbidden* | `domain` y `application` no importan `yaml`, `pandas`, `scipy`, `matplotlib`, `pygame`, `typer` ni `threadpoolctl` |
| `lint-imports`, contrato *forbidden* | `pygame` solo se usa en `presentation`: no lo importan `bootstrap`, `infrastructure`, `application`, `domain` ni `analysis` (ADR-031) |
| `lint-imports`, contrato *forbidden* | `analysis` no importa `domain`, `application`, `infrastructure` ni `presentation` |
| `tests/architecture/test_layer_imports.py` | Lista blanca estricta: cualquier importación de `domain` o `application` que no sea stdlib, `numpy` o un paquete interno permitido hace fallar la prueba (incluye importaciones relativas) |
| `ruff` (TID251, NPY002) | Prohíbe el módulo `random` y la API global heredada `np.random.*` en todo el código |

## Pruebas de determinismo

Catálogo de pruebas de reproducibilidad (ADR-016, ADR-028). Se identifican como DET-n para no
confundirlas con las decisiones de diseño D1–D24.

| ID | Comprobación | Fase |
|---|---|---|
| DET-1 | El mismo episodio ejecutado dos veces en el mismo proceso produce el mismo hash SHA-256 del estado en cada paso | F1 |
| DET-2 | El mismo episodio ejecutado en un proceso independiente produce el mismo hash | F1 |
| DET-3 | Ejecutor secuencial, pool de 1 worker y pool de 4 workers producen resultados idénticos bit a bit | F6 |
| DET-4 | Guardar y cargar un modelo conserva sus salidas | F5 |
| DET-5 | Cambiar de política con la misma semilla conserva el entorno: posiciones iniciales y cola de reaparición de plantas | F1 |
| DET-6 | Regresión de métricas resumen entre máquinas, con tolerancia | F6 |

La reproducibilidad bit a bit se exige en la misma máquina con el mismo `uv.lock`; entre
máquinas es estadística (ADR-016).

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
   cambios de parámetros se hacen al lanzar (`--set`) y quedan registrados. El visor es un
   observador síncrono del simulador que solo recibe copias de solo lectura (ADR-031); las
   activaciones se añaden en F5.
4. **Reproducción:** `uv sync --frozen` → pruebas → entrenamientos → experimentos → análisis.
