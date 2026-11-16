# Diccionario de datos de P1

Archivos que escribe `neuroeco pilot p1` (F4, tareas T3 y T3b) en
`results/pilots/p1/<bloque>/<iteration_NNN | entry | evaluation>/`. Las decisiones de origen
están en [ADR-033](decisions/ADR-033-p1-operational-definitions.md) (P1-13, P1-16, P1-19, P1-20 y
P1-22) y el formato en [ADR-023](decisions/ADR-023-csv-results.md). La definición de las columnas
vive en el código (`neuroeco.application.calibration`, `EPISODE_COLUMN_TYPES` y
`BOOTSTRAP_COLUMNS`); este documento la explica y una prueba fija su orden.

## Directorios

| Ruta | Contenido |
|---|---|
| `calibration/iteration_NNN/` | Una iteración de calibración (`--iteration`); NNN es el número de la iteración |
| `calibration/entry/` | Evaluación de entrada (`--entry-evaluation`, estado E) |
| `confirmation/evaluation/` | Bloque de confirmación (`--confirmation --author-authorized`) |
| `second_confirmation/evaluation/` | Segunda confirmación, solo tras una recalibración autorizada |
| `<destino>.failed-<AAAAMMDDTHHMMSSZ>-<8 hex>/` | Registro de un intento fallido o rechazado: `failure.json` y, si ya se había capturado, `provenance.json`. Nunca contiene CSV ni es un resultado |
| `<destino>.partial-<8 hex>/` | Bloque en curso. Solo queda si el proceso murió sin poder registrar el fallo (corte de energía, proceso terminado); se recupera como indica la sección "Recuperación de un directorio parcial" |

Un destino solo existe cuando el bloque terminó completo: los archivos se preparan en
`<destino>.partial-<id>` y se publican con un único renombrado. Ningún destino se sobrescribe.
En Windows, si otro proceso (antivirus, indexador) retiene un instante el directorio, el
renombrado se reintenta como máximo 5 veces con esperas de 0.2, 0.4, 0.8 y 1.6 s; si sigue
fallando, el bloque se registra como fallo de infraestructura.

Todos los directorios viven dentro del repositorio (`--output-root` debe estar en él) y se
versionan: el comando exige un árbol de git limpio, así que el resultado o el registro de fallo
de una ejecución se confirma (commit) antes de la siguiente.

## Formato común

- CSV en UTF-8 con encabezado, separador `,` y fin de línea `\r\n` (módulo `csv` de Python).
- `int`: entero en base 10. `str`: texto. `float`: `repr` de Python, la representación más corta
  que reproduce exactamente el mismo número; nunca `nan` ni `inf` (D14).
- El orden de las filas es el de ejecución: escenario (A, B, C), condición (orden del catálogo de
  P1-14) e `item`.

## `episodes.csv`: una fila por episodio

