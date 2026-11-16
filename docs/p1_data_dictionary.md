# Diccionario de datos de P1

Archivos que escribe `neuroeco pilot p1` (F4, tarea T3) en
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

Un destino solo existe cuando el bloque terminó completo: los archivos se preparan en
`<destino>.partial-<id>` y se publican con un único renombrado. Ningún destino se sobrescribe.

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
`thread_env`), `mode`, `block`, `stage`, `iteration`, `bootstrap_run`, `scenarios`,
`episodes_per_condition`, `episodes_planned`, `author_authorized`, `project_seed` (texto),
`values`, `values_source`, `p1_spec`, `registered_iterations` y `registered_rounds` (ruta y
SHA-256), `uv_lock_sha256`, `dependencies`, `state_k` (A1, margen de B7 y comprobaciones E1, E2 y
E5 por escenario), `configurations` (escenario, overrides, `config_hash`, mundo y reglas de cada
configuración resuelta), `finished_utc`, `duration_seconds` y `episodes_written`. El comando
solo se ejecuta con `git_dirty` = `false`.

## `failure.json`

`schema` (`neuroeco.p1-failure/1`), `timestamp_utc`, `phase` (`preflight`, `execution` o
`writing`), `destination`, `command`, `error_type`, `message`, `notes` (identifican el episodio),
`episodes_completed` y `a2_violation` (invariante, paso —`null` para S₀—, detalle y episodio) o
`null`. Código de salida: 2 ante una violación A2 y 1 ante cualquier otro error.
