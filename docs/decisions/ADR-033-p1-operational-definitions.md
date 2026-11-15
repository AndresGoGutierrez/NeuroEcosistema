# ADR-033: Definiciones operativas de la calibración P1 (F4)

- **Estado:** Aceptada. P1-1 a P1-12 aprobadas por el autor en T0 de F4 (2026-11-15). P1-13 a
  P1-24 corregidas en T0b tras la auditoría metodológica y aprobadas por el autor (decisiones
  D1–D18). Ninguna se fijó después de ver datos: no se ha ejecutado ningún episodio de P1.
- **Fecha:** 2026-11-15
- **Eje de la bitácora:** Diseño experimental / Ingeniería y reproducibilidad
- **Requisitos relacionados:** §6 (tres escenarios con diferencias medibles; referencia por reglas
  y aleatoria; semillas registradas), §9 (reproducibilidad)

## Contexto

ADR-020 fija el procedimiento y las clases de criterios de P1, ADR-012 exige ajustar y congelar
`p_flee` y `u_cruise`, y ADR-029 y ADR-030 dejan los valores numéricos pendientes de P1. Esos
ADR no bastan para implementar P1 sin elegir criterios: varios no tienen definición operativa
(A4, B2, B3, B6, C4), no fijan el alcance por escenario ni el tamaño del bloque de calibración,
la derivación de semillas del bootstrap choca con el aislamiento de `analysis` y la expresión
"alternando como máximo 3 veces" admite varias lecturas. Si esas elecciones se hicieran durante
la calibración, se fijarían reglas después de ver datos. Este ADR las fija **antes** de generar
ningún dato. No modifica ADR-010, ADR-012, ADR-014, ADR-020, ADR-028, ADR-029, ADR-030, ADR-031
ni ADR-032, ni el código de F1–F3.

## Alternativas consideradas

| Tema | Alternativas | Elegida |
|---|---|---|
| Semillas del bootstrap (A6, B2) | Importar `SeedRegistry` en `analysis` (rompe el contrato de capas) / semillas ad hoc en `analysis` / clave calculada en la aplicación y registrada en CSV | Clave registrada en CSV; `analysis` reconstruye el `SeedSequence` con NumPy |
| Prueba de F1 que fija los valores provisionales | Borrarla / mantenerla y no calibrar / sustituirla en el congelamiento | Sustituirla por una que fije los valores congelados |
| Bloque de calibración | Mismo bloque que la confirmación / bloque nuevo en cada iteración / bloque fijo e independiente | Bloque fijo de 30 episodios por escenario, independiente de la confirmación |
| Objetivo del ajuste de las reglas | Sin rejilla / rejilla con objetivo común / rejilla con la métrica primaria de cada especie | Métrica primaria de cada especie, en A, frente a la otra especie por reglas |
| Empates en la rejilla | Elección libre / tolerancia numérica / orden fijo previo | Comparación exacta con enteros y orden de preferencia fijado en este ADR |
| A6 con separación completa (BCa no estimable) | Incumple / prueba exacta alternativa / intervalo degenerado | Intervalo degenerado {−1} (D1) |
| Supervivencia del depredador (B3) | Métrica de F1 `predator_survival` (cuenta como supervivientes a los vivos en un final anticipado) / supervivencia individual con censura explícita | Supervivencia individual con censura explícita (D2) |
| "Alternando como máximo 3 veces" | L1: etapa A ↔ ajuste de reglas / L2: presa ↔ depredador / L3: A ↔ B ↔ C (choca con "solo se ajusta el factor del escenario") | L1, con un máximo de 3 rondas de ajuste (D7) |
| Registro de los valores congelados | Editar ADR-012, ADR-029 y ADR-030 / ADR nuevo | ADR nuevo, sin modificar los anteriores |

## Evidencia disponible

- **Analítica, emparejamiento.** Con las mismas claves dentro de cada escenario, las comparaciones
  reglas − aleatoria y reglas − sonda usan los mismos entornos (DET-5, ADR-028). S₀ se sortea en
  el orden presas, plantas, depredadores (`initialize_world`), de modo que la condición sin
  depredadores conserva las presas y las plantas del mismo episodio. Con `seed_group` distintos
  por escenario, las comparaciones entre escenarios son entre muestras independientes, como exige
  el δ de Cliff sin emparejar de A6.
- **Analítica, valores provisionales (decisión A5 de F1).** K1–K4, E1, E2 y E5 se cumplen; el
  margen de K5 es 20 − (2.5 + 2.3·⌈π/0.5⌉) = 1.4 > 0; E₀,pred + e_prey = 80 + 40 = 120 <
  c_basal·T_max = 160, de modo que un depredador con menos de dos capturas no puede llegar a
  T_max con ninguna política (condición suficiente de E4).
