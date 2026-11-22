# Guion de la demo (F9)

Duración aproximada: 8–10 minutos. Todos los comandos desde la raíz del repositorio, después de
`uv sync --frozen`. `R=results/experiments/f8/runs`.

**Forma más simple:** `uv run neuroeco demo` abre una ventana de menú con botones: escenario
(A, B, C), cerebro de cada especie (reglas, red entrenada, sin entrenar, azar o red compacta en
A), número de presas (5–50) y depredadores (1–10) y la ejecución formal cuyas redes se usan
(r0–r9), y la partida (#0–#99): la semilla de las posiciones iniciales y del azar, del grupo
exploratorio (nunca una semilla TEST); la misma partida siempre se repite igual. «Ver en el
visor» abre la partida; al cerrarla con Esc se vuelve al menú.
«Resultados rápidos» simula la misma partida sin ventana y muestra sus métricas en el panel.
Sin menú: `uv run neuroeco demo --scenario A --prey rules --predator trained` (`--mode run`
para la terminal). Los pasos siguientes muestran los comandos equivalentes.

En el visor, al hacer clic en un agente se dibuja su radio de visión y el panel muestra sus
entradas, su salida y las activaciones de las capas ocultas.

## 1. El ecosistema con reglas (1 min)

```bash
uv run neuroeco view --scenario A
```

Mostrar el HUD (presas, depredadores, plantas, energía) y el inspector de un agente: sensores
(proximidad y rumbo relativo, ADR-007) y la acción aplicada.

## 2. Antes y después de entrenar: C1 (3 min)

```bash
uv run neuroeco run --scenario A --predator model:$R/f8_predator_base_A_r0/checkpoints/gen_0000.npz
uv run neuroeco run --scenario A --predator model:$R/f8_predator_base_A_r0/selected.npz
uv run neuroeco view --scenario A --predator model:$R/f8_predator_base_A_r0/selected.npz
```

Resultado ensayado (episodio 0): la red sin entrenar captura 0 presas; la entrenada, 23 de 25
(fracción 0.92). En el visor, el inspector muestra las activaciones de las capas ocultas.

## 3. Red frente a reglas: C3 (2 min)

```bash
uv run neuroeco view --scenario A --prey model:$R/f8_prey_base_A_r0/selected.npz \
                     --predator model:$R/f8_predator_base_A_r0/selected.npz
```

Explicar con `results/experiments/f8/analysis/c3_differences.png`: el depredador entrenado
iguala a las reglas (y las supera en B); la presa entrenada queda por debajo en A y C.

## 4. Resultados y reproducibilidad (2–3 min)

- `results/experiments/f8/analysis/tables.md` y las figuras (C1, C3, curvas de validación).
- `uv run neuroeco experiment analyze` regenera todas las tablas y figuras desde
  `test_episodes.csv`.
- Protocolo prerregistrado (`protocol-v1`) antes de los datos; bitácora ADR-001 a ADR-037.

## Ensayo

Los comandos `run` de la sección 2 se ensayaron el 2026-11-18 con los resultados indicados.
El visor (`view`) necesita una ventana gráfica: el autor lo prueba en su máquina antes de la
presentación.
