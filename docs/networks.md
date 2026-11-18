# Redes neuronales de los agentes (F5)

Implementación de [ADR-025](decisions/ADR-025-network-architecture.md) (arquitectura),
[ADR-018](decisions/ADR-018-network-initialization.md) (inicialización) y
[ADR-007](decisions/ADR-007-sensor-encoding.md) (entradas). Código: `src/neuroeco/domain/neural.py`
y `src/neuroeco/infrastructure/model_store.py`.

## Arquitecturas

| Modelo | Topología | Parámetros |
|---|---|---|
| `prey_base` | 10 → 16 → 16 → 2 | 482 |
| `prey_compact` (C2) | 10 → 8 → 8 → 2 | 178 |
| `predator_base` | 7 → 16 → 16 → 2 | 434 |
| `predator_compact` (C2) | 7 → 8 → 8 → 2 | 154 |

- La dimensión de entrada sale del esquema de sensores de la especie (`PREY_SCHEMA`,
  `PREDATOR_SCHEMA`, versión 1), nunca de la configuración.
- tanh en las capas ocultas y en la salida: la salida ya está en [−1, 1] y pasa por el mismo
  decodificador que las demás políticas (o₀ → giro = o₀·ω_max; o₁ → velocidad = v_max·(o₁ + 1)/2).
- `NetworkSpec` rechaza en su construcción menos de dos capas ocultas o anchuras no enteras
  positivas.

## Genoma

Vector plano de todos los pesos y sesgos, capa por capa: la matriz de pesos (fan_in × fan_out, por
filas) seguida del vector de sesgos. Es la representación que manipula el algoritmo genético
(ADR-027). `NeuralNetwork` copia el genoma y lo deja de solo lectura.

## Inicialización (ADR-018)

Pesos ~ Normal(0, 1/fan_in) y sesgos 0, capa por capa (`lecun_genome`), con el flujo `GA_INIT`
del esquema de semillas (ADR-028).

- **I1:** 10⁶ pesos con fan_in = 16 tienen varianza muestral 1/16 ± 2 %
  (`tests/unit/domain/test_neural.py`).
- **I2:** `neuroeco pilot i2` construye el conjunto de referencia (episodios de las reglas en A,
  B y C con el entorno congelado, semillas PILOT del grupo 2, una de cada 10 filas de agentes
  vivos), lo guarda en `results/pilots/f5_i2/reference_observations.npz` con su SHA-256 y evalúa
  S1–S3 sobre 100 genomas aleatorios de cada arquitectura. S1 y S2 se comprueban en todas las
  capas tanh (ocultas y salida), lo más estricto de las dos lecturas de "por capa".

## Política neuronal y ablación

- `NeuralPolicy` implementa `Policy`: es determinista y no consume su flujo aleatorio.
- `InputAblationPolicy` (ADR-019, X3) pone a cero un grupo de sensores (`plant`, `predator1`,
  `predator2`, `energy`, `prey1`, `prey2`) antes de decidir; cero es el valor de "no percibido".
- `ablate_input_weights` es la misma intervención a nivel de pesos (anula los pesos de la
  primera capa que salen de esas entradas); las pruebas comprueban que ambas coinciden y que la
  decisión cambia.

## Modelos guardados

Un modelo es un `.npz` con el genoma en float64 y una cabecera JSON (`neuroeco.model/1`):
arquitectura, especie, versión y nombres ordenados del esquema de entradas, tamaños de capa,
activación, número de parámetros, SHA-256 del genoma y metadatos.

- **DET-4:** guardar y cargar conserva las salidas bit a bit.
- La carga **rechaza** un esquema de entradas distinto (versión o nombres), otra especie o
  arquitectura, otra topología o activación y un genoma que no coincide con su SHA-256. Nunca se
  adapta un modelo.
- Un modelo existente nunca se sobrescribe.
- `neuroeco run` y `neuroeco view` aceptan `--prey model:<archivo>` y
  `--predator model:<archivo>`; el visor muestra en el inspector las activaciones de las capas
  ocultas de la decisión del agente seleccionado.