- **Analítica, sonda STILL (A4 b).** STILL tiene velocidad 0 y gasta c_basal = 0.16 por paso con
  E₀ = 80. Para llegar viva a T_max, una presa necesita ganar más de 80 (al menos 3 plantas con
  e_plant = 30; al menos 2 con el máximo de E5) y solo come si aparece una planta a menos de
  r_eat (≈ 1.25 % de las presas al inicio). Un depredador necesita más de 80: tres capturas en la
  práctica (dos dan exactamente 80, el límite de la inanición). En `predator_probe_STILL` ningún
  depredador persigue y la presa por reglas huye a una distancia (1 − p_flee)·R_v ∈ [10, 16] con
  radio de giro 2, de modo que las capturas son prácticamente imposibles. Una supervivencia
  STILL indicaría una anomalía real.
- **Analítica, final del episodio.** El episodio termina cuando no quedan presas vivas (ADR-008,
  fase 9). La métrica de F1 `predator_survival` asigna T_max a los depredadores vivos en ese
  momento, aunque no hayan llegado a T_max: por eso B3 y B6 usan definiciones propias.
- **Empírica (F3, informativa):** el IC BCa del δ de Cliff cubrió 0.956 con 50 × 50; el de la
  media pareada cubrió 0.942 y 0.933 con n = 50. Por eso el BCa de B2 es solo descriptivo.
- **Empírica (auditoría de T0, datos sintéticos, no de P1):** con separación completa (δ̂ = −1)
  `cliffs_delta_bca` devuelve "no estimable"; con un solo solapamiento devuelve un IC finito.
- Pendiente: todos los resultados de P1 (F4).

## Criterio de selección

Que cada criterio de ADR-020 sea computable de forma reproducible desde los CSV, que ninguna
regla dependa de resultados observados y que no se cambie ningún ADR aprobado.

## Decisión

### Decisiones aprobadas en T0 (P1-1 a P1-12)

**P1-1. Semillas del bootstrap.** El comando de aplicación calcula la clave de cada IC bootstrap
con el esquema de ADR-028 (propósito ANALYSIS, flujo BOOTSTRAP) y la registra en un CSV junto a
los resultados. `analysis` reconstruye `numpy.random.SeedSequence(project_seed, spawn_key=clave)`
y el generador `numpy.random.default_rng(...)` sin importar `application` (concreción en P1-20).

**P1-2. Prueba de valores provisionales.** Se modifica exclusivamente
`test_base_configuration_matches_the_approved_provisional_values`
(`tests/unit/infrastructure/test_config_loader.py`) en el congelamiento, para que fije los valores
congelados en lugar de los provisionales. No cambia el comportamiento del dominio ni debilita las
garantías de F1: la prueba sigue comprobando la semilla del proyecto, los valores exactos de la
configuración y K1–K4, E1, E2 y E5. Las demás pruebas de F1 que usan los valores provisionales
como datos sintéticos (`tests/support.py`) no cambian, porque prueban reglas y no la
configuración. La modificación se justifica en el commit y en el ADR de congelamiento. Cualquier
otra prueba cerrada que falle se rige por P1-23.

**P1-3. Definición operativa de A4.** En el escenario A con políticas por reglas hay alimentación
y capturas; la sonda STILL muere de inanición (presa y depredador, como criterios separados); B
presenta más muertes por inanición que A, y C más capturas que A (precisión en P1-16).

**P1-4. Ajuste de las políticas por reglas.** Rejillas `p_flee` ∈ {0.2, 0.3, 0.4, 0.5} y
`u_cruise` ∈ {0.3, 0.5, 0.7}. Cada especie maximiza su métrica primaria frente a la otra especie
por reglas en el escenario A. Se registran los resultados de todas las combinaciones. La mejor
combinación es la mejor **de la rejilla en este bloque**, no un óptimo global, y así se reporta.
Procedimiento y empates en P1-17.

**P1-5. Bloques.** Calibración: 30 episodios por escenario, con las mismas semillas en todas las
iteraciones. Confirmación: 50 semillas nuevas, independientes de la calibración, con un
`seed_group` por escenario (ADR-020). Valores en P1-13.

**P1-6. Parámetros ajustables en la etapa A.** Primero `plant_energy` y `regrow_delay`; después
`n_plants` (condición en P1-18). No se cambian la geometría (`size`, radios) ni los parámetros de
las especies sin consultar al autor. Tampoco `t_max`, `n_prey`, `prey_energy` (e_prey) ni
`n_predators` de A.

**P1-7. B2.** Se cumple cuando la diferencia media pareada reglas − aleatoria es estrictamente
mayor que 0. El IC BCa de esa diferencia es descriptivo.

