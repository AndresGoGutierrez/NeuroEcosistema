# ADR-033: Definiciones operativas de la calibración P1 (F4)

- **Estado:** Aceptada en las decisiones P1-1 a P1-12, aprobadas por el autor el 2026-11-15. Las
  definiciones complementarias P1-13 a P1-22 se proponen en T0 de F4 y quedan **pendientes de la
  revisión del autor**; ningún episodio de P1 se ejecuta antes de esa revisión.
- **Fecha:** 2026-11-15
- **Eje de la bitácora:** Diseño experimental / Ingeniería y reproducibilidad
- **Requisitos relacionados:** §6 (tres escenarios con diferencias medibles; referencia por reglas
  y aleatoria; semillas registradas), §9 (reproducibilidad)

## Contexto

ADR-020 fija el procedimiento y las clases de criterios de P1, ADR-012 exige ajustar y congelar
`p_flee` y `u_cruise`, y ADR-029 y ADR-030 dejan los valores numéricos pendientes de P1. Esos
ADR no bastan para implementar P1 sin elegir criterios: varios no tienen definición operativa
(A4, B2, B6, C4), no fijan el alcance por escenario ni el tamaño del bloque de calibración, y la
derivación de semillas del bootstrap choca con el aislamiento de `analysis`. Si esas elecciones
se hicieran durante la calibración, se fijarían reglas después de ver datos. Este ADR las fija
**antes** de generar ningún dato. No modifica ADR-010, ADR-012, ADR-014, ADR-020, ADR-028,
ADR-029, ADR-030 ni ADR-032.

## Alternativas consideradas

| Tema | Alternativas | Elegida |
|---|---|---|
| Semillas del bootstrap (A6, B2) | Importar `SeedRegistry` en `analysis` (rompe el contrato de capas) / semillas ad hoc en `analysis` / clave calculada en la aplicación y registrada en CSV | Clave registrada en CSV; `analysis` reconstruye el `SeedSequence` con NumPy |
| Prueba de F1 que fija los valores provisionales | Borrarla / mantenerla y no calibrar / sustituirla en el congelamiento | Sustituirla por una que fije los valores congelados |
| Bloque de calibración | Mismo bloque que la confirmación / bloque nuevo en cada iteración / bloque fijo e independiente | Bloque fijo de 30 episodios por escenario, independiente de la confirmación |
| Objetivo del ajuste de las reglas | Sin rejilla / rejilla con objetivo común / rejilla con la métrica primaria de cada especie | Métrica primaria de cada especie, en A, frente a la otra especie por reglas |
| Empates en la rejilla | Elección libre / tolerancia numérica / orden fijo previo | Comparación exacta con enteros y orden de preferencia fijado en este ADR |
| Registro de los valores congelados | Editar ADR-012, ADR-029 y ADR-030 / ADR nuevo | ADR nuevo, sin modificar los anteriores |

## Evidencia disponible

- Analítica: con el emparejamiento por semillas dentro de cada escenario, las comparaciones
  reglas − aleatoria y reglas − sonda usan los mismos entornos (números aleatorios comunes,
  ADR-028). Con `seed_group` distintos por escenario, las comparaciones entre escenarios son
  entre muestras independientes, como exige el δ de Cliff sin emparejar de A6.
- Analítica (valores provisionales, decisión A5 de F1): K1–K4, E1, E2 y E5 se cumplen; el margen
  de K5 es 20 − (2.5 + 2.3·⌈π/0.5⌉) = 1.4 > 0; E₀,pred + e_prey = 80 + 40 = 120 < c_basal·T_max =
  160, de modo que un depredador con menos de dos capturas no puede llegar a T_max con ninguna
  política (condición suficiente de E4).
- Empírica (F3, informativa): el IC BCa del δ de Cliff cubrió 0.956 con 50 × 50; el de la media
  pareada cubrió 0.942 y 0.933 con n = 50. Por eso el BCa de B2 es solo descriptivo.
- Pendiente: todos los resultados de P1 (F4).

## Criterio de selección

Que cada criterio de ADR-020 sea computable de forma reproducible desde los CSV, que ninguna
regla dependa de resultados observados y que no se cambie ningún ADR aprobado.

## Decisión

### Decisiones aprobadas por el autor (P1-1 a P1-12)

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
configuración. La modificación se justifica en el commit y en el ADR de congelamiento.

**P1-3. Definición operativa de A4.** En el escenario A con políticas por reglas hay alimentación
y capturas (ambas con media por episodio > 0); la sonda STILL muere de inanición; B presenta más
muertes por inanición que A, y C más capturas que A (precisión en P1-16).

