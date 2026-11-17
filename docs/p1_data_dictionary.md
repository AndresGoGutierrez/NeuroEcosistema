# Diccionario de datos de P1

Archivos que escriben `neuroeco pilot p1` (F4, tareas T3, T3b y T3c) y
`neuroeco pilot p1-criteria` (T4) en
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
| `<destino>.partial-<8 hex>/` | Bloque en curso. Solo queda si el proceso murió (corte de energía, proceso terminado) o si falló el renombrado final, en cuyo caso ya contiene `failure.json`; se recupera como indica la sección "Recuperación de un directorio parcial" |

Un destino solo existe cuando el bloque terminó completo: los archivos se preparan en
`<destino>.partial-<id>` y se publican con un único renombrado. Ningún destino se sobrescribe.
En Windows, si otro proceso (antivirus, indexador) retiene un instante el directorio, el
renombrado se reintenta como máximo 5 veces con esperas de 0.2, 0.4, 0.8 y 1.6 s; si sigue
fallando, el bloque se registra como fallo de infraestructura.

Todos los directorios viven dentro del repositorio (`--output-root` debe estar en él, y con los
grupos reales debe ser `results/pilots/p1`), ninguno puede estar ignorado por git y se versionan:
el comando exige un árbol de git limpio, así que el resultado o el registro de fallo de una
ejecución se confirma (commit) antes de la siguiente.

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
`p1_spec`, `registered_iterations` y `registered_rounds` (ruta y SHA-256), `config_files`,
`input_files`, `prerequisites`, `previous_attempts`, `git_checks`, `uv_lock_sha256`,
`dependencies`, `state_k` (A1, margen de B7 y comprobaciones E1, E2 y E5 por escenario),
`configurations` (escenario, overrides, `config_hash`, mundo y reglas de cada configuración
resuelta), `finished_utc`, `duration_seconds`, `episodes_written`, `episodes_discarded`,
`result_files` y `a2_violation`.

| Campo | Contenido |
|---|---|
| `config_files` (T3c) | SHA-256 de `p1_spec`, `p0_spec`, `base`, `scenarios` y `baselines`. Deben ser idénticos en toda la cadena (ver "Orden de ejecución") |
| `input_files` (T3c) | Ruta y SHA-256 de cada archivo leído: configuración, especificaciones registradas y archivos de los resultados exigidos |
| `prerequisites` | Resultados completos exigidos antes de este bloque: directorio, modo, `values_iteration` y SHA-256 de su `provenance.json` |
| `previous_attempts` | Intentos anteriores en el mismo destino: directorio y `kind` (`failure`, `interrupted`, `unrecognized`, o `partial` para un directorio parcial sin recuperar), con fase, tipo de error, fecha y `a2_violation` (verdadero, falso o `null` si no se puede saber) |
| `sequence_gate` (T4c) | Verificación de la secuencia de P1-18 antes del bloque (D-T4c-5): `applied`; si se aplicó, `step` (el paso que se ejecuta), `verdict` (`allowed`, o `author_authorization_required` en una confirmación), `reason`, `notes`, `transitions` (cada transición verificada) y `d9_confirmed`; si no se aplicó, `reason` (especificación sintética) |
| `git_checks` | `root`; `outside_repository` y `untracked` (archivos leídos fuera del repositorio o sin versionar); `hidden_changes` (marcas assume-unchanged o skip-worktree); `content_overrides` (filtros `clean`/`process` configurados o referencias `refs/replace/`); `head_mismatches` (archivos versionados cuyo contenido difiere de HEAD); `package_inside`; `canonical_paths`; `output_root_inside`; `ignored_outputs`; `head`, `upstream`, `upstream_full_ref`, `remote`, `remote_url` (sin credenciales), `upstream_commit` y `synchronized` |
| `episodes_written` | Episodios publicados: solo con `status` = `completed`; `null` en un fallo |
| `episodes_discarded` | `null` mientras corre, 0 en un bloque completado y, en un fallo, los episodios ejecutados cuyas filas se descartaron |
| `result_files` (T3c) | SHA-256 de `episodes.csv` y `bootstrap_keys.csv`, registrados al publicar; `null` en un fallo |
| `a2_violation` (T3c) | `null` mientras corre, `false` en un bloque completado y, en un fallo, si fue una violación A2 |