**P1-8. Lotes sin depredadores.** Para B4 (E3) se ejecutan lotes adicionales con
`n_predators = 0` en A y en B.

**P1-9. C4.** "Casi sin capturas" significa menos de una captura media por episodio.

**P1-10. Ubicación del código.** `application/calibration.py` (comprobador de invariantes A2 y
ejecución por bloques) y `analysis/calibration.py` (evaluación de los criterios desde los CSV).

**P1-11. Valores congelados.** Se registran en un ADR nuevo (previsiblemente ADR-034), sin
modificar ADR-010, ADR-012, ADR-029 ni ADR-030.

**P1-12. Etiqueta.** `env-frozen-v1` solo se crea y se publica al final, tras verificar los
resultados y con autorización expresa del autor.

### Decisiones aprobadas en T0b (P1-13 a P1-24)

**P1-13. Semillas de los episodios.** Propósito PILOT; `run = 0`, `generation = 0`, `item` = índice
del episodio (0…29 en calibración, 0…49 en confirmación). `seed_group` declarados en la
especificación de P1 y comprobados por el cargador junto con los existentes (0 exploratorio,
1 P0):

| Bloque | A | B | C |
|---|---|---|---|
| Calibración | 10 | 11 | 12 |
| Confirmación | 20 | 21 | 22 |
| Segunda confirmación (solo tras una recalibración documentada y autorizada, ADR-020) | 30 | 31 | 32 |

- Dentro de un escenario, todas las condiciones (P1-14), todas las combinaciones de la rejilla y
  todas las iteraciones usan las mismas claves: las comparaciones dentro del escenario son
  pareadas y las comparaciones entre escenarios son independientes. Ningún episodio se descarta
  ni se sustituye.
- Cada episodio usa cuatro flujos, cada uno con su propia clave de seis enteros
  `(purpose, seed_group, run, generation, item, stream)` (ADR-028). `SeedRegistry.episode_streams`
  deriva siempre los cuatro, que comparten los cinco primeros campos y difieren solo en `stream`.
  Cada fila del CSV de episodios los registra en nueve columnas enteras:
  - cinco columnas con los campos comunes: `purpose` (1, PILOT), `seed_group`, `run`,
    `generation` e `item`;
  - cuatro columnas con el valor de `stream` de cada flujo: `stream_env_init` (3, ENV_INIT),
    `stream_env_dynamics` (4, ENV_DYNAMICS), `stream_policy_prey` (5, POLICY_PREY) y
    `stream_policy_predator` (6, POLICY_PREDATOR).

  La clave de cada flujo es (`purpose`, `seed_group`, `run`, `generation`, `item`,
  `stream_<flujo>`). El flujo se reconstruye exactamente con
  `numpy.random.default_rng(numpy.random.SeedSequence(project_seed, spawn_key=clave))`, el mismo
  cálculo que `SeedRegistry.generator`, con `project_seed` tomado de la procedencia (P1-19). Las
  cuatro columnas de flujo se registran en todas las condiciones, aunque una política no consuma
  números aleatorios o no haya depredadores (`no_predators`), porque `episode_streams` deriva
  siempre los cuatro flujos.
- **Aislamiento (D16):** las pruebas usan especificaciones sintéticas con `seed_group` ≥ 1000 y
  nunca los grupos 10–32. La ejecución de un bloque de confirmación exige una opción explícita del
  comando; sin ella, el comando la rechaza.

**P1-14. Condiciones de cada bloque.** En cada escenario, 30 (o 50) episodios de cada condición:

| Condición | Presa | Depredador | Escenarios |
|---|---|---|---|
| `rules` | Reglas | Reglas | A, B, C |
| `random_prey` | Aleatoria | Reglas | A, B, C |
| `random_predator` | Reglas | Aleatoria | A, B, C |
| `prey_probe_<sonda>` (4 condiciones) | STILL, SPIN, STRAIGHT_MAX, STRAIGHT_CRUISE | Reglas | A, B, C |
| `predator_probe_<sonda>` (4 condiciones) | Reglas | STILL, SPIN, STRAIGHT_MAX, STRAIGHT_CRUISE | A, B, C |
| `no_predators` | Reglas | — (`n_predators = 0`) | A, B |

Total: 35 condiciones (12 en A, 12 en B, 11 en C); 1050 episodios por bloque de calibración y 1750
en la confirmación. "Ejecutar un escenario" significa ejecutar todas sus condiciones. Las sondas
usan el `cruise_fraction` vigente de su especie (ADR-012). No se usan redes.

**P1-15. Alcance por escenario.** Salvo que el criterio nombre escenarios concretos, se evalúa en
**cada** escenario con la condición `rules`. A3 se aplica a las dos métricas primarias de ADR-014:
supervivencia media de la presa y fracción capturada (D5).