**P1-4. Ajuste de las políticas por reglas.** Rejillas `p_flee` ∈ {0.2, 0.3, 0.4, 0.5} y
`u_cruise` ∈ {0.3, 0.5, 0.7}. Cada especie maximiza su métrica primaria frente a la otra especie
por reglas en el escenario A. Se registran los resultados de todas las combinaciones. La mejor
combinación es la mejor **de la rejilla en este bloque**, no un óptimo global, y así se reporta.
Procedimiento y empates en P1-17.

**P1-5. Bloques.** Calibración: 30 episodios por escenario, con las mismas semillas en todas las
iteraciones. Confirmación: 50 semillas nuevas, independientes de la calibración, con un
`seed_group` por escenario (ADR-020). Valores en P1-13.

**P1-6. Parámetros ajustables en la etapa A.** Primero `plant_energy` y `regrow_delay`; después
`n_plants`. No se cambian la geometría (`size`, radios) ni los parámetros de las especies sin
consultar al autor. Tampoco `t_max`, `n_prey`, `prey_energy` (e_prey) ni `n_predators` de A.

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

### Definiciones complementarias (P1-13 a P1-22, pendientes de revisión del autor)

**P1-13. Semillas de los episodios.** Propósito PILOT; `run = 0`, `generation = 0`, `item` = índice
del episodio (0…29 en calibración, 0…49 en confirmación). `seed_group` declarados en la
especificación de P1 y comprobados por el cargador junto con los existentes (0 exploratorio,
1 P0):

| Bloque | A | B | C |
|---|---|---|---|
| Calibración | 10 | 11 | 12 |
| Confirmación | 20 | 21 | 22 |
| Segunda confirmación (solo tras una recalibración documentada, ADR-020) | 30 | 31 | 32 |

Dentro de un escenario, todas las condiciones (P1-14), todas las combinaciones de la rejilla y
todas las iteraciones usan las mismas claves: las comparaciones dentro del escenario son
pareadas y las comparaciones entre escenarios son independientes. Ningún episodio se descarta ni
se sustituye.

**P1-14. Condiciones de cada bloque.** En cada escenario, 30 (o 50) episodios de cada condición:

| Condición | Presa | Depredador | Escenarios |
|---|---|---|---|
| `rules` | Reglas | Reglas | A, B, C |
| `random_prey` | Aleatoria | Reglas | A, B, C |
| `random_predator` | Reglas | Aleatoria | A, B, C |
| `prey_probe_<sonda>` (4 condiciones) | STILL, SPIN, STRAIGHT_MAX, STRAIGHT_CRUISE | Reglas | A, B, C |
| `predator_probe_<sonda>` (4 condiciones) | Reglas | STILL, SPIN, STRAIGHT_MAX, STRAIGHT_CRUISE | A, B, C |
| `no_predators` | Reglas | — (`n_predators = 0`) | A, B |

Total: 35 condiciones; 1050 episodios por bloque de calibración y 1750 en la confirmación. Las
sondas usan el `cruise_fraction` vigente de su especie (ADR-012). No se usan redes.

**P1-15. Alcance por escenario.** Salvo que el criterio nombre escenarios concretos, se evalúa en
**cada** escenario con la condición `rules`. A3 se aplica a las dos métricas primarias
(supervivencia media de la presa y fracción capturada, ADR-014).

**P1-16. Fórmulas de los criterios.** Todas se calculan desde el CSV de episodios. "Media" es la
media por episodio; las razones primarias se suman como enteros (numerador y denominador comunes,
ADR-017), de modo que las comparaciones con los límites son exactas. Las desigualdades son las
escritas, sin tolerancias.

