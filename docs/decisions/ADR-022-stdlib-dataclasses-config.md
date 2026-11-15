# ADR-022: Configuración con dataclasses de la biblioteca estándar

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D22
- **Eje de la bitácora:** Ingeniería y reproducibilidad
- **Requisitos relacionados:** §4 (registro de configuraciones), §8 (modificación controlada de parámetros)

## Contexto

La configuración se lee de YAML y debe validarse. Pydantic en infraestructura más dataclasses
en el dominio duplicaría el modelo de configuración.

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| Pydantic en infraestructura + dataclasses en el dominio | Doble modelo que mantener sincronizado; una dependencia más |
| Pydantic en el dominio | Viola ADR-001 |
| **Dataclasses inmutables con invariantes en `__post_init__` + cargador YAML genérico** | Mensajes de error escritos a mano |

## Evidencia disponible

Analítica: las invariantes (≥ 2 capas ocultas, K1–K4, E1, E2, E5) son reglas del dominio y
deben cumplirse aunque no exista un validador externo.

## Criterio de selección

Un solo modelo de configuración y las invariantes donde pertenecen.

## Decisión

- Parámetros como `dataclasses` inmutables (`frozen=True`) en dominio y aplicación, con
  validación en `__post_init__`.
- `infrastructure/config_loader.py`: YAML → diccionarios → dataclasses, **rechazando claves
  desconocidas**; aplica sobrescrituras `--set`.
- Se elimina Pydantic de las dependencias.

## Consecuencias

La configuración resuelta se vuelca y se resume con un hash en cada ejecución.

## Verificación

F1: pruebas del cargador (claves desconocidas, tipos, invariantes, sobrescrituras).
