# Informe de pilotos

Los pilotos fijan parámetros y verifican supuestos antes de los experimentos formales. Usan
semillas del propósito PILOT, nunca reutilizadas en los experimentos (ADR-028). Sus resultados no
son conclusiones del proyecto.

## P0: costo de la simulación por paso (F1)

### Pregunta y alcance

¿Cuánto cuesta un paso de simulación y cómo escala con el tamaño de las poblaciones? En F1 se
mide la simulación en un solo proceso, desglosada en percepción, decisión (política por reglas) y
reglas del mundo. El forward de la red y la aceleración en paralelo se medirán en P0b (F6),
según la decisión A3.

### Método

| Elemento | Valor |
|---|---|
| Especificación | `configs/pilots/p0.yaml` (`seed_group` 1) |
| Rejilla | n_prey ∈ {10, 25, 50} × n_predators ∈ {3, 8}; 40 plantas; parámetros provisionales (A5) |
| Políticas | Por reglas en ambas especies |
| Repeticiones | 5 episodios independientes por celda (semillas PILOT, `item` 0–4) |
| Medida | c_step = mediana de las 5 repeticiones del tiempo medio por paso de cada episodio |
| Criterio (A4) | c_step ≤ 500 µs con 50 presas y 8 depredadores (configuración de referencia) |
| Orden de medición | Celdas en orden fijo (10, 25, 50 presas × 3, 8 depredadores); repeticiones consecutivas |
| Calentamiento | Un episodio previo de hasta 50 pasos en la configuración de referencia, no registrado |
| Reloj | `time.perf_counter`, inyectado; el dominio no lee el reloj |
| Comando | `uv run neuroeco pilot p0` |

La configuración de referencia (50 presas, 8 depredadores) es una **prueba de esfuerzo**: tiene
el doble de presas que cualquier escenario experimental provisional. El autor la fijó así al aprobar el plan
de F1 (A4) y confirmó que se mantiene tras conocer los resultados.

### Resultado registrado

Ejecución del 2026-11-15 sobre el commit `d1b6e57` con el árbol limpio. Máquina: Windows 11,
procesador Intel64 Family 6 Model 183 (32 hilos lógicos), Python 3.12.14, NumPy 2.5.4, variables
de hilos de BLAS fijadas a 1 (la verificación con threadpoolctl llega en F6). Datos completos en
`results/pilots/p0/`.

| n_prey | n_pred | Mediana (µs/paso) | Mín | Máx | Percepción | Decisión | Reglas |
|---|---|---|---|---|---|---|---|
| 10 | 3 | 328.2 | 317.9 | 336.6 | 163.9 | 29.8 | 112.6 |
| 10 | 8 | 342.4 | 339.9 | 349.7 | 174.6 | 30.9 | 116.7 |
| 25 | 3 | 414.4 | 410.6 | 455.3 | 215.6 | 33.7 | 141.0 |
| 25 | 8 | 460.4 | 458.0 | 476.8 | 244.7 | 35.6 | 154.5 |
| 50 | 3 | 600.0 | 585.6 | 689.2 | 328.3 | 39.8 | 201.7 |
| **50** | **8** | **833.0** | **583.7** | **838.1** | 465.2 | 53.1 | 274.3 |

Las columnas de fase son medianas del tiempo por paso de cada fase; no suman exactamente la
mediana total.

**Veredicto: FAIL.** c_step = 833 µs en la configuración de referencia, por encima de 500 µs.

**Información complementaria (no sustituye a la referencia):** la celda 25/8 coincide con el
escenario C provisional (25 presas, 8 depredadores, 40 plantas). Su mediana es 460.4 µs y sus
cinco repeticiones quedan entre 458.0 y 476.8 µs. El margen frente a 500 µs (8 %) es pequeño en
comparación con la variabilidad observada entre ejecuciones (siguiente apartado). La celda 25/3
corresponde al escenario A; el escenario B (15 plantas) no se midió.

### Variabilidad de la medición

