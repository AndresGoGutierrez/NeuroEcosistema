# ADR-031: Integración del visor y registro de la sesión

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Eje de la bitácora:** Ingeniería y reproducibilidad
- **Requisitos relacionados:** §4 (ejecución observable, estadísticas y consulta de decisiones o
  variables de los agentes), §7.6 y §8 (demostración en vivo y modificación controlada de un
  parámetro)

## Contexto

F2 debe mostrar la simulación en tiempo real con un HUD y un inspector de agentes, y permitir
cambiar parámetros al lanzar (`--set`) dejando constancia (ADR-021, ADR-024). Los criterios de
cierre exigen que el visor no altere la simulación (el hash con visor es igual al hash sin
visor), que el inspector coincida con la traza del paso y que la sobrescritura quede registrada.
El simulador de F1 está cerrado y su comportamiento no debe cambiar.

## Alternativas consideradas

| Alternativa | Ventajas | Inconvenientes |
|---|---|---|
| **Observador síncrono sobre `on_step` de `simulate_episode`** | No modifica el simulador; el visor queda fuera del camino de los datos; pausar es bloquear dentro del callback | El estado inicial S₀ no pasa por `on_step` |
| Sesión paso a paso propia con `step_world` | Control directo del avance | Duplica el bucle del episodio (fases 1–9 y terminación) con riesgo de divergencia |
| Reproducir un archivo con la trayectoria grabada | Desacopla por completo | Exige formato y almacenamiento de trayectorias: alcance nuevo |

## Evidencia disponible

Analítica. `simulate_episode` ya acepta `on_step(trace)`, y el dominio no lee el reloj ni
recibe nada del observador; un observador que no escribe en el estado ni usa los generadores
del episodio no puede cambiar la trayectoria. Empírica, en F2: prueba de igualdad de hashes por
paso con el visor real (driver `dummy` de SDL), en A, B y C, con políticas por reglas y
aleatoria, incluyendo pausas, avances y selecciones.

## Criterio de selección

Garantía de no interferencia por construcción y sin cambios en F1, con la menor cantidad de
código nuevo.

## Decisión

**Integración (V1).**

- `application/session.py` convierte cada `StepTrace` en un fotograma inmutable: copias de solo
  lectura del estado tras el paso (S_t+1) y de las observaciones (de S_t) y acciones del paso t,
  más las estadísticas del HUD. El visor solo recibe fotogramas, nunca el estado vivo.
- `presentation/viewer.py` (pygame) es el observador: dibuja, procesa eventos y, en pausa,
  ejecuta su bucle dentro del callback, de modo que la simulación espera sin cambiar.
- El visor no recibe ni usa generadores aleatorios. pygame solo se usa en `presentation`
  (contrato de import-linter, V8) y se importa de forma diferida en el comando `view`, de modo
  que `run` y `pilot` no lo cargan.
- **S₀ (V7):** se reconstruye con `initialize_world` sobre flujos nuevos derivados de la misma
  identidad de semillas; los generadores del episodio no se tocan.
- **Cierre anticipado:** el observador lanza una excepción propia; la CLI la captura, completa
  el registro y cierra pygame.

**Inspector (V4).** Especie e índice; vivo, o causa y paso de muerte; energía (valor y fracción
de E_max); posición y rumbo tras el paso; entradas con nombre del esquema (ADR-007) observadas
en S_t; salida bruta de la política; giro y velocidad decodificados con `decode_actions`; si la
acción se aplicó (el agente estaba vivo al empezar el paso). Las activaciones de la red se
añaden en F5 sin modificar estos campos.

**HUD (V5).** Paso / t_max; escenario y políticas; presas vivas, capturadas y muertas de hambre;
depredadores vivos; plantas activas; energía media de los vivos por especie; capturas y
alimentaciones acumuladas; hash de configuración abreviado; pausa o velocidad.

**Controles (V6).** Espacio: pausa y reanudación. Flecha derecha: avance de un paso en pausa.
`+` y `−`: velocidad (pasos por fotograma). Clic: seleccionar agente. Esc o cerrar la ventana:
salir. No se cambian parámetros durante la sesión; se relanza con `--set`.

**Registro de la sesión (V2, V3).** Cada `neuroeco view` escribe
`runs/view/<AAAAMMDDTHHMMSSZ>-<id>/session.json` (fuera de git; `<id>` aleatorio de 8 caracteres
hexadecimales y directorio creado en exclusiva, sin sobrescribir otro). Se escribe **antes** de
empezar el episodio con estado `running` y se reemplaza de forma atómica al terminar con
`completed`, `closed` o `error`. Contiene las sobrescrituras literales, el hash de la
configuración, la configuración del mundo resuelta, la identidad de semillas, las políticas, la
procedencia (capturada antes de escribir nada) y, al final, los pasos ejecutados y las métricas.
`run` no cambia.

**Capturas (V9).** Las capturas de comprobación no se versionan.

## Consecuencias

- F1 no cambia: ni el dominio, ni `application/evaluation`, ni las métricas.
- Las copias por fotograma cuestan unos microsegundos por paso; irrelevante a la velocidad de
  un visor.
- El visor muestra datos del paso t (decisión) junto al estado S_t+1; el panel lo indica de
  forma explícita.
- El registro no sustituye al manifest de las ejecuciones formales (`RunStore`, F6).

## Verificación

F2: pruebas de no interferencia (hash por paso con visor = sin visor; dibujar, pausar, avanzar y
seleccionar no cambian la trayectoria; política aleatoria intacta; `view` y `run` dan los mismos
hashes y métricas), inspector = traza, contenido del registro y cierre anticipado; contrato de
import-linter que limita pygame a `presentation`.