**P1-16. Fórmulas de los criterios.**

*Reglas generales de agregación (D14):*

- Los criterios se calculan exclusivamente desde el CSV de episodios y la procedencia.
- Solo se usan columnas enteras (numeradores, denominadores, recuentos) o flotantes que nunca son
  NaN (`prey_net_energy_rate`, cuya exposición siempre es > 0). Un NaN en una columna usada es un
  error que detiene la evaluación; ninguna agregación descarta observaciones en silencio (nada de
  `skipna`).
- "Media" es la media por episodio. Con el mismo número de episodios por condición y
  denominadores comunes, las comparaciones de medias se hacen con sumas enteras y los límites
  son fracciones exactas (`fractions.Fraction`), sin tolerancias.
- Las comparaciones pareadas unen las condiciones por (`seed_group`, `item`) y verifican que
  existen todos los pares; si falta alguno, la evaluación se detiene.
- Antes de cada bootstrap, las filas se ordenan por `item` (orden canónico).
- Un denominador nulo en C2 o C4 hace que esa parte de la alerta sea "no aplicable": se informa y
  no dispara la alerta.

*Columnas mínimas por episodio* (calculadas por `application/calibration.py` a partir del
`EpisodeRecord`, sin cambiar las métricas de F1): bloque, etapa, iteración, escenario, condición,
las nueve columnas de clave de P1-13, valores de todos los parámetros ajustables, hash de la
configuración, `steps`, numerador y denominador de la supervivencia de la presa, presas vivas al
final, capturas, muertes por inanición de presas, plantas comidas, exposición (Σ pasos-presa
vivos), capturas antes de 0.05·T_max, `prey_net_energy_rate`, depredadores muertos por inanición,
y por depredador (agregado por episodio) los recuentos de B3 y B6.

| Criterio | Datos | Se cumple si |
|---|---|---|
| A1 | Cada configuración candidata | El validador acepta K1–K4 y `calibration_checks` da E1, E2 y E5 satisfechas |
| A2 | Todos los episodios ejecutados (incluidas las rondas de la rejilla) | El comprobador de P1-22 no registra ninguna violación |
| A3 | `rules`, cada escenario | IQR (tipo 7, ADR-032) de la supervivencia por episodio > 0 **y** IQR de la fracción capturada por episodio > 0 |
| A4 (a) | `rules`, A | Σ plantas comidas > 0 y Σ capturas > 0 |
| A4 (b1) | `prey_probe_STILL`, A | En cada episodio, toda presa termina capturada o muerta de inanición (ninguna viva al final), y Σ muertes por inanición en el bloque ≥ 1 |
| A4 (b2) | `predator_probe_STILL`, A | En cada episodio, todo depredador muere de inanición. Si un episodio termina antes (todas las presas desaparecidas) con algún depredador vivo, b2 no se cumple |
| A4 (c) | `rules`, A y B | Σ muertes por inanición de presas en B > Σ en A |
| A4 (d) | `rules`, A y C | Σ capturas en C > Σ en A |
| A5 | `rules`, cada escenario | 1/20 ≤ Σ numeradores / Σ denominadores de la supervivencia ≤ 19/20 |
| A6 | `rules`; supervivencia por episodio de A, B y C | δ(B, A) y δ(C, A) de Cliff con IC BCa sin emparejar (9999 remuestreos, 95 %, ADR-032): el límite superior de cada IC < 0. Regla de degeneración (D1) abajo |
| B1 | `rules`, cada escenario | 1/5 ≤ supervivencia agregada ≤ 9/10 |
| B2 | `rules` frente a `random_prey` (supervivencia) y frente a `random_predator` (capturas), cada escenario | Las 6 sumas de diferencias pareadas (3 escenarios × 2 especies) > 0; IC BCa descriptivo |
| B3 | `rules`, cada escenario | Al menos la mitad (fracción exacta ≥ 1/2) de los depredadores de ese escenario en el bloque alcanza el umbral de supervivencia (D2, abajo) |
| B4 | `rules` y `no_predators` | (i) igual que A4 (c); (ii) media por episodio de `prey_net_energy_rate` en `no_predators` > 0 en A y ≤ 0 en B (interpretación abajo) |
| B5 | `rules`, A y C | Media de la incidencia acumulada de captura en T_max (presas capturadas / n_prey) en C > en A, es decir Σ capturas C > Σ capturas A (D4). La tasa por exposición (Σ capturas / Σ pasos-presa vivos) se reporta por escenario como métrica descriptiva independiente |
| B6 | `rules`, cada escenario | Todo depredador vivo en T_max tiene al menos 2 capturas (D3, abajo) |
| B7 | Configuración | Margen de K5 = R_v,prey − (r_capture + (v_max,pred + v_max,prey)·⌈π/ω_max,prey⌉) ≥ 0 |
| C1 | Cada sonda frente a `rules`, cada escenario | **Alerta** si la suma de la métrica primaria de la especie de la sonda ≥ la de `rules` |
| C2 | `rules`, cada escenario | **Alerta** si Σ capturas antes de 0.05·T_max / Σ capturas > 1/10 (no aplicable si Σ capturas = 0) |
| C3 | `rules`, cada escenario | **Alerta** si la mediana de `steps` < T_max/4 |
| C4 | `rules`, A | **Alerta** si Σ muertes por inanición / Σ muertes > 9/10 (no aplicable si Σ muertes = 0), o si Σ capturas < número de episodios (media < 1) |