Una ejecución anterior (commit `652591e`) dio c_step = 574.3 µs en la referencia, con un rango
de 563.5–584.4 µs. Se descartó como evidencia porque su procedencia era incorrecta (se registró
`git_dirty` después de escribir los resultados; corregido en `d1b6e57`). Entre ambos commits solo
cambiaron la CLI y su prueba, y la simulación es determinista (DET-1), así que **los episodios
medidos son idénticos en las dos ejecuciones** y las diferencias se deben solo a la medición:

- Referencia 50/8: 574.3 µs frente a 833.0 µs.
- Dentro de la ejecución registrada, en la referencia, las repeticiones 0–2 dieron entre 833.0 y
  838.1 µs y las repeticiones 3–4, medidas a continuación, 620.4 y 583.7 µs.
- Celda 25/8: 482.5 µs en la ejecución anterior frente a 460.4 µs en la registrada; la diferencia
  no va siempre en la misma dirección.

La causa no está identificada. El orden fijo de medición es compatible con efectos del estado
térmico o de energía del portátil, pero no está demostrado.

El veredicto no depende de ese ruido: ninguna repetición de la referencia, en ninguna de las dos
ejecuciones, bajó de 500 µs (mínimos de 563.5 y 583.7 µs).

### Dónde se va el tiempo

Según el desglose por fases de la tabla, en la referencia la percepción supone alrededor del
56 % de la mediana total; las reglas del mundo, el 33 %; la decisión, el 6 %.

Un perfil con `cProfile` de un episodio de referencia (570 pasos; solo proporciones relativas,
porque el perfilador añade sobrecarga) muestra:

- `geometry.minimal_displacement` es la función con más tiempo propio: alrededor del 33 % del
  tiempo total bajo el perfilador, con unas 8 llamadas por paso.
- Parte de esas llamadas son redundantes: `encode_nearest` calcula el desplazamiento toroidal dos
  veces (una dentro de `pairwise_distances` y otra para los rumbos), y la percepción
  presa→depredador y depredador→presa calcula los mismos pares en sentidos opuestos.

### Plan de optimización

Decisión del autor del 2026-11-15. Ninguna optimización se aplica en F1; las aprobadas se
realizarán antes de P0b (F6).

| ID | Cambio | Decisión | Condición |
|---|---|---|---|
| O1 | Calcular el desplazamiento una sola vez en `encode_nearest` y obtener las distancias con `hypot` del mismo array | **Aprobada** como optimización posterior | Demostrar equivalencia bit a bit con pruebas de referencia (huella del estado en cada paso, registrada antes del cambio) y con DET-1, DET-2 y DET-5 |
| O2 | Reutilizar la negación del desplazamiento presa→depredador para la percepción del depredador | **Descartada** | No se implementa: cambia los valores numéricos (ver abajo) |
| O3 | Limitar percepción e interacciones a agentes vivos y plantas activas | **Aplazada** | Solo se reconsidera si una medición demuestra un beneficio real y se garantiza la equivalencia |
| O4 | Metodología de medición: orden de celdas aleatorizado y entrelazado, calentamiento por celda, registro del estado de energía y ejecuciones adicionales de P0 | **Aprobada** como mejora de la medición | A4 no cambia: c_step y el veredicto siguen definidos por la mediana de 5 repeticiones de una ejecución en la referencia; las ejecuciones adicionales solo documentan la variabilidad |

**Por qué se descarta O2.** La versión anterior de este informe afirmaba que la negación del
desplazamiento solo difería cuando una componente valía exactamente L/2. Eso es cierto en
aritmética exacta, pero no en coma flotante: `mod(Δ + L/2, L) − L/2` redondea de forma distinta
para Δ y −Δ. Se comprobó con 200 configuraciones aleatorias de 50 presas y 8 depredadores
(L = 150, posiciones uniformes): difieren el 22.5 % de las componentes del desplazamiento y el
28.2 % de las distancias, en como máximo 1.4·10⁻¹⁴ (un ulp a esa escala). Una diferencia así
puede decidir si un objeto queda dentro del radio de visión o cómo se resuelve un empate, y
hace divergir las trayectorias. El ahorro estimado era de unos 12 µs por paso.