| Criterio | Datos | Se cumple si |
|---|---|---|
| A1 | Cada configuración evaluada | El validador acepta K1–K4 y `calibration_checks` da E1, E2 y E5 satisfechas |
| A2 | Todos los episodios de todas las condiciones | El comprobador de P1-22 no registra ninguna violación |
| A3 | `rules`, cada escenario | IQR (tipo 7, ADR-032) de la supervivencia por episodio > 0 y de la fracción capturada por episodio > 0 |
| A4 | `rules` y `prey_probe_STILL` | (a) en A, media de plantas comidas > 0 y media de capturas > 0; (b) en A, con la presa STILL, ninguna presa viva en T_max en ningún episodio y al menos una muerte por inanición; (c) media de muertes por inanición por episodio B > A; (d) media de capturas por episodio C > A |
| A5 | `rules`, cada escenario | 0.05 ≤ Σ numeradores / Σ denominadores de la supervivencia ≤ 0.95 |
| A6 | `rules`; supervivencia por episodio | δ(B, A) y δ(C, A) de Cliff con IC BCa sin emparejar (9999 remuestreos, 95 %, ADR-032): el límite superior de cada IC < 0. Un IC "no estimable" no cumple |
| B1 | `rules`, cada escenario | 0.20 ≤ supervivencia agregada ≤ 0.90 |
| B2 | `rules` frente a `random_prey` (supervivencia) y frente a `random_predator` (fracción capturada), cada escenario | Las 6 diferencias medias pareadas (3 escenarios × 2 especies) > 0; IC BCa descriptivo |
| B3 | `rules`, cada escenario | Mediana entre episodios de la supervivencia media de los depredadores (Σ pasos vivos / (n_pred·T_max)) ≥ 0.5 |
| B4 | `rules` y `no_predators` | Media de muertes por inanición B > A (igual que A4 c) y media por episodio de la tasa neta de energía de la presa (`prey_net_energy_rate`) en `no_predators` > 0 en A y ≤ 0 en B |
| B5 | `rules` | Tasa de captura ajustada por exposición agregada (Σ capturas / Σ pasos-presa vivos) C > A |
| B6 | `rules`, cada escenario | Ningún depredador vivo en T_max tiene menos de 2 capturas (medida; se reporta además la condición suficiente E₀,pred + e_prey < c_basal,pred·T_max) |
| B7 | Configuración | Margen de K5 = R_v,prey − (r_capture + (v_max,pred + v_max,prey)·⌈π/ω_max,prey⌉) ≥ 0 |
| C1 | Sondas frente a `rules`, cada escenario | **Alerta** si la media de la métrica primaria de una sonda ≥ la de `rules` de su especie |
| C2 | `rules`, cada escenario | **Alerta** si Σ capturas antes de 0.05·T_max / Σ capturas > 0.10 |
| C3 | `rules`, cada escenario | **Alerta** si la mediana de la duración del episodio (`steps`) < 0.25·T_max |
| C4 | `rules`, escenario A | **Alerta** si Σ muertes por inanición / Σ muertes > 0.90, o si la media de capturas por episodio < 1 |

B5 usa la tasa por exposición para no repetir A4 (d): con `n_prey` constante, la incidencia
acumulada de captura en T_max equivale al número medio de capturas.

**P1-17. Procedimiento de ajuste de las reglas.**

- Presa: rejilla `p_flee` × `u_cruise,prey` (12 combinaciones) frente al depredador por reglas con
  sus valores vigentes. Objetivo: Σ numeradores de la supervivencia de la presa en los 30
  episodios de A (equivale a la supervivencia media).
- Depredador: `u_cruise,pred` (3 valores) frente a la presa por reglas con los valores recién
  elegidos. Objetivo: Σ capturas en los 30 episodios de A (equivale a la fracción capturada media).
- **Ronda** = rejilla de la presa seguida de la del depredador. Tras cada ronda se reevalúan los
  criterios de la etapa A con los valores nuevos. Si se incumplen, se vuelve a la etapa A (sus
  iteraciones cuentan para su límite de 5). Si una ronda no cambia ningún valor, el ajuste termina.
  Como máximo **3 rondas** ("alternando como máximo 3 veces", ADR-020); si la tercera aún cambia
  valores, se conservan esos y se documenta que el ajuste no convergió.
- **Empates** (comparación exacta de enteros, sin tolerancia), en este orden:
  1. Si la combinación vigente está entre las empatadas, se conserva.
  2. Si no, la de menor `u_cruise`.
  3. Si persiste, la de menor `p_flee`.

  *Justificación:* la comparación con enteros hace que el empate sea exacto y reproducible. La
  regla 1 exige una mejora estricta en el bloque para cambiar un valor ya fijado. La regla 2
  prefiere el menor gasto de energía en crucero (costo cuadrático, ADR-010). La regla 3 solo
  garantiza una elección única. El orden se fija antes de ver datos y no depende de ningún
  resultado.

**P1-18. Etapas e iteraciones.**

- Una **iteración** es la ejecución de una configuración candidata en el bloque de calibración.
  Se numeran globalmente (1, 2, …) y cada una indica su etapa. Una ronda de la rejilla cuenta como
  una iteración de la etapa de ajuste.