En un bloque fallido, `finished_utc`, `duration_seconds`, `episodes_written` y `result_files`
valen `null`: nada se publicó.

## `failure.json`

`schema` (`neuroeco.p1-failure/1`), `timestamp_utc`, `phase` (`preflight`, `execution` o
`writing`), `destination`, `command`, `git` (`commit`, `dirty`, `upstream`, `upstream_commit` y
`remote_url` en el momento del fallo), `mode` (modo, bloque, etapa, iteración,
`values_iteration`, valores y `values_source` con su SHA-256), `previous_attempts` (como en la
procedencia), `error_type`, `message`, `notes` (identifican el episodio), `episodes_completed` y
`a2_violation` (invariante, paso —`null` para S₀—, detalle y episodio) o `null`. Código de
salida: 2 ante una violación A2 y 1 ante cualquier otro error. Como `git` y `mode` se registran
siempre, una candidata rechazada en el estado K (antes de capturar la procedencia) queda
documentada en su propio registro.

## Comprobaciones previas

Antes del primer episodio, y sin ninguna opción para saltarlas:

1. **Especificación de P1.** Si declara algún grupo real (10–32), la tabla completa debe ser la
   de ADR-033: calibración 30 episodios con 10/11/12, confirmación 50 con 20/21/22 y segunda
   confirmación 50 con 30/31/32 (P1-5, P1-13, D16). Así ningún bloque puede usar las semillas de
   otro. Las especificaciones sintéticas de las pruebas (grupos ≥ 1000) no están sujetas a esta
   tabla.
2. **Registro.** En `configs/pilots/p1/` solo se admiten `iterations/NNN.yaml` y
   `rounds/RR.yaml`; cualquier otro archivo o subdirectorio se rechaza. Después, la secuencia
   estática de T1 y, salvo en una especificación sintética, la **secuencia de P1-18 según los
   resultados** (T4c, D-T4c-5; ver "Puerta de la secuencia en `pilot p1`").
3. **Sin recalibración (T3c, Mn-6 y Mn-7).** Una iteración nueva se rechaza si ya existe
   `calibration/entry` o si existe cualquier resultado o intento de una confirmación.
4. **Intentos anteriores y orden de ejecución** (secciones siguientes).
5. **Estado K**, plan exacto del bloque (grupos, condiciones, `item` y overrides de cada tarea),
   autorización de las confirmaciones y destino inexistente.
6. **Git**, tras capturar la procedencia, en este orden:
   - árbol limpio (`git status`);
   - ningún filtro `clean`/`process` configurado ni referencia `refs/replace/` (con ellos, un
     contenido modificado podría parecer el de HEAD);
   - ningún archivo versionado con las marcas assume-unchanged o skip-worktree (`git status`
     no los mira);
   - **todo** archivo versionado (código, configuración, especificaciones y resultados) igual al
     objeto de HEAD, comparado con `git hash-object` (que aplica la conversión de fin de línea)
     contra el árbol real de HEAD (`--no-replace-objects`); un archivo ausente, un enlace
     simbólico o un submódulo cuentan como diferencia;
   - el paquete `neuroeco` que se ejecuta está dentro del repositorio;
   - todos los archivos leídos dentro del repositorio y versionados (`git ls-files`, no solo las
     rutas recibidas);
   - con los grupos reales, las rutas canónicas: `configs/pilots/p1.yaml`, `configs/` y
     `results/pilots/p1` del repositorio;
   - `--output-root` dentro del repositorio y ningún archivo de resultado ni de fallo ignorado
     por git (`git check-ignore`);
   - la rama remota de HEAD es una rama de seguimiento (`refs/remotes/…`) de un remoto con URL,
     y su commit es el de HEAD. No se hace `git fetch`: se usa la referencia local que deja el
     último push, de modo que la comprobación no depende de la red.

## Orden de ejecución

Un resultado previo cuenta solo si su directorio está publicado y su procedencia tiene:

- `status` = `completed`, y el modo, bloque e iteración esperados;
- `config_files` **idénticos** a los actuales (T3c, IA-3): ningún parámetro ajeno a los ocho
  valores candidatos puede cambiar a lo largo de la cadena;