| Columna | Tipo | Significado |
|---|---|---|
| `block` | str | `calibration`, `confirmation` o `second_confirmation` |
| `stage` | str | `A`, `B` o `C` (iteración), `entry` o `confirmation` |
| `iteration` | int | Número de la iteración; 0 en la evaluación de entrada y en las confirmaciones |
| `scenario` | str | `A`, `B` o `C` |
| `condition` | str | Condición de P1-14: `rules`, `random_prey`, `random_predator`, `prey_probe_<SONDA>`, `predator_probe_<SONDA>` o `no_predators` |
| `purpose` | int | Campo de la clave (P1-13): 1 = PILOT |
| `seed_group` | int | Grupo de semillas del escenario en el bloque |
| `run` | int | Campo de la clave: 0 |
| `generation` | int | Campo de la clave: 0 |
| `item` | int | Índice del episodio dentro de la condición |
| `stream_env_init` | int | 3 (ENV_INIT) |
| `stream_env_dynamics` | int | 4 (ENV_DYNAMICS) |
| `stream_policy_prey` | int | 5 (POLICY_PREY) |
| `stream_policy_predator` | int | 6 (POLICY_PREDATOR) |
| `config_hash` | str | SHA-256 de la configuración resuelta del episodio (ADR-022) |
| `plant_energy` | float | Valor candidato: energía de una planta |
| `regrow_delay` | int | Valor candidato: pasos hasta la reaparición de una planta |
| `n_plants_a` | int | Valor candidato: plantas de A (y de C) |
| `n_plants_b` | int | Valor candidato: plantas de B |
| `n_predators_c` | int | Valor candidato: depredadores de C |
| `prey_flee_threshold` | float | Valor candidato: `p_flee` |
| `prey_cruise_fraction` | float | Valor candidato: `u_cruise` de la presa |
| `predator_cruise_fraction` | float | Valor candidato: `u_cruise` del depredador |
| `t_max` | int | T_max resuelto |
| `n_prey` | int | Presas del episodio |
| `n_predators` | int | Depredadores del episodio (0 en `no_predators`) |
| `n_plants` | int | Plantas del episodio |
| `steps` | int | Pasos ejecutados (menos que `t_max` si murieron todas las presas) |
| `prey_survival_numerator` | int | Σ t_i de las presas (t_i = paso de muerte o T_max), ADR-014 |
| `prey_survival_denominator` | int | n_prey · T_max |
| `prey_alive_end` | int | Presas vivas al final |
| `prey_captured` | int | Presas capturadas (= capturas; numerador de la fracción capturada, denominador `n_prey`) |
| `prey_starved` | int | Presas muertas de inanición |
| `plants_eaten` | int | Plantas comidas |
| `exposure` | int | Σ pasos-presa vivos (denominador de la tasa por exposición) |
| `early_captures` | int | Capturas en pasos < 0.05 · T_max (C2) |
| `prey_net_energy_rate` | float | (energía ganada − gastada) / exposición, de las métricas de F1 (B4, E3) |
| `predators_alive_end` | int | Depredadores vivos al final |
| `predators_starved` | int | Depredadores muertos de inanición |
| `predators_reaching_half` | int | Depredadores con t_i ≥ 0.5 · T_max, con t_i = paso de muerte o `steps` si siguen vivos (B3, D2) |
| `predators_censored_before_half` | int | Vivos al final de un episodio terminado antes de T_max y antes de 0.5 · T_max |
| `predators_censored_after_half` | int | Vivos al final de un episodio terminado antes de T_max pero en o después de 0.5 · T_max |
| `predators_alive_at_t_max` | int | Vivos al final con `steps` = T_max (B6, D3) |
| `predators_alive_at_t_max_below_two_captures` | int | De los anteriores, los que tienen menos de 2 capturas |

Las cuatro claves de un episodio son (`purpose`, `seed_group`, `run`, `generation`, `item`,
`stream_<flujo>`) y cada flujo se reconstruye con
`numpy.random.default_rng(numpy.random.SeedSequence(project_seed, spawn_key=clave))`, con
`project_seed` tomado de `provenance.json` (P1-13).

## `bootstrap_keys.csv`: una fila por comparación (P1-20)

Solo aparecen las comparaciones cuyos escenarios se ejecutaron: etapa A, 3 y 6; etapa B, 1, 3,
4, 6 y 7; etapa C, 2, 3, 5, 6 y 8; evaluación de entrada y confirmaciones, de la 1 a la 8.

| Columna | Tipo | Significado |
|---|---|---|
| `comparison` | int | 1 = A6 δ(B, A); 2 = A6 δ(C, A); 3, 4, 5 = B2 de la presa en A, B, C; 6, 7, 8 = B2 del depredador en A, B, C |
| `comparison_name` | str | Nombre de la comparación (`A6_B_VS_A`, …) |
| `project_seed` | str | Semilla del proyecto (128 bits): se lee como texto y después se convierte a entero |
| `purpose` | int | 5 = ANALYSIS |
| `seed_group` | int | Grupo de A en el bloque (10, 20 o 30 en P1; reservados para P1) |
| `run` | int | Número de iteración; 0 en la evaluación de entrada y en las confirmaciones |
| `generation` | int | 0 |
| `item` | int | Número de la comparación |
| `stream` | int | 7 = BOOTSTRAP |

## `provenance.json`