- **A6, regla de degeneración (D1).** Si el BCa no es estimable y δ̂ = −1, todas las réplicas
  bootstrap valen −1 (un remuestreo de dos muestras completamente separadas sigue completamente
  separado): la distribución bootstrap es degenerada en −1, el intervalo es {−1} y A6 se cumple
  para esa comparación. Cualquier otro intervalo no estimable incumple A6. La regla se aplica en
  `analysis/calibration.py`; `stats.py` no cambia.
- **B3, supervivencia individual (D2).** Para cada depredador, t_i = paso de muerte si murió, o
  `steps` si sigue vivo al final del episodio. Umbral: 0.5·T_max = 500 pasos. Alcanza el umbral si
  t_i ≥ 500, incluido el que sigue vivo al terminar un episodio de 500 pasos o más. Si el episodio
  termina antes de 500 pasos, los depredadores vivos no alcanzan el umbral. Se registran por
  separado los censurados (vivos al final con `steps` < T_max), distinguiendo si la censura
  ocurrió antes o después del umbral. No se usa la métrica de F1 `predator_survival` para B3.
- **B4 (ii), interpretación declarada (D12).** Para una presa viva al final, energía ganada −
  gastada = e_final − E₀; para una muerta de hambre ≈ −E₀. "Tasa neta > 0" exige, por tanto, que
  la energía final media supere E₀ = 0.8·E_max; una población sostenible con energía final menor
  que E₀ da una tasa ≤ 0. E3 (ADR-030) se mantiene tal como está; si B4 falla por este motivo, se
  documenta y se decide por ADR, como cualquier criterio B.
- **B5 (D4).** La lectura literal coincide con A4 (d) porque `n_prey` es constante; se mantiene por
  fidelidad a ADR-020 y ADR-014.
- **B6 (D3).** Un depredador está vivo en T_max solo si sigue vivo y `steps` = t_max. Se usan las
  capturas reales por depredador (`predators.events` del `EpisodeRecord`). Los episodios con
  `steps` < t_max no aportan depredadores vivos en T_max. Se reporta además la condición
  suficiente E₀,pred + e_prey < c_basal,pred·T_max.

**P1-17. Ajuste de las políticas por reglas.**

- Presa: rejilla `p_flee` × `u_cruise,prey` (12 combinaciones) frente al depredador por reglas con
  sus valores vigentes. Objetivo: Σ numeradores de la supervivencia de la presa en los 30
  episodios de `rules` en A (equivale a la supervivencia media).
- Depredador: `u_cruise,pred` (3 valores) frente a la presa por reglas con los valores recién
  elegidos. Objetivo: Σ capturas en los 30 episodios de `rules` en A (equivale a la fracción
  capturada media).
- **Ronda** = rejilla de la presa seguida de la del depredador, solo con la condición `rules` en A
  y las semillas de calibración (grupo 10). Nunca usa datos de confirmación.
- **Empates** (comparación exacta de enteros, sin tolerancia), en este orden:
  1. Si la combinación vigente está entre las empatadas, se conserva.
  2. Si no, la de menor `u_cruise`.
  3. Si persiste, la de menor `p_flee`.

  *Justificación:* la comparación con enteros hace que el empate sea exacto y reproducible. La
  regla 1 exige una mejora estricta en el bloque para cambiar un valor ya fijado. La regla 2
  prefiere el menor gasto de energía en crucero (costo cuadrático, ADR-010). La regla 3 solo
  garantiza una elección única. El orden se fija antes de ver datos y no depende de ningún
  resultado.
- La alternancia con la etapa A y los límites se rigen por la máquina de estados de P1-18.

**P1-18. Etapas, iteraciones y máquina de estados (lectura L1, D7–D10).**

*Definiciones.*

- Una **iteración** es la ejecución de una configuración candidata en el bloque de calibración en
  una etapa A, B o C. Se numeran globalmente (1, 2, …) y cada una indica su etapa. La iteración 1
  es la evaluación de los valores provisionales en la etapa A.
