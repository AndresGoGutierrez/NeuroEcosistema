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
| Criterio (A4) | c_step ≤ 500 µs con 50 presas y 8 depredadores |
| Calentamiento | Un episodio corto previo que no se registra |
| Reloj | `time.perf_counter`, inyectado; el dominio no lee el reloj |
| Comando | `uv run neuroeco pilot p0` |

### Resultado registrado

Ejecución del 2026-11-15 sobre el commit `d1b6e57` con el árbol limpio. Máquina: Windows 11,
procesador Intel64 Family 6 Model 183 (32 hilos lógicos), Python 3.12.14, NumPy 2.5.4, un hilo
de BLAS. Datos completos en `results/pilots/p0/`.

| n_prey | n_pred | Mediana (µs/paso) | Mín | Máx | Percepción | Decisión | Reglas |
|---|---|---|---|---|---|---|---|
| 10 | 3 | 328.2 | 317.9 | 336.6 | 163.9 | 29.8 | 112.6 |
| 10 | 8 | 342.4 | 339.9 | 349.7 | 174.6 | 30.9 | 116.7 |
| 25 | 3 | 414.4 | 410.6 | 455.3 | 215.6 | 33.7 | 141.0 |
| 25 | 8 | 460.4 | 458.0 | 476.8 | 244.7 | 35.6 | 154.5 |
| 50 | 3 | 600.0 | 585.6 | 689.2 | 328.3 | 39.8 | 201.7 |
| **50** | **8** | **833.0** | **583.7** | **838.1** | 465.2 | 53.1 | 274.3 |

**Veredicto: FAIL.** c_step = 833 µs en la configuración de referencia, por encima de 500 µs.

### Variabilidad de la medición

Una ejecución anterior con el mismo código de simulación (commit `652591e`) dio c_step = 574 µs en
la referencia, con un rango de 563–584 µs. Se descartó como evidencia porque su procedencia era
incorrecta (se registró `git_dirty` después de escribir los resultados; corregido en `d1b6e57`),
pero muestra que **la medición varía mucho entre ejecuciones en este portátil**: 574 frente a
833 µs para el mismo código. Las celdas se miden siempre en el mismo orden y la de referencia es
la última, lo que es compatible con estrangulamiento térmico o de energía; no está demostrado.

El veredicto no depende de ese ruido: el mínimo observado en la referencia en ambas ejecuciones
(563 y 584 µs) supera el umbral.

### Dónde se va el tiempo

Perfil de un episodio de referencia con `cProfile` (solo proporciones relativas, porque el
perfilador añade sobrecarga):

- La percepción supone alrededor del 56 % del costo; las reglas del mundo el 33 %; la decisión
  el 6 %.
- `geometry.minimal_displacement` concentra la mayor parte del tiempo propio, con unas 8 llamadas
  por paso. La causa es una **redundancia de la implementación**: `encode_nearest` calcula el
  desplazamiento toroidal dos veces (una dentro de `pairwise_distances` y otra para los rumbos), y
  la percepción presa→depredador y depredador→presa recalcula el mismo conjunto de pares.

### Plan de optimización (pendiente de aprobación)

| ID | Cambio | ¿Cambia algún resultado? | Efecto esperado |
|---|---|---|---|
| O1 | Calcular el desplazamiento una sola vez en `encode_nearest` y obtener las distancias con `hypot` del mismo array | No: operaciones idénticas, resultado idéntico bit a bit | Elimina 3 de las ~8 llamadas por paso |
| O2 | Calcular una vez por paso el desplazamiento presa↔depredador y usar su negación para la percepción del depredador | No para lo percibido: solo difiere cuando una componente vale exactamente L/2, y esa distancia supera el radio de visión por K3 | Elimina otra llamada por paso |
| O3 | Limitar percepción e interacciones a agentes vivos y plantas activas | No | Reduce el costo a medida que mueren agentes |
| O4 | Metodología de medición: orden de celdas aleatorizado y entrelazado, calentamiento por celda, registro del estado de energía y 3 ejecuciones completas de P0 | No (afecta solo a la medición) | Medición menos sesgada por el estado de la máquina |

O1–O3 se verificarían con las pruebas de determinismo (DET-1, DET-2, DET-5), con una prueba de
equivalencia entre la implementación anterior y la nueva sobre estados aleatorios, y con P0 repetido.