Se captura antes de escribir nada (P1-19) y se completa al terminar. Campos principales:
`schema` (`neuroeco.p1-provenance/1`), `status` (`running`, `completed` o `failed`), los campos
de `collect_provenance` (`timestamp_utc`, `command`, `config_hash` de la primera configuración,
`git_commit`, `git_dirty`, `python`, `numpy`, `platform`, `machine`, `processor`, `cpu_count`,
`thread_env`), `mode`, `block`, `stage`, `iteration`, `values_iteration` (número de la iteración
que aporta los valores), `bootstrap_run`, `scenarios`, `episodes_per_condition`,
`episodes_planned`, `author_authorized`, `project_seed` (texto), `values`, `values_source`,
`p1_spec`, `registered_iterations` y `registered_rounds` (ruta y SHA-256), `prerequisites`,
`previous_attempts`, `git_checks`, `uv_lock_sha256`, `dependencies`, `state_k` (A1, margen de B7
y comprobaciones E1, E2 y E5 por escenario), `configurations` (escenario, overrides,
`config_hash`, mundo y reglas de cada configuración resuelta), `finished_utc`,
`duration_seconds`, `episodes_written` y `episodes_discarded`.

| Campo (T3b) | Contenido |
|---|---|
| `prerequisites` | Resultados completos exigidos antes de este bloque (ver "Orden de ejecución"): directorio, modo, `values_iteration` y SHA-256 de su `provenance.json` |
| `previous_attempts` | Intentos anteriores en el mismo destino: directorio y `kind` (`failure`, `interrupted`, `unrecognized`), con fase, tipo de error, fecha y `a2_violation` (verdadero, falso o `null` si no se puede saber) |
| `git_checks` | `root` del repositorio, `outside_repository` y `untracked` (archivos leídos fuera del repositorio o sin versionar; deben estar vacíos), `output_root_inside`, `head`, `upstream`, `upstream_commit` y `synchronized` |
| `episodes_written` | Episodios publicados: solo con `status` = `completed`; `null` en un fallo |
| `episodes_discarded` | `null` mientras corre, 0 en un bloque completado y, en un fallo, los episodios ejecutados cuyas filas se descartaron |

En un bloque fallido, `finished_utc`, `duration_seconds` y `episodes_written` valen `null`: nada
se publicó.

## `failure.json`

`schema` (`neuroeco.p1-failure/1`), `timestamp_utc`, `phase` (`preflight`, `execution` o
`writing`), `destination`, `command`, `git` (`commit`, `dirty`, `upstream` y `upstream_commit`
en el momento del fallo), `mode` (modo, bloque, etapa, iteración, `values_iteration`, valores y
`values_source` con su SHA-256), `previous_attempts` (como en la procedencia), `error_type`,
`message`, `notes` (identifican el episodio), `episodes_completed` y `a2_violation` (invariante,
paso —`null` para S₀—, detalle y episodio) o `null`. Código de salida: 2 ante una violación A2 y
1 ante cualquier otro error. Como `git` y `mode` se registran siempre, una candidata rechazada en
el estado K (antes de capturar la procedencia) queda documentada en su propio registro.

## Comprobaciones previas

Antes del primer episodio, y sin ninguna opción para saltarlas:

1. **Especificación de P1.** Si declara algún grupo real (10–32), la tabla completa debe ser la
   de ADR-033: calibración 30 episodios con 10/11/12, confirmación 50 con 20/21/22 y segunda
   confirmación 50 con 30/31/32 (P1-5, P1-13, D16). Así ningún bloque puede usar las semillas de
   otro. Las especificaciones sintéticas de las pruebas (grupos ≥ 1000) no están sujetas a esta
   tabla.
2. **Registro.** En `configs/pilots/p1/` solo se admiten `iterations/NNN.yaml` y
   `rounds/RR.yaml`; cualquier otro archivo o subdirectorio se rechaza. Después, la secuencia
   estática de T1.
3. **Intentos anteriores y orden de ejecución** (secciones siguientes).
4. **Estado K**, plan exacto del bloque (grupos, condiciones, `item` y overrides de cada tarea),
   autorización de las confirmaciones y destino inexistente.