- Iteración 1 = valores provisionales sin cambios.
- Cada iteración de las etapas A, B o C cambia **un solo parámetro**, respetando el orden de P1-6
  y las restricciones A1. B cambia solo su `n_plants` (1 ≤ N_plants,B < N_plants,A) y C solo su
  `n_predators` (n_pred,C > n_pred,A). El cambio de `n_plants` en la etapa A se aplica a A y a C
  (C conserva N_plants de A, ADR-029).
- Escenarios ejecutados: etapa A y ajuste, solo A; etapa B, A y B; etapa C, A y C.
- **Límite:** 5 iteraciones por etapa en toda la calibración (el ajuste, como máximo 3 rondas). Si
  una etapa lo agota sin cumplir sus criterios, se detiene la calibración y se consulta al autor.
- Criterios que decide cada etapa: A, los de clase A computables en A (A1, A2, A3, A4 a y b, A5);
  B, A3 y A5 en B, A4 c y A6 (B, A); C, A3 y A5 en C, A4 d y A6 (C, A). Los criterios B se
  evalúan en cada etapa. Un incumplimiento de clase B solo justifica recalibrar con una causa
  paramétrica identificable, nunca para alcanzar un tamaño del efecto (ADR-020).
- **Evaluación de entrada a la confirmación:** el bloque de calibración completo (35 condiciones)
  con la configuración final. No es una iteración, porque no cambia ningún valor.

**P1-19. Registro previo de cada iteración.** Antes de ejecutarla, cada iteración se describe en un
archivo de especificación versionado (etapa, número, valores, parámetro cambiado, motivo con
referencia al resultado anterior) y se registra en un commit propio. La ejecución ocurre sobre ese
commit, con árbol limpio en la procedencia. Los resultados (`results/pilots/p1/…`: CSV de
episodios, CSV de claves del bootstrap, CSV de criterios y procedencia) y la entrada en
`docs/pilot_report.md` se registran en el commit siguiente, incluidas las iteraciones fallidas.

**P1-20. Claves del bootstrap.** `(5 ANALYSIS, seed_group de A en el bloque, número de iteración,
0, comparación, 7 BOOTSTRAP)`. En la confirmación, el número de iteración es 0 y el `seed_group`
es 20 (30 en una segunda confirmación). Comparaciones: 1 = A6 δ(B, A); 2 = A6 δ(C, A); 3, 4 y
5 = B2 de la presa en A, B y C; 6, 7 y 8 = B2 del depredador en A, B y C. El CSV de claves contiene
`project_seed` (como texto, porque tiene 128 bits) y los seis enteros de cada clave.

**P1-21. Confirmación.** Solo empieza si la evaluación de entrada cumple toda la clase A y si cada
criterio B y alerta C tiene su resultado y su decisión documentados. Se ejecuta una sola vez con
la configuración final, sin cambiar nada después de verla. Si falla un criterio A, se detiene y se
consulta al autor; una segunda confirmación solo es posible tras una recalibración documentada,
con los `seed_group` 30–32.

**P1-22. Comprobador A2.** Observador síncrono sobre `on_step` (como el visor, ADR-031) que no
modifica el estado. En S₀ comprueba que cada depredador está a distancia ≥ d_safe de cada presa;
en cada paso, vivas + capturadas + muertas de hambre = n_prey, vivos + muertos de hambre =
n_predators y 0 < e ≤ E_max para todo agente vivo; al final, que ninguna captura ocurrió en el
primer paso (`capture_step` ≥ 1). Una violación detiene el bloque, se registra el episodio y el
paso, y se consulta al autor: indicaría un defecto del núcleo de F1.

### Ubicación del código y extensión de archivos existentes

Además de P1-10, F4 **añade** sin cambiar lo existente: la carga de la especificación de P1 en
`infrastructure/config_loader.py` y el comando `neuroeco pilot p1` en `presentation/cli.py`. Los
comandos `run`, `view` y `pilot p0`, el dominio, las métricas y las semillas no cambian.

## Consecuencias

- Todos los criterios de ADR-020 se pueden recomputar desde los CSV versionados.
- La calibración y la confirmación usan semillas disjuntas fijadas antes de ver ningún dato.
- Los valores de la rejilla elegidos son condicionales al bloque de calibración y a la rejilla.
- Coste estimado: unos 7–10 minutos por bloque de calibración completo y 12–15 minutos para la
  confirmación en el portátil del autor.

## Verificación

F4: pruebas de `application/calibration.py` y `analysis/calibration.py` (comprobador A2 con
violaciones inyectadas; criterios sobre CSV sintéticos con fronteras exactas; reconstrucción de
la semilla del bootstrap); `docs/pilot_report.md` (sección P1) con todas las iteraciones; ADR de
congelamiento; etiqueta `env-frozen-v1`.