- el SHA-256 de su especificación (`values_source.sha256`) igual al del archivo registrado
  actual;
- `episodes_written` = `episodes_planned`;
- `episodes.csv` y `bootstrap_keys.csv` con el SHA-256 registrado al publicar (T3c, Mn-4), las
  columnas de este diccionario, tantas filas como episodios escritos y, fila a fila, la
  identidad planificada (bloque, etapa, iteración, escenario, condición, grupo e `item`).

Esta comprobación no mira el valor de ningún criterio; lo hace la puerta de la secuencia (T4c),
que con los grupos reales se ejecuta antes.

| Modo | Exige |
|---|---|
| `--iteration N` | Las iteraciones 1 … N−1 completas; ninguna evaluación de entrada ni confirmación iniciada |
| `--entry-evaluation` | Todas las iteraciones hasta la última (de etapa C) completas |
| `--confirmation` | Lo anterior y `calibration/entry` completa con los mismos valores |
| `--second-confirmation` | Las iteraciones completas y `confirmation/evaluation` completa con valores de una iteración **anterior** a la de `--values-from` (P1-21, decisión Mn-7). Como hoy no hay ningún flujo de recalibración aprobado, ninguna iteración posterior a la confirmación puede ejecutarse: la segunda confirmación es inalcanzable mientras no se apruebe ese flujo |

## Intentos anteriores y repeticiones (D18)

- Un intento fallido nunca impide repetir una iteración o una evaluación de entrada; queda en
  `previous_attempts`.
- **Confirmaciones.** Se repiten con las mismas semillas solo tras un fallo de infraestructura.
  Se rechaza la ejecución si algún intento anterior en el mismo destino fue una violación A2 o
  no tiene un registro reconocible (no se puede descartar A2).
- **Segunda confirmación.** Se rechaza si algún intento de la primera confirmación fue una
  violación A2, no tiene un registro reconocible o es un directorio parcial sin recuperar: una
  violación A2 no justifica una segunda confirmación.
- **Cómo se registra un fallo (T3c, IA-2).** El aviso se imprime primero en la consola. Si el
  bloque ya tenía directorio parcial, `failure.json` y la procedencia fallida (con
  `a2_violation`) se escriben **dentro de él antes de renombrarlo**; después se borran los CSV y
  se renombra a `.failed-…`. Si el renombrado falla (un bloqueo de Windows que dura más que los
  reintentos), el directorio parcial conserva la evidencia.
- **Clasificación de un intento.** `failure` si tiene un `failure.json` válido; su violación A2
  cuenta también si solo la declara la procedencia. `interrupted` solo si no hay
  `failure.json`, la procedencia sigue en `running` y no declara A2. Cualquier otro caso es
  `unrecognized`.

## Recuperación de un directorio parcial

Un `<destino>.partial-<id>/` sin publicar aparece si el proceso murió (corte de energía, proceso
terminado) o si falló el renombrado final. El comando rechaza ejecutar ese destino mientras
exista. Procedimiento (D18):

1. Borrar los CSV y los archivos `*.tmp` que contenga, sin usarlos. No tocar `failure.json` ni
   `provenance.json`.
2. Renombrarlo a `<destino>.failed-<AAAAMMDDTHHMMSSZ>-<id>/` (fecha UTC de la recuperación). No
   escribir un `failure.json` a mano.
3. Confirmarlo (commit y push) con un mensaje que documente la interrupción, y volver a ejecutar.

Si el directorio contiene `failure.json` (por ejemplo, el renombrado falló tras una violación
A2), el intento conserva esa clasificación: una violación A2 nunca se convierte en una
interrupción y la confirmación no se repite. Sin `failure.json`, con la procedencia en `running`,
el intento se clasifica `interrupted` (fallo de infraestructura).

**Riesgo residual.** Si el proceso muere exactamente entre detectar una violación A2 y escribir
`failure.json`, o si el disco no admite ni ese archivo, no queda registro y el intento parecería
interrumpido. El aviso ya se habrá impreso en la consola; ante cualquier duda, el autor debe
revisar esa salida antes de recuperar el directorio.

## Acreditación de A2