**Efecto esperado de O1.** En un microbenchmark aislado, el cálculo que O1 elimina cuesta unos
78 µs por paso en la referencia (53 µs para presa→planta, 50×40, y unos 12 µs para cada sentido
de presa↔depredador) y unos 42 µs en 25/8. Es una estimación: no se espera que O1 baste por sí
sola para que la referencia cumpla 500 µs. El efecto real se medirá con la metodología de O4.

## P1: calibración ecológica (F4)

### Pregunta y alcance

¿Qué valores de los parámetros ecológicos ajustables y de las políticas por reglas cumplen los
criterios de clase A de ADR-020 en los tres escenarios? La calibración sigue la máquina de estados
de ADR-033 (P1-18): etapa A con rondas de ajuste de las reglas (P1-17), etapas B y C, evaluación
de entrada y, con autorización expresa del autor, confirmación con semillas nuevas.

### Método

| Elemento | Valor |
|---|---|
| Especificación | `configs/pilots/p1.yaml`: calibración 30 episodios por condición (grupos 10/11/12), confirmación 50 (20/21/22) |
| Condiciones | 35 por bloque (P1-14); escenario A con 12 condiciones |
| Criterios | P1-16 desde los CSV (`pilot p1-criteria`); S_A, S_B y S_C de P1-18 |
| Secuencia | Verificada antes de cada bloque por la puerta de `pilot p1` (D-T4c-5, T4d) |
| Registro previo | Cada paso publicado (commit y push) antes de ejecutarse (P1-19) |
| Procedimiento | [p1_runbook.md](p1_runbook.md) |
| Valores provisionales (iteración 1) | `plant_energy` 30.0, `regrow_delay` 50, `n_plants` 40 (A, C) y 15 (B), `n_predators` 3 (A, B) y 8 (C), `p_flee` 0.3, `u_cruise` 0.5 (presa y depredador) |

### Registro de pasos

Cada paso real añade aquí una fila con su resultado y la decisión que siguió.

