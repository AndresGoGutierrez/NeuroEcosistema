# ADR-025: Arquitectura de las redes neuronales

- **Estado:** Aceptada (diseño consolidado)
- **Fecha:** 2026-11-15
- **Eje de la bitácora:** Diseño de las redes
- **Requisitos relacionados:** §3 (redes multicapa), §4 (una arquitectura por especie con al menos dos capas ocultas; entradas, salidas, activaciones y parámetros documentados), §5 (por qué esa cantidad de capas, neuronas, activaciones y salidas)

## Contexto

Cada especie necesita un MLP con al menos dos capas ocultas cuya salida se convierta en la
acción de movimiento. El tamaño de la red afecta a la eficiencia de la neuroevolución.

## Alternativas consideradas

| Aspecto | Alternativas | Elegida |
|---|---|---|
| Anchura base | 8, 16, 32 | **16** (unas 1.5–2 veces el número de entradas) |
| Alternativa para C2 | [32, 32] o [8, 8] | **[8, 8]**: prueba la hipótesis tamaño frente a eficiencia evolutiva |
| Activación oculta | tanh, ReLU | **tanh**: centrada en cero y acotada; sin gradientes no hay problema de desvanecimiento |
| Salidas | Discretas (8 direcciones) o continuas | **Continuas** (giro y aceleración): la velocidad tiene costo cuadrático (ADR-010) |

## Evidencia disponible

Analítica: el algoritmo genético escala mal con la dimensión del genoma; mantener el número de
parámetros bajo reduce el costo de la búsqueda. Empírica: C2 (F8).

## Criterio de selección

Cumplir el mínimo de dos capas ocultas con el menor número de parámetros razonable.

## Decisión

| Modelo | Topología | Parámetros |
|---|---|---|
| Presa base | 10 → 16 → 16 → 2 | 176 + 272 + 34 = **482** |
| Presa compacta (C2) | 10 → 8 → 8 → 2 | 88 + 72 + 18 = **178** |
| Depredador base | 7 → 16 → 16 → 2 | 128 + 272 + 34 = **434** |
| Depredador compacto (C2) | 7 → 8 → 8 → 2 | 64 + 72 + 18 = **154** |

- tanh en capas ocultas y en la salida.
- Salidas: o₀ → Δθ = o₀·ω_max (positivo = giro a la izquierda); o₁ → v = v_max·(o₁ + 1)/2.
- `NetworkSpec` rechaza menos de dos capas ocultas en su construcción.
- Inicialización: ADR-018. Entradas: ADR-007.

## Consecuencias

Las especies tienen modelos diferenciados (entradas, parámetros y fitness distintos), como exige §10.

## Verificación

F5: conteo de parámetros, rechazo de < 2 capas ocultas, la salida decodificada coincide con la
acción aplicada; documentación en `docs/networks.md`.
