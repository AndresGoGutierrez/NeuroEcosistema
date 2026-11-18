# ADR-035: Definiciones operativas de P2 y P3

- **Estado:** Aceptada
- **Fecha:** 2026-11-17
- **Eje de la bitácora (§5 de la propuesta):** Aprendizaje
- **Requisitos relacionados:** ADR-004 (R), ADR-013 (Δ y θ), ADR-026 (curriculum), ADR-027
  (N, E, V, G, σ, k, t)

## Contexto

ADR-027 deja N, E, V, G, σ y k_val para P2 (σ de la red compacta en P2b); ADR-026, la decisión
sobre el curriculum; ADR-013, Δ y θ; ADR-004, la medición de P3 y el cálculo de R. Ningún ADR
define el procedimiento de P2. Este ADR lo fija **antes** de ejecutar ningún entrenamiento piloto.
Lo redactó Claude por delegación expresa del autor (2026-11-17).

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| Búsqueda amplia (N, E, σ, k, t a la vez) | Cómputo fuera del presupuesto de un portátil |
| **σ en rejilla; N, E, V, k, t y k_val fijados a priori; G por estancamiento** | N y E no se optimizan: se justifican por el ruido y el presupuesto |

## Evidencia disponible

- P0b: un episodio de entrenamiento cuesta ~0.2–0.4 s y la aceleración con 16 workers es ~6×.
- Analítica: con semillas comunes por generación (ADR-026), E = 4 ya iguala el ruido entre
  genomas; N = 40 con k = 2 y t = 3 mantiene presión de selección moderada.

## Decisión

**Valores fijados a priori (no se ajustan en P2):** N = 40, E = 4, V = 16, k = 2, t = 3,
k_val = 5. k y t solo cambian si la diversidad (ADR-027) cae por debajo del 10 % de su valor
inicial antes de la mitad de la ejecución en la mayoría de las ejecuciones piloto.

**P2 (red base) y P2b (red compacta):**

- Escenario A; las cuatro redes de ADR-025, cada una frente al oponente por reglas.
- Rejilla σ ∈ {0.02, 0.05, 0.10}, la misma para las cuatro redes (ADR-013); 2 ejecuciones por
  (red, σ); G_piloto = 60 generaciones. Semillas TRAIN con `seed_group` 40–63 (una por red y σ;
  `run` 0 y 1); validación con las semillas VALIDATION fijas.
- **σ** de cada red: el de mayor mediana del F_val final (las 2 ejecuciones); empate → el menor.
- **G**: con la σ elegida, g* = primera generación validada en la que la mediana de F_val alcanza
  el 95 % de su ganancia máxima en el piloto. G = ⌈1.25 · máx(g*)⌉ sobre las cuatro redes,
  redondeado al múltiplo de k_val superior y con mínimo 60. Si alguna red aún mejora al final
  del piloto (g* = 60), G = 75.
- **Curriculum** (ADR-026): se activa si más del 80 % de los genomas de depredador base tienen
  F_train = 0 en las generaciones 0–9 de las ejecuciones con la σ elegida; entonces κ = 2 y
  G_c = ⌈G/2⌉. Si no, κ = 1.
- **F₀, F_base, Δ y θ** (ADR-013), por especie, de la red base en A con la σ elegida: F₀ = mediana
  del F_val de la generación 0; F_base = mediana del F_val final; ganancia = F_base − F₀;
  Δ = 0.10 · ganancia; θ = F₀ + 0.9 · ganancia.

**P3 (ADR-004):** con los valores finales, una ejecución completa de cada una de las 8
configuraciones (2 especies × 3 escenarios con la red base y las 2 compactas en A), con el número
de workers elegido y en carga sostenida (≥ 30 min en total). t_run = duración de cada una; margen
m = 30 %; H = horas disponibles que declara el autor; R = mín(R_max, 10) según ADR-004. Las
ejecuciones de P3 usan `seed_group` 64–71 y no forman parte de los experimentos formales.

Todos los valores elegidos se registran en `results/pilots/p2/p2_decision.json` y en
`docs/pilot_report.md` antes de F7 (`protocol-v1`).

## Consecuencias

- El costo de P2 + P2b es de 24 ejecuciones cortas (~2–3 h con 16 workers según P0b).
- N y E no se optimizan; su elección se declara como limitación.

## Verificación

`neuroeco pilot p2` y `neuroeco pilot p2-decide` reproducen los valores a partir de las
ejecuciones guardadas; F7 los fija en el protocolo.