| Paso | Especificación | Commit del registro | Commit de los resultados | S_X | Criterios B incumplidos | Veredicto de la secuencia | Decisión |
|---|---|---|---|---|---|---|---|
| Iteración 1, intento 1 (rechazado) | `iterations/001.yaml` | `9c22a8c` | — (registro del rechazo: `iteration_001.failed-20261117T193505Z-daf4fb6a`) | — | — | — | Rechazo de la verificación previa sin ningún episodio: la configuración de Git del sistema y la global de la máquina definen los filtros `filter.lfs.clean`/`process` (T3c IA-1). El repositorio no usa LFS. Se retiran los filtros de la máquina y se repite la iteración sin cambiar su registro |
| Iteración 1, intento 2 (rechazado) | `iterations/001.yaml` | `9c22a8c` | — (registro del rechazo: `iteration_001.failed-20261117T193810Z-adab8996`) | — | — | — | Mismo rechazo sin ningún episodio: ya se había retirado el filtro global, pero seguía el del sistema. Después se retiró también el del sistema (`git config --get-regexp "^filter\."` vacío) |
| Iteración 1 (etapa A) | `iterations/001.yaml` | `9c22a8c` | `19f6503` | S_A cumplido (A1–A5 y B1–B3, B6, B7 pasan; ninguna alerta C) | Ninguno | `a round: allowed` (r = 0 < 3: ronda T) | Supervivencia agregada de presas 0.317 (238117/750000); B2 reglas − azar: presa +0.138 (BCa 95 % 0.114–0.167), depredador +0.907 (0.864–0.933); 680 capturas en 30 episodios; mediana de pasos 977. 360 episodios en 109 s, sin violación A2. Siguiente paso propuesto: ronda 01 (P1-17) |
| Ronda 1 (rejillas y A_rev) | `rounds/01.yaml` | `4627c71` | rejillas `cfbfb65`, `fb2cb77`; A_rev: commit que añade esta fila | S_A cumplido en A_rev (todos los A y B pasan; ninguna alerta C) | Ninguno | `a round: allowed` (r = 1 < 3) | Presa ganadora `p_flee` 0.2, `u_cruise` 0.3 (único; borde inferior de la rejilla de `p_flee`); depredador ganador `u_cruise` 0.7 (único, con márgenes mínimos: 654 / 652 / 647 capturas). A_rev: supervivencia agregada 0.340 (127613/375000; antes 0.317), 654 capturas, mediana de pasos 1000; BCa de B2 no se calcula en A_rev (D-T4c-1). Siguiente paso: ronda 2 |
| Ronda 2, rejilla de la presa, intento 1 (interrumpido) | `rounds/02.yaml` | `be3654c` | — (registro: `round_02/prey_grid.failed-20261117T201639Z-7e9ddf00`) | — | — | STOP por directorio parcial, levantado con D18 | El proceso se detuvo manualmente al empezar, sin ningún episodio escrito (solo `provenance.json` en estado `running`). Recuperado según D18 (renombrado sin `failure.json`; clasificado como interrupción, sin A2) y repetida la fase |
| Ronda 2 (rejillas) | `rounds/02.yaml` | `be3654c` | `2c2332b`, `5dd1229` | — (sin A_rev: ningún valor cambió) | — | `a stage-B iteration: allowed` (T_fin) | Ganadores idénticos a la ronda 1: presa `p_flee` 0.2, `u_cruise` 0.3 (255226 frente a 250021 de la segunda); depredador `u_cruise` 0.7 (mismos totales 654 / 652 / 647, porque la presa ganadora y las semillas no cambian). Las reglas quedan fijas; siguiente paso: iteración 2 (etapa B) sin cambios |
| Iteración 2 (etapa B, sin cambios) | `iterations/002.yaml` | `ffae772` | `e3e12be` | S_B no cumplido: A6 (B, A) falla | B4 (ii) | `a stage-B iteration: allowed` (iB = 1 < 5) | 720 episodios, sin violación A2. Supervivencia agregada A 0.340, B 0.339: con N_B = 15 la escasez de B no se nota (δ de Cliff 0.038, IC BCa [−0.25, 0.33]); A4 (c) y B4 (i) sí pasan (98 frente a 55 presas muertas de hambre). B4 (ii) falla ya en A: la tasa neta media de `no_predators` es −0.042 en A y −0.055 en B. No depende de N_B, así que no justifica una iteración; es el caso previsto en D12 y requerirá una decisión del autor. Siguiente: iteración 3 con N_B = 7 (la mitad) |
| Iteración 3 (etapa B, N_B = 7) | `iterations/003.yaml` | `ee1fdfa` | `ae46cb7` | S_B no cumplido: A6 (B, A) falla | B4 (ii) | `a stage-B iteration: allowed` (iB = 2 < 5) | 720 episodios, sin A2. Supervivencia B 0.316 frente a A 0.340; δ de Cliff −0.23, IC BCa [−0.50, 0.087]; muertes por hambre 192 en B frente a 55 en A. B1, B2, B3 (7/10) y B6 pasan en B; ninguna alerta C. B4 (ii) sigue fallando en A (−0.042). Siguiente: iteración 4 con N_B = 4 |
| Iteración 4 (etapa B, N_B = 4) | `iterations/004.yaml` | `0bdb66d` | `d0e8a45` | **S_B cumplido** | B4 (ii) | Pasar a C requiere una decisión `b_criteria` del autor (P1-18). **Decisión 1 del autor** (`p1_decisions/001.yaml`): pasar a la etapa C; B4 (ii) aceptado pendiente de ADR tras la confirmación (D12) | 720 episodios, sin A2. Supervivencia B 0.292 frente a A 0.340; A6 (B, A): δ de Cliff −0.54, IC BCa [−0.74, −0.26]; 224 frente a 55 muertes por hambre. B1, B2, B3 (7/9) y B6 pasan en B; ninguna alerta C (mediana de pasos en B 629). B4 (ii): −0.042 en A y −0.140 en B; la parte de A no depende de N_B (D12) |
| Iteración 5 (etapa C, n_pred,C = 8) | `iterations/005.yaml` | `797259f` | `113342a` | **S_C cumplido** | B1 en C, B3 en C | Seguir requiere una decisión `b_criteria` del autor (P1-18). **Decisión 2 del autor** (`p1_decisions/002.yaml`): repetir la etapa C con n_pred,C = 6 | 690 episodios, sin A2. Supervivencia C 0.161 (B1 exige ≥ 0.2); A4 (d) 732 frente a 654 capturas; A6 (C, A) δ = −1 (intervalo degenerado {−1}, D1). B3 en C: 2/15 (103 depredadores censurados antes del umbral: los episodios terminan pronto, mediana de pasos 464, porque las presas se agotan). Alerta C2 en C: 106 de 732 capturas antes de 0.05 T_max. Causa paramétrica identificable: demasiados depredadores en C. **Incidencia:** el bloque se ejecutó antes de comprobar que el CI de su registro (`44177087773`) había fallado. El fallo era de aislamiento de las pruebas (`make_configs` copiaba la decisión real 001 a las configuraciones sintéticas), no del código de producción; la puerta verificó huellas, decisiones y secuencia. Corregido en las pruebas en el mismo commit que publica estos resultados |
| Iteración 6, intento 1 (interrumpido) | `iterations/006.yaml` | `cd4d954` | — (registro: `iteration_006.failed-20261117T234950Z-d7cde04a`) | — | — | STOP por directorio parcial, levantado con D18 | El proceso terminó con "Illegal instruction" justo después de capturar la procedencia, sin ningún episodio escrito. No se reproduce (prueba sintética de extremo a extremo y cálculo con numpy correctos; sin errores en el registro de eventos ni actualizaciones del sistema posteriores a la reserva). Tratado como fallo de infraestructura: recuperado según D18 y repetida la iteración |
| Iteración 6 (etapa C, n_pred,C = 6) | `iterations/006.yaml` | `cd4d954` | `2ed02dc` | **S_C cumplido** | B3 en C | Seguir requiere una decisión `b_criteria` del autor (P1-18). **Decisión 3 del autor** (`p1_decisions/003.yaml`): repetir la etapa C con n_pred,C = 5 | 690 episodios, sin A2. Supervivencia C 0.203 (B1 pasa por poco); A4 (d) 716 frente a 654 capturas; A6 (C, A) δ = −0.90, IC BCa [−0.99, −0.68]. B3 en C: 43/180 (83 depredadores censurados antes del umbral; mediana de pasos 457 < T_max/2 porque las presas se agotan). Sin alertas C (C2: 71 de 716 capturas tempranas, ≤ 1/10) |
| Iteración 7 (etapa C, n_pred,C = 5) | `iterations/007.yaml` | `a1d3078` | `229ecd2` | **S_C cumplido** | B3 en C (por un depredador) | **Decisión 4** (`p1_decisions/004.yaml`, tomada por Claude por delegación expresa del autor): evaluación de entrada; B3 aceptado pendiente de ADR | 690 episodios, sin A2. Supervivencia C 0.241; A4 (d) 702 frente a 654 capturas; A6 (C, A) δ = −0.81, IC BCa [−0.92, −0.57]; mediana de pasos 898. B3 en C: 37/75 = 0.493 (umbral 1/2). Sin alertas C |
| Evaluación de entrada (estado E) | valores de `iterations/007.yaml` | `324856d` (decisión 4) | `9fee669` | **Toda la clase A cumplida** en las 35 condiciones | B3 en C, B4 (ii) (ya aceptados en las decisiones 1 y 4) | `author_authorization_required` | 1050 episodios, sin A2; ninguna alerta C. Siguiente: revisión de la entrada (decisión 5) y confirmación con los grupos 20/21/22 |
| Confirmación (grupos 20/21/22) | valores de `iterations/007.yaml` | `85db573` (decisión 5) | commit que añade esta fila | **Toda la clase A cumplida** con semillas nuevas | B3 en C (62/125 = 0.496), B4 (ii) (A −0.041, B −0.140) | CONF completada | 1750 episodios en 483 s, ejecutados por el autor con `--author-authorized`; sin A2; ninguna alerta C. Los B no cumplidos se deciden en ADR-034 |