- Cada iteración cambia **exactamente un parámetro** respecto de la última configuración evaluada
  (D10), salvo la primera iteración de cada etapa, que evalúa la configuración vigente al entrar en
  ella sin cambios. La magnitud del cambio es libre, pero se registra y justifica antes de ejecutar
  (P1-19).
- Una **ronda** es una ejecución de las dos rejillas de P1-17. Las rondas no son iteraciones de A,
  B ni C.
- Una **alternancia** es cada transición A_rev → A_ajuste: volver del ajuste de reglas a la
  etapa A porque los valores nuevos rompieron un criterio de A.
- **Contadores:** iA, iB, iC ≤ 5 (iteraciones por etapa, en toda la calibración); r ≤ 3 (rondas);
  v ≤ 3 (alternancias). Como cada alternancia sigue a una ronda con cambios, v ≤ r.
- **Conjuntos de criterios de cada etapa:** S_A = {A1, A2, A3 en A, A4 a, A4 b1, A4 b2, A5 en A};
  S_B = {A1, A2, A3 en B, A5 en B, A4 c, A6 (B, A)}; S_C = {A1, A2, A3 en C, A5 en C, A4 d,
  A6 (C, A)}.
- Los criterios B y las alertas C se evalúan **cuando se han ejecutado sus escenarios**: en A_eval y
  A_rev, B1, B2, B3 y B6 en A, y C1–C4 en A; en B_eval, además, B1, B2, B3 y B6 en B, B4, y C1–C3 en B; en
  C_eval, además, B1, B2, B3 y B6 en C, B5, y C1–C3 en C. B7 se evalúa en K.

*Restricciones de los cambios.*

- Etapa A: `plant_energy` o `regrow_delay`. `n_plants` solo se permite (D9) cuando el cambio
  necesario de `plant_energy` violaría E5, o después de dos iteraciones infructuosas (que no
  cumplieron S_A) que cambiaron `plant_energy` o `regrow_delay`. El cambio de `n_plants` se aplica a
  A y a C (C conserva N_plants de A, ADR-029) y debe mantener N_A > N_B vigente.
- Etapa B: solo `n_plants` de B, con 1 ≤ N_B < N_A.
- Etapa C: solo `n_predators` de C, con n_pred,C > n_pred,A.
- Un incumplimiento de clase B solo justifica una iteración si tiene una causa paramétrica
  identificable, nunca para alcanzar un tamaño del efecto (ADR-020); si no, se documenta la
  decisión.

*Máquina de estados.*

| Estado | Acción | Transiciones |
|---|---|---|
| K | Validar A1 y calcular B7 de la configuración candidata, sin ejecutar episodios | Cumple → estado de evaluación de la etapa. No cumple → candidata rechazada, no consume iteración; se propone otra. Si no existe ninguna dentro de las restricciones de la etapa → STOP |
| A_eval | Ejecutar el escenario A (12 condiciones); iA += 1; evaluar S_A | S_A se cumple: → T si r < 3; → T_fin si r = 3. S_A no se cumple: → A_ajuste si iA < 5; → STOP si iA = 5 |
| A_ajuste | Registrar previamente un cambio de un solo parámetro (restricciones de la etapa A) | → K → A_eval |
| T | Ronda: r += 1; rejilla de la presa y después del depredador | Ningún valor cambia → T_fin. Algún valor cambia → A_rev |
| A_rev | Ejecutar el escenario A (12 condiciones) con los valores nuevos; no consume iA (D8); evaluar S_A | S_A se cumple: → T si r < 3; → T_fin si r = 3 (se documenta que el ajuste no convergió). S_A no se cumple: v += 1; → A_ajuste si v ≤ 3 e iA < 5; → STOP en otro caso |
| T_fin | Los valores de las reglas quedan fijos para el resto de la calibración | → K → B_eval |
| B_eval | Ejecutar A y B (24 condiciones); iB += 1; evaluar S_B y los B computables | S_B se cumple y cada B computable está cumplido o con decisión documentada → K → C_eval. S_B no se cumple, o un B tiene causa paramétrica: → nuevo N_B → K → B_eval si iB < 5; → STOP si iB = 5 |
| C_eval | Ejecutar A y C (23 condiciones); iC += 1; evaluar S_C y los B computables | Análogo a B_eval con n_pred,C → E, o STOP si iC = 5 |
| E | Evaluación de entrada: las 35 condiciones con la configuración final; no es una iteración | Toda la clase A se cumple y cada B y C tiene resultado y decisión → AUT. Falla algún A → STOP |
| AUT | Informe al autor | Solo con su autorización expresa (D11) → CONF |
| CONF | Bloque de confirmación (20–22), una sola vez (P1-21) | Toda la clase A se cumple → ADR de los B no cumplidos y documentación de las C → petición de congelamiento. Falla algún A → STOP |

