# NeuroEcosistema: depredadores y presas

Simulación 2D en la que dos poblaciones de agentes autónomos —presas y depredadores— toman
decisiones de movimiento mediante redes neuronales multicapa entrenadas por neuroevolución.
El objetivo del proyecto no es producir el ecosistema "más inteligente", sino demostrar con
evidencia reproducible qué decisiones de modelado y entrenamiento funcionan, cuáles no y por qué.

Proyecto final integrador — Electiva I de Profundización: Inteligencia Artificial,
Facultad de Ingeniería de Sistemas, Universidad Santo Tomás, seccional Tunja.
Los requisitos provienen de la propuesta académica del curso, que es el documento de referencia
del proyecto y no se incluye en este repositorio. Las secciones de la propuesta se citan como
§1–§11 en la documentación.

## Estado

| Fase | Contenido | Estado |
|---|---|---|
| F0 | Fundaciones: repositorio, entorno, contratos de arquitectura, decisiones (ADR) | Cerrada |
| F1 | Núcleo de simulación y piloto P0 | Cerrada (P0 con plan de optimización) |
| F2 | Visualización: visor, HUD, inspector y registro de `--set` | Completada |
| F3 | Estadística: métodos de ADR-013, ADR-014 y ADR-017 y pruebas de cobertura | En curso |
| F4–F9 | Calibración, redes, neuroevolución, protocolo, experimentos, entregables | Pendientes |

El plan completo y los criterios de cierre de cada fase están en
[docs/decisions/ADR-024-phase-plan-and-gates.md](docs/decisions/ADR-024-phase-plan-and-gates.md)
y el registro de cierres en [docs/phase_gates.md](docs/phase_gates.md).

## Requisitos

- [uv](https://docs.astral.sh/uv/) ≥ 0.12. uv descarga e instala Python 3.12 si no está presente.
- Windows, Linux o macOS.

## Instalación

```bash
git clone <url-del-repositorio>
cd <carpeta-del-repositorio>
uv sync --frozen
```

`uv sync --frozen` instala exactamente las versiones registradas en `uv.lock`
(Python 3.12 según `.python-version`), sin volver a resolver dependencias.

## Verificación

```bash
uv run ruff check .          # estilo y reglas (incluye la prohibición del RNG global)
uv run ruff format --check . # formato
uv run lint-imports          # contratos de Clean Architecture
uv run pytest                # pruebas
```

## Estructura

```
configs/          Configuración YAML (semilla del proyecto en base.yaml)
src/neuroeco/
  domain/         Reglas del ecosistema, percepción, políticas, redes, evolución (stdlib + numpy)
  application/    Casos de uso, puertos, semillas, métricas
  infrastructure/ Adaptadores: configuración, almacenamiento, ejecución, entorno de ejecución
  analysis/       Estadística y reportes (solo lee archivos de resultados)
  presentation/   CLI y visor
tests/            Pruebas (incluye pruebas de arquitectura)
docs/             Documentación académica (en español)
```

La regla de dependencias es `presentation → infrastructure → application → domain`; el dominio
solo puede importar la biblioteca estándar y `numpy`. Se verifica con `lint-imports` y con
`tests/architecture`. Detalle en [docs/architecture.md](docs/architecture.md).

## Reproducibilidad

- Dependencias fijadas en `uv.lock`; versión de Python fijada en `.python-version`.
- Toda la aleatoriedad deriva de `project_seed` (`configs/base.yaml`) mediante
  `numpy.random.SeedSequence` con claves de seis campos enteros
  ([ADR-028](docs/decisions/ADR-028-seed-scheme.md)). El módulo `random` y la API global
  `np.random.*` están prohibidos por `ruff`.
- La reproducibilidad bit a bit se garantiza en la misma máquina con el mismo `uv.lock`; entre
  máquinas es estadística ([ADR-016](docs/decisions/ADR-016-blas-threads-and-process-start.md)).

## Documentación

- [Decisiones técnicas (bitácora)](docs/decisions/README.md)
- [Arquitectura](docs/architecture.md)
- [Registro de cierre de fases](docs/phase_gates.md)
- [Declaración de uso de IA generativa](docs/ai_usage_statement.md)