`episodes.csv` no tiene una columna de A2. El comprobador de P1-22 observa cada paso de cada
episodio y una violación detiene el bloque sin publicar nada. Por eso A2 se acredita para un
bloque cuando su `provenance.json` tiene `status` = `completed`, `a2_violation` = `false` y
`episodes_written` = `episodes_planned` = número de filas de `episodes.csv`, con los SHA-256 de
`result_files`. Cualquier violación queda en un `failure.json` con `a2_violation` distinto de
`null` y en la procedencia fallida con `a2_violation` = `true`.

## Rondas de ajuste de las reglas: `pilot p1 --round RR.yaml --phase …` (T4c)

Una ronda registrada (`configs/pilots/p1/rounds/RR.yaml`, P1-19) se ejecuta en fases, cada una
con todas las protecciones de los demás modos (D-T4c-3):

| Fase | Directorio | Episodios | Archivos |
|---|---|---|---|
| `prey` | `calibration/round_RR/prey_grid/` | `rules` en A × 12 combinaciones `p_flee` × `u_cruise` de la presa | `episodes.csv`, `selection.json`, `provenance.json` |
| `predator` | `calibration/round_RR/predator_grid/` | `rules` en A × 3 valores de `u_cruise` del depredador, con la presa ganadora | `episodes.csv`, `selection.json`, `provenance.json` |
| `reevaluation` | `calibration/round_RR/reevaluation/` | A_rev: las 12 condiciones de A con los ganadores; solo si la ronda cambió algún valor | `episodes.csv`, `provenance.json` |

- **Filas:** mismas columnas de `episodes.csv`; `stage` = `round_prey`, `round_predator` o
  `A_rev` (valores añadidos, D-T4c-6) e `iteration` = la iteración A tras la que va la ronda.
  En una rejilla, cada fila lleva los valores de su combinación; todas las combinaciones usan
  las mismas claves (grupo de calibración de A, `item` 0…n−1, P1-13).
- **Sin claves del bootstrap:** las rejillas no calculan intervalos y P1-20 no define clave
  para A_rev (D-T4c-1). En los criterios de A_rev, B2 conserva su veredicto (suma pareada) y su
  BCa figura como no calculado; A_rev se evalúa con S_A (P1-18).
- **`selection.json`** (`neuroeco.p1-selection/1`): `phase`, `parameters`, `winner`,
  `objective`, `rule` (`unique`, `current`, `lowest u_cruise`, `lowest p_flee`), `tied` y
  `totals` de todas las combinaciones (P1-4, P1-17). Se calcula con `select_prey` o
  `select_predator` sobre las filas publicadas.
- **Procedencia:** el mismo esquema con los campos añadidos `round` y `phase`; `values` son los
  valores con los que se ejecutó la fase (los vigentes en la rejilla de la presa, con la presa
  ganadora en la del depredador y con los dos ganadores en A_rev).
- **Encadenamiento:** una fase exige la iteración de anclaje y las anteriores, todas las
  fases de las rondas anteriores (A_rev solo si la ronda cambió algo) y las fases previas de su
  ronda. Los ganadores se recalculan siempre desde las filas publicadas y `selection.json` debe
  coincidir byte a byte (D-T4c-2). A_rev se rechaza si la ronda no cambió ningún valor.
- **Determinismo (D-T4c-4):** en la rejilla de la presa, las filas de la combinación vigente
  deben ser idénticas (salvo `block`, `stage` e `iteration`) a las filas `rules` de A de la
  evaluación anterior: la iteración de anclaje o el A_rev de la ronda anterior sobre la misma
  iteración. Cualquier diferencia detiene la ronda y queda un registro de fallo.

## Criterios de un bloque: `neuroeco pilot p1-criteria` (T4, D1)

`neuroeco pilot p1-criteria --result <directorio>` evalúa un bloque publicado con
`neuroeco.analysis.calibration` y escribe, dentro del mismo directorio, `criteria.csv` y
`criteria_provenance.json`. El flujo de cada bloque es: `pilot p1` → `pilot p1-criteria` → un
único commit con los resultados, los criterios y su procedencia (P1-19).

**Comprobaciones (si alguna falla, no se escribe nada y el código de salida es 1):**

