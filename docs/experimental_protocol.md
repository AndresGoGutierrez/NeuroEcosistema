# Protocolo experimental (F7)

Protocolo prerregistrado de los experimentos formales (F8). Se fija antes de entrenar ninguna
ejecución formal; los valores salen de los pilotos (`docs/pilot_report.md`) y de los ADR citados.
Archivo ejecutable: `configs/protocol.yaml`.

## Diseño

| Elemento | Valor | Fuente |
|---|---|---|
| Configuraciones | prey_base y predator_base en A, B y C; prey_compact y predator_compact en A (8) | ADR-013 |
| Ejecuciones por configuración | R = 10 | ADR-004, P3 |
| Semillas | grupos 100–107 (una por configuración), `run` = 0–9; VALIDATION y TEST comunes a todas las condiciones | ADR-028 |
| Algoritmo genético | N = 40, élite k = 2 con reevaluación, torneo t = 3, mutación gaussiana σ = 0.10, sin cruce | ADR-027, P2 |
| Evaluación en entrenamiento | E = 4 episodios por genoma | ADR-035 |
| Generaciones | G = 70; validación cada k_val = 5 generaciones con V = 16 episodios | ADR-035, P2 |
| Currículo | solo depredador: κ = 2 durante G_c = 35 generaciones | ADR-026, P2 |
| Selección del modelo | máximo F_val en validación; ante empate, la generación más temprana | ADR-027 |
| Prueba | 50 episodios TEST por (modelo, oponente) | este protocolo |
| Oponentes | M0 reglas; M1/M2 variantes de reglas; M3 aleatorio; M4 juego cruzado entre redes base | ADR-019 |

El orden de entrenamiento recorre el índice de ejecución primero (las 8 configuraciones de la
ejecución 0, luego las de la 1, …), para que una parada anticipada deje un diseño balanceado.

## Hipótesis y análisis

Métrica primaria: supervivencia media de las presas (presa) y fracción capturada (depredador),
ADR-014. Unidad experimental: la ejecución (ADR-017).

- **C1** (antes/después de entrenar, redes base, frente a M0): d_r = después − antes.
- **C3** (red entrenada frente a reglas, frente a M0): d_r = red − reglas.
  Para C1 y C3: mediana con intervalo exacto por signos, prueba de signos exacta y Holm con
  m = 6 por familia (R = 10 ≥ 8, confirmatorio); Hodges-Lehmann y Wilcoxon como sensibilidad.
- **C2** (compacta frente a base, escenario A): desplazamiento de Hodges-Lehmann con intervalo
  exacto y regla de no inferioridad con margen Δ (presa 0.0104, depredador 0.0843); eficiencia
  como generaciones hasta θ (presa 0.279, depredador 0.758) por permutación exacta, Holm m = 2
  (ADR-013, P2).
- **Generalización**: Adv(O) = red − reglas frente a M0–M4, solo estimación (ADR-019).

## Ejecución

```
uv run neuroeco experiment train --stop-at AAAA-MM-DDTHH:MM   # reanudable
uv run neuroeco experiment evaluate
uv run neuroeco experiment analyze
```

`train` conserva las ejecuciones completas y renombra una incompleta a `.incomplete-<UTC>`
antes de repetirla con las mismas semillas. `evaluate` nunca sobrescribe una evaluación.

## Ensayo

El ensayo en miniatura (`tests/integration/test_experiment.py`) recorre entrenamiento con
parada y reanudación, evaluación TEST y análisis completo (tablas y figuras) con el protocolo
reducido (R = 2, G = 2). Con R < 8 el análisis informa solo estimación, como está previsto.

## Desviaciones

Cualquier cambio respecto a este protocolo después de iniciar F8 se registra aquí con su fecha
y motivo.