5. **Git**, tras capturar la procedencia: árbol limpio; todos los archivos leídos (`p1.yaml`,
   `p0.yaml`, `base.yaml`, `scenarios.yaml`, `baselines.yaml`, las especificaciones registradas y
   los archivos de los resultados exigidos) dentro del repositorio y versionados, comprobado con
   `git ls-files` y no solo con las rutas recibidas; `--output-root` dentro del repositorio; y
   `HEAD` igual a su rama remota (`@{u}`), es decir, publicado. No se hace `git fetch`: se usa la
   referencia local que deja el último push, de modo que la comprobación no depende de la red.

## Orden de ejecución

Un resultado previo cuenta solo si su directorio está publicado, su procedencia tiene `status`
= `completed`, el modo, bloque e iteración esperados, `episodes_written` = `episodes_planned` =
filas de `episodes.csv` (con las columnas de este diccionario), existe `bootstrap_keys.csv` y el
SHA-256 de su especificación (`values_source.sha256`) coincide con el del archivo registrado
actual. No se mira el valor de ningún criterio (eso es T4b).

| Modo | Exige |
|---|---|
| `--iteration N` | Las iteraciones 1 … N−1 completas |
| `--entry-evaluation` | Todas las iteraciones hasta la última (de etapa C) completas |
| `--confirmation` | Lo anterior y `calibration/entry` completa con los mismos valores |
| `--second-confirmation` | Las iteraciones completas y `confirmation/evaluation` completa con valores de una iteración **anterior** a la de `--values-from` (P1-21: la segunda confirmación sigue a una recalibración; nunca repite ni sustituye a la primera) |

## Intentos anteriores y repeticiones (D18)

- Un intento fallido nunca impide repetir una iteración o una evaluación de entrada; queda en
  `previous_attempts`.
- **Confirmaciones.** Se repiten con las mismas semillas solo tras un fallo de infraestructura.
  Se rechaza la ejecución si algún intento anterior en el mismo destino fue una violación A2 o
  no tiene un registro reconocible (no se puede descartar A2).
- **Segunda confirmación.** Se rechaza si algún intento de la primera confirmación fue una
  violación A2 o no tiene un registro reconocible: una violación A2 no justifica una segunda
  confirmación.

## Recuperación de un directorio parcial

Un `<destino>.partial-<id>/` sin publicar solo aparece si el proceso murió sin registrar el fallo.
El comando rechaza ejecutar ese destino mientras exista. Procedimiento (fallo de infraestructura,
D18):

1. Borrar los CSV y los archivos `*.tmp` que contenga, sin usarlos.
2. Renombrarlo a `<destino>.failed-<AAAAMMDDTHHMMSSZ>-<id>/` (fecha UTC de la recuperación),
   conservando su `provenance.json` con `status` = `running`. No escribir un `failure.json` a mano.
3. Confirmarlo (commit y push) con un mensaje que documente la interrupción, y volver a ejecutar.

El comando reconoce ese directorio como intento `interrupted`: una violación A2 siempre deja un
`failure.json`, de modo que un intento interrumpido es, por construcción, un fallo de
infraestructura.

## Acreditación de A2

`episodes.csv` no tiene una columna de A2. El comprobador de P1-22 observa cada paso de cada
episodio y una violación detiene el bloque sin publicar nada. Por eso A2 se acredita para un
bloque cuando su `provenance.json` tiene `status` = `completed` y `episodes_written` =
`episodes_planned` = número de filas de `episodes.csv`; cualquier violación queda en un
`failure.json` con `a2_violation` distinto de `null`.

## Historial del esquema

- **T3 (`b53f547`):** primera versión de `neuroeco.p1-provenance/1` y `neuroeco.p1-failure/1`.
- **T3b:** campos añadidos, sin cambiar ni quitar ninguno: en la procedencia
  `values_iteration`, `prerequisites`, `previous_attempts`, `git_checks` y
  `episodes_discarded`; en `failure.json` `git`, `mode` y `previous_attempts`. En un fallo,
  `episodes_written`, `finished_utc` y `duration_seconds` pasan a `null`. Los identificadores de
  esquema se mantienen (decisión T3b-2): los cambios son aditivos y no existía ningún archivo
  real con estos esquemas.