1. Las mismas comprobaciones de git que `pilot p1`: sin marcas assume-unchanged o
   skip-worktree, sin filtros `clean`/`process` ni `refs/replace/`, todo archivo versionado
   igual a HEAD, el paquete `neuroeco` dentro del repositorio, rama remota bajo
   `refs/remotes/` con URL y HEAD sincronizado con ella, y los archivos de criterios no
   ignorados. La única diferencia: se admiten sin versionar **solo** los archivos del bloque
   evaluado (`provenance.json`, `episodes.csv`, `bootstrap_keys.csv` y los dos de criterios),
   para que resultados y criterios entren en un mismo commit; cualquier otro archivo sin
   versionar se rechaza, porque el código de evaluación debe ser el publicado.
2. El bloque: `status` = `completed`, `a2_violation` = `false`, SHA-256 de los dos CSV iguales
   a `result_files`, cada episodio planificado exactamente una vez, claves de P1-13 y P1-20,
   valores candidatos y configuraciones iguales a la procedencia, y recuentos coherentes
   (D14). Un bloque fallido, parcial, alterado o con una violación A2 nunca se evalúa (P1-22).
3. Sin sobrescritura: si ya existen los dos archivos, la ejecución solo se acepta cuando el
   nuevo `criteria.csv` es idéntico byte a byte al existente y la procedencia existente
   corresponde a él y a los mismos archivos de entrada; entonces no se reescribe nada. Si
   difieren, o solo existe uno de los dos, se rechaza.

### `criteria.csv`: una fila por criterio o parte de criterio

Mismo formato común que los demás CSV. Orden de las filas: A1, A2, B7; los criterios de cada
escenario ejecutado (A, B, C); los de A (A4 a, b1, b2 y C4); los de B frente a A (A4 c, B4); los
de C frente a A (A4 d, B5); y A6. Con los mismos archivos de entrada y el mismo `uv.lock`, el
archivo es idéntico en cada ejecución.

| Columna | Significado |
|---|---|
| `criterion` | `A1` … `A6`, `B1` … `B7`, `C1` … `C4` (P1-16) |
| `class` | `A`, `B` o `C` |
| `part` | Parte del criterio: `a`, `b1`, `b2`, `c`, `d` (A4); `prey` o `predator` (B2); `i` o `ii` (B4); la sonda (C1); `starvation_share` o `few_captures` (C4); vacío en los demás |
| `scenario` | `A`, `B` o `C`; `B-A` o `C-A` para una comparación entre escenarios; vacío para A1, A2 y B7 |
| `status` | `pass` o `fail` (clases A y B); `alert`, `no_alert` o `not_applicable` (clase C, con denominador nulo en C2 o C4) |
| `value` | Cantidades exactas calculadas (fracciones como `7/20`) |
| `rule` | Condición aplicada, con la referencia a P1-16 o a la decisión correspondiente |
| `bca_estimate`, `bca_lower`, `bca_upper` | Intervalo BCa de A6 (decide el criterio) y de B2 (solo descriptivo, P1-7); vacíos en los demás y los límites vacíos si no es estimable |
| `bca_estimable` | `true` o `false` (vacío sin intervalo) |
| `bca_confidence`, `bca_resamples` | 0.95 y 9999 (ADR-032) |

Reglas aplicadas: aritmética exacta con fracciones (D14); C4 cuenta solo muertes de presas
(D2); el BCa de B2 usa la supervivencia de la presa y la fracción capturada (D3); en A6, un BCa
no estimable con δ = −1 es el intervalo degenerado {−1} y se cumple (D1), y cualquier otro BCa
no estimable no se cumple. El generador de cada intervalo se reconstruye de su fila de
`bootstrap_keys.csv` exactamente como `SeedRegistry.generator`.

`pilot p1-criteria` no evalúa las rejillas de una ronda. Su ganador (P1-17) lo calculan las
funciones puras `select_prey` y `select_predator` sobre las filas de `rules` en A, y `pilot p1`
lo publica en `selection.json` de cada rejilla (T4c; ver "Rondas de ajuste de las reglas").

### `criteria_provenance.json`

`schema` (`neuroeco.p1-criteria-provenance/1`), `timestamp_utc`, `command`,
`result_directory` (relativo al repositorio), `block` (bloque, etapa e iteración),
`input_files` (SHA-256 de `provenance.json`, `episodes.csv` y `bootstrap_keys.csv`), `git`
(`head`, `upstream`, `upstream_commit` y `remote_url` sin credenciales), `python`, `platform`,
`dependencies` (numpy, scipy y pandas), `criteria_rows`, `criteria_sha256` y
`stage_requirements` (etapa y si se cumplen S_A, S_B, S_C o toda la clase A según la etapa,
P1-18).