*Regla de no retorno.* Desde B_eval o C_eval nunca se vuelve a la etapa A ni al ajuste de reglas.
Si un resultado de B o C pareciera exigir un cambio en A, se detiene y se consulta al autor.

*STOP: se detiene F4 y se consulta al autor* cuando una etapa agota sus 5 iteraciones; v superaría
3; no existe una candidata válida dentro de las restricciones de la etapa; se viola A2; la colocación inicial falla
(`InitializationError`: la configuración se rechaza, nunca se descarta un episodio); B o C exigen
cambiar A; falla la evaluación de entrada; falla un criterio A en la confirmación; o aparece una
ambigüedad nueva que afecte a los criterios.

**P1-19. Registro previo de cada iteración.**

- Antes de ejecutarla, cada iteración (y cada ronda) se describe en un archivo de especificación
  versionado: etapa, número, valores, parámetro cambiado, magnitud y motivo con referencia al
  resultado anterior y, si procede, a las observaciones exploratorias que lo motivan (P1-24).
- La especificación se registra en un commit propio que se **publica (push) antes de ejecutar**,
  de modo que GitHub fija su anterioridad.
- La ejecución ocurre sobre ese commit. La procedencia se captura antes de escribir ningún
  resultado (árbol limpio) e incluye commit, sistema operativo, CPU, versión de Python y de las
  dependencias, `project_seed` y hashes de configuración.
- Los resultados (`results/pilots/p1/…`: CSV de episodios, CSV de claves del bootstrap, CSV de
  criterios y procedencia) y la entrada en `docs/pilot_report.md` se registran en el commit
  siguiente, incluidas las iteraciones fallidas.
- Después de la primera iteración, `analysis/calibration.py` y este ADR solo cambian con
  autorización del autor, y cualquier cambio obliga a reevaluar todas las iteraciones anteriores
  desde sus CSV.

**P1-20. Claves del bootstrap (D15).**

- Clave: `(5 ANALYSIS, seed_group de A en el bloque, run, 0, comparación, 7 BOOTSTRAP)`.
- `run` = número de iteración en la calibración (≥ 1); `run = 0` con el grupo 10 para la
  evaluación de entrada; `run = 0` con el grupo 20 para la confirmación y con el grupo 30 para una
  segunda confirmación.
- Comparaciones: 1 = A6 δ(B, A); 2 = A6 δ(C, A); 3, 4 y 5 = B2 de la presa en A, B y C; 6, 7 y 8 =
  B2 del depredador en A, B y C.
- Las claves ANALYSIS con `seed_group` ∈ {10, 20, 30} quedan **reservadas para P1**; otros análisis
  (F8) no pueden usarlas.
- El CSV de claves contiene `project_seed` y los seis enteros de cada clave. `project_seed` tiene
  128 bits y se lee como texto (ADR-023, tipos explícitos) antes de convertirlo a entero.
- Una prueba comprueba que la reconstrucción desde NumPy produce el mismo generador que
  `SeedRegistry.generator` con la misma clave.

**P1-21. Confirmación (D11, D18).**

- Solo empieza tras la evaluación de entrada (E) y con la **autorización expresa del autor**.
- Se ejecuta una sola vez con la configuración final, sin cambiar nada después de verla.
- Si falla un criterio A, se detiene y se consulta al autor; una segunda confirmación solo es
  posible tras una recalibración documentada y autorizada, con los grupos 30–32.
- Un fallo de infraestructura (por ejemplo, un error del programa o un corte de energía, nunca una
  violación de A2) permite repetir la confirmación con las mismas semillas, descartando los
  resultados parciales sin usarlos, y se documenta.

**P1-22. Comprobador A2.**

- Observador síncrono sobre `on_step`, como el visor (ADR-031). `StepTrace.world` es el estado
  vivo: el comprobador solo lo lee y nunca lo modifica.
- S₀ no pasa por `on_step` (ADR-031): se reconstruye con `initialize_world` sobre flujos nuevos de
  la misma identidad de semillas (V7) y se comprueba que cada depredador está a distancia ≥ d_safe
  de cada presa.
- En cada paso: presas vivas + capturadas + muertas de inanición = n_prey; depredadores vivos +
  muertos de inanición = n_predators; 0 < e ≤ E_max para todo agente vivo; ninguna captura en el
  primer paso (paso 0).
- Una violación detiene el bloque de inmediato y registra el episodio, el paso y la invariante. No
  se produce CSV de criterios del bloque incompleto, y se consulta al autor: indicaría un defecto
  del núcleo de F1.
