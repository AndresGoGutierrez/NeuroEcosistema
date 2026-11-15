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

Analítica: las invariantes (≥ 2 capas ocultas, K1–K4) son reglas del dominio y deben cumplirse
aunque no exista un validador externo.

E1, E2 y E5 (ADR-030) **no** son invariantes: son objetivos de calibración que P1 comprueba y
reporta (criterio A1 de ADR-020). Si se validaran en la construcción, las pruebas unitarias no
podrían usar mundos pequeños (por ejemplo, energía baja para provocar inanición rápida).
Aclaración aprobada por el autor al planificar F1 (2026-11-15).

## Criterio de selección

Un solo modelo de configuración y las invariantes donde pertenecen.

## Decisión

- Parámetros como `dataclasses` inmutables (`frozen=True`) en dominio y aplicación, con
  validación de las invariantes en `__post_init__`.
- E1, E2 y E5 se evalúan con una función de comprobación del dominio que devuelve el resultado de
  cada restricción, sin rechazar la configuración.
- `infrastructure/config_loader.py`: YAML → diccionarios → dataclasses, **rechazando claves
  desconocidas**; aplica sobrescrituras `--set`.
- Se elimina Pydantic de las dependencias.

## Consecuencias

La configuración resuelta se vuelca y se resume con un hash en cada ejecución.

## Verificación

F1: pruebas del cargador (claves desconocidas, tipos, invariantes, sobrescrituras) y de la
función de comprobación de E1, E2 y E5.