## Verificación de la secuencia: `neuroeco pilot p1-sequence` (T4b, T4c)

`neuroeco pilot p1-sequence [--spec configs/pilots/p1.yaml] [--output-root results/pilots/p1]
[--d9-confirmed N ...]` es de solo lectura: no ejecuta episodios ni escribe archivos. El autor
lo ejecuta antes de autorizar cada iteración (D-T4b-1); desde T4c, `pilot p1` aplica la misma
verificación en sus comprobaciones previas (ver la sección siguiente).

1. Ordena los pasos: las iteraciones registradas, cada una seguida de sus rondas
   (`after_iteration`), y la evaluación de entrada si está publicada.
2. Para cada iteración con resultado publicado comprueba que pertenece a su especificación
   registrada (modo, etapa, iteración, valores y SHA-256 de `NNN.yaml` en `values_source`) y
   que su `criteria.csv` es exactamente la evaluación del código actual: se recalcula y se
   compara byte a byte, y `criteria_provenance.json` debe corresponder a los archivos. Sin
   `criteria.csv` el bloque no se puede usar.
3. El resultado de una ronda (T4c) sale de sus fases publicadas: cada rejilla se verifica como
   un prerrequisito de `pilot p1` y su ganador se recalcula desde sus filas (D-T4c-2); si la
   ronda cambió algún valor, el resultado de A_rev sale de su bloque y de sus criterios, como
   en una iteración.
4. Recorre las transiciones de P1-18 con el resultado de cada evaluación (S_A, S_B, S_C o la
   clase A completa en la entrada, y los criterios B incumplidos) y se detiene en la primera no
   permitida o en el primer paso sin resultado, que es el que va a ejecutarse. Un paso con
   resultados mientras otro anterior está incompleto se rechaza.

Después de una ronda (T4c): sin ningún valor cambiado, T_fin y la etapa B; con valores
cambiados, primero A_rev. Si A_rev cumple S_A, otra ronda mientras r < 3, y la etapa B con r = 3
(con una nota: el ajuste no convergió). Si A_rev no cumple S_A, la alternancia v aumenta y sigue
una iteración de A mientras v ≤ 3 e iA < 5; si no, STOP. El paso que sigue a una ronda debe
llevar exactamente los valores ganadores de las reglas, y una ronda tras otra conserva la misma
iteración de anclaje.

Veredictos: `allowed`, `rejected` (transición contraria a P1-18), `stop` (presupuesto agotado o
entrada fallida: consultar al autor), `author_confirmation_required` (cambio de `n_plants` por
la vía E5 de D9) y `author_authorization_required` (la entrada cumplió la clase A; la
confirmación necesita la autorización expresa, D11). El veredicto `not_verifiable_until_T4c` de
T4b (D-T4b-2) ya no existe: T4c verifica lo que sigue a una ronda. El código de salida es 0 solo
con `allowed`. Las notas del informe señalan las transiciones que requieren una decisión
documentada del autor (D-T4b-3); no son comprobaciones automáticas. `--d9-confirmed N` registra
que el autor confirmó la vía E5 para la iteración N, y esa confirmación debe constar en su
motivo (P1-19).

## Puerta de la secuencia en `pilot p1` (T4c, D-T4c-5)

Ninguna ejecución empieza si la secuencia no la permite. Tras la secuencia estática y antes de
cualquier otra comprobación de resultados, `pilot p1` construye los pasos exactamente como
`pilot p1-sequence` y exige que el bloque sea **el paso pendiente** y que su transición sea
`allowed`:

| Modo | Paso exigido |
|---|---|
| `--iteration N` | La iteración N es el primer paso sin resultado y P1-18 la permite tras el anterior |
| `--round RR --phase …` | La ronda RR es el paso pendiente (sus tres fases, hasta tener A_rev cuando cambió algún valor) |
| `--entry-evaluation` | Todos los pasos registrados están completos y P1-18 permite la evaluación de entrada |
| `--confirmation` | Secuencia completa con la evaluación de entrada publicada y la clase A cumplida (`author_authorization_required`); la autorización sigue siendo `--author-authorized` |
| `--second-confirmation` | Siempre se rechaza: P1-18 no tiene ese estado mientras no se apruebe un flujo de recalibración (Mn-7) |