- Una prueba de hashes por paso demuestra que el comprobador no altera la trayectoria (mismo
  método que la no interferencia del visor en F2).

**P1-23. Pruebas cerradas en el congelamiento (D13).** Si al congelar los valores falla alguna
prueba de una fase cerrada distinta de la autorizada en P1-2 (por ejemplo, las de
`tests/unit/application/test_session.py` que exigen capturas, alimentaciones o muertes con la
configuración real), se detiene y se consulta al autor. Esas pruebas no se modifican por iniciativa
propia.

**P1-24. Uso exploratorio durante F4 (D17).** `neuroeco run` y `neuroeco view` solo se usan con el
`seed_group` 0 y para depurar. Toda observación exploratoria que motive un cambio de parámetros se
cita en el registro previo de la iteración correspondiente (P1-19), publicado antes de ejecutarla.

### Ubicación del código y extensión de archivos existentes

Además de P1-10, F4 **añade** sin cambiar lo existente: la carga de la especificación de P1 en
`infrastructure/config_loader.py` y el comando `neuroeco pilot p1` en `presentation/cli.py`. Los
comandos `run`, `view` y `pilot p0`, el dominio, las métricas, las semillas y `stats.py` no
cambian.

## Consecuencias

- Todos los criterios de ADR-020 se pueden recomputar desde los CSV versionados, de forma exacta y
  en cualquier sistema (salvo diferencias de redondeo del BCa entre plataformas, que solo
  importarían en una frontera exacta).
- Los episodios son reproducibles bit a bit en la misma máquina con el mismo `uv.lock`; entre
  máquinas, estadísticamente (ADR-016). P1 se ejecuta en el portátil del autor.
- La calibración y la confirmación usan semillas disjuntas fijadas antes de ver ningún dato. La
  selección repetida sobre las 30 semillas de calibración hace que sus resultados sean optimistas;
  la confirmación independiente lo controla.
- B2 es descriptivo y las alertas C tienen falsos positivos esperables (24 comparaciones de C1 por
  bloque); A6 es conjuntiva (intersección-unión) y no requiere corrección por multiplicidad.
- Los valores de la rejilla elegidos son condicionales al bloque de calibración y a la rejilla.
- Coste estimado: unos 7–10 minutos por bloque de calibración completo y 12–15 minutos para la
  confirmación en el portátil del autor.

## Verificación

F4: pruebas de `application/calibration.py` y `analysis/calibration.py`, todas con
especificaciones sintéticas y grupos ≥ 1000: comprobador A2 con violaciones inyectadas y prueba de
hashes por paso; criterios sobre CSV sintéticos con fronteras exactas, NaN, denominadores nulos,
pares incompletos y la regla de degeneración de A6; censura de B3 y B6 con episodios terminados
antes de T_max; equivalencia de la semilla del bootstrap con `SeedRegistry`; rechazo de la
confirmación sin la opción explícita. `docs/pilot_report.md` (sección P1) con todas las
iteraciones; ADR de congelamiento; etiqueta `env-frozen-v1`.

## Historial

- **T0 (`deb2ac4`):** P1-1 a P1-12 aprobadas; P1-13 a P1-22 propuestas.
- **T0b:** auditoría metodológica previa a cualquier dato. Correcciones aprobadas por el autor:
  D1 (A6 con IC degenerado), D2 (B3 con supervivencia individual y censura), D3 (B6 con
  `steps` = t_max y capturas por depredador), D4 (B5 literal; tasa por exposición descriptiva),
  D5 (A3 con las dos métricas primarias), D6 (A4 b1 y b2), D7 (lectura L1 de la alternancia),
  D8 (A_rev no consume iteraciones), D9 (condición para cambiar `n_plants`), D10 (un parámetro por
  iteración, magnitud prerregistrada), D11 (autorización antes de la confirmación), D12
  (interpretación de E3), D13 (P1-23), D14 (reglas de agregación), D15 (claves del bootstrap),
  D16 (aislamiento de pruebas y protección de la confirmación), D17 (P1-24), D18 (repetición por
  fallo de infraestructura). Se añadieron P1-23 y P1-24.
- **Precisión documental posterior a T0b** (revisión del autor): la redacción de P1-13 sobre el
  registro de las claves en el CSV se precisó (cinco columnas comunes y cuatro columnas de flujo,
  y cómo se reconstruye cada flujo). No cambia ninguna decisión ni el esquema de semillas de
  ADR-028.
- **Precisión documental posterior a T0b** (revisión del autor): la lista de columnas mínimas de
  P1-16 remite ahora a "las nueve columnas de clave de P1-13" en lugar de "las seis componentes de
  la clave", para que coincida con P1-13. No cambia ninguna decisión.