- **A qué especificaciones se aplica.** A toda especificación con algún grupo de semillas menor
  que 1000, incluidos los reales de P1-13 (10–32); solo están exentas las sintéticas de las
  pruebas, con **todos** sus grupos ≥ 1000 (D16), que conservan el comportamiento de T3–T3c.
  Como cada episodio toma su grupo de esas declaraciones y el plan se comprueba de forma
  independiente, ningún episodio con un grupo menor que 1000 puede ejecutarse sin la
  verificación. Con un grupo real, además, la tabla completa debe ser la aprobada (T3b-1).
- **Sin opción para saltarla.** No existe ninguna opción que la desactive. `--d9-confirmed N`
  (la misma confirmación de D-T4b-4 que en `pilot p1-sequence`, documentada en el motivo de la
  iteración) solo permite la vía E5 de D9 para la iteración N; no omite ninguna otra regla y
  debe repetirse en cada ejecución posterior mientras esa transición forme parte de la
  secuencia, porque la secuencia se verifica completa cada vez.
- **Rechazo.** Un resultado que no se puede usar (sin `criteria.csv`, criterios que no
  coinciden, resultado ajeno a su especificación) o un paso no permitido se rechazan en la fase
  `preflight`, antes de capturar la procedencia y de ejecutar ningún episodio, con
  `P1RefusalError` y un `failure.json` cuyo mensaje cita D-T4c-5.
- **Archivos leídos.** La procedencia, los CSV y los dos archivos de criterios de cada bloque
  usado, y las rejillas, se añaden a `input_files`, de modo que deben estar versionados e iguales
  a HEAD (P1-19).
- **Flujo de cada paso:** `pilot p1` → `pilot p1-criteria` → commit y push → siguiente paso.

## Historial del esquema

- **T3 (`b53f547`):** primera versión de `neuroeco.p1-provenance/1` y `neuroeco.p1-failure/1`.
- **T3b:** campos añadidos, sin cambiar ni quitar ninguno: en la procedencia
  `values_iteration`, `prerequisites`, `previous_attempts`, `git_checks` y
  `episodes_discarded`; en `failure.json` `git`, `mode` y `previous_attempts`. En un fallo,
  `episodes_written`, `finished_utc` y `duration_seconds` pasan a `null`. Los identificadores de
  esquema se mantienen (decisión T3b-2): los cambios son aditivos y no existía ningún archivo
  real con estos esquemas.
- **T3c:** campos añadidos en la procedencia: `config_files`, `input_files`, `result_files` y
  `a2_violation`, y en `git_checks` `content_overrides`, `hidden_changes`, `head_mismatches`,
  `package_inside`, `canonical_paths`, `ignored_outputs`, `upstream_full_ref`, `remote` y
  `remote_url`; en `failure.json`, `git.remote_url`. Son aditivos y se mantienen los
  identificadores `/1`. Un resultado anterior a T3c (sin `config_files` ni `result_files`) no
  sirve como prerrequisito; no existe ninguno real.
- **T4:** primera versión de `criteria.csv` y `neuroeco.p1-criteria-provenance/1`.
- **T4c:** valores añadidos de `stage` (`round_prey`, `round_predator`, `A_rev`), campos
  añadidos `round` y `phase` en la procedencia y en `failure.json` de las fases de una ronda, y
  primera versión de `selection.json` (`neuroeco.p1-selection/1`). Se mantienen los
  identificadores `/1` (D-T4c-6): los lectores existentes rechazan con un mensaje claro las
  etapas que no evalúan (por ejemplo, `pilot p1-criteria` sobre una rejilla). En C3 se añade
  `sequence_gate` a la procedencia (D-T4c-5), también aditivo.
- **Política (Mn-8):** cualquier cambio futuro incompatible (quitar o renombrar un campo, o
  cambiar su tipo o su significado) incrementará la versión del esquema (`/2`). Los lectores
  (T4) deben validar los campos que usan y no solo el identificador.
