# ADR-032: Implementación estadística y protocolo de cobertura (F3)

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Eje de la bitácora:** Diseño experimental / Ingeniería y reproducibilidad
- **Requisitos relacionados:** §6 (comparaciones obligatorias; conclusiones coherentes con los
  datos), §9 (reproducibilidad)

## Contexto

ADR-013, ADR-014 y ADR-017 fijan los métodos estadísticos. ADR-024 exige para cerrar F3 sus
pruebas en verde, "incluidas las lentas de cobertura", sin precisar cuáles. Hacen falta además
decisiones de implementación (aritmética, remuestreos, cuantiles) y un protocolo de cobertura
fijado **antes** de ejecutarlo, para que ningún umbral se elija después de ver los resultados.
Este ADR no modifica ADR-013, ADR-014 ni ADR-017.

## Alternativas consideradas

| Tema | Alternativas | Elegida |
|---|---|---|
| Métodos exactos | scipy en todos los casos / implementación propia contrastada con scipy | Propia, contrastada con scipy y con enumeraciones ingenuas en las pruebas |
| Aritmética | Flotantes / numeradores enteros y fracciones exactas | Enteros y `fractions.Fraction` |
| Cobertura | Sin pruebas / Monte Carlo con umbral libre / Monte Carlo con protocolo previo | Protocolo previo con umbral L − 3·SE |
| BCa del δ de Cliff (id 41) | N = 10 000 en CI (≈ 7 min por sistema y push) / fuera de CI / N = 2000 en CI | N = 2000 en CI (solo informativa) |

## Evidencia disponible

- Analítica: niveles exactos por enumeración de Bin(n, ½), de la distribución nula de T⁺ de
  Wilcoxon y de la de U de Mann-Whitney (tabla del protocolo). Coinciden con ADR-017 (IC por
  signos) y ADR-013 ([D₍₆₎, D₍₃₁₎] al 443/462 = 95.9 %).
- Garantías: el IC por signos cubre cualquier mediana con probabilidad ≥ L para cualquier
  distribución, continua o discreta (intervalo cerrado); los IC de Hodges-Lehmann por inversión
  de Wilcoxon (una muestra, distribución continua simétrica) y de Mann-Whitney (dos muestras,
  modelo de desplazamiento continuo) tienen cobertura exactamente L.
- Empírica (portátil del autor): un IC BCa con 9999 remuestreos cuesta 3.2 ms para la media de
  50 diferencias y unos 40 ms para el δ de Cliff de 50 contra 50 (con rangos medios; 134 ms con
  pares). Con N = 10 000 el id 41 costaría unos 7 minutos por sistema en cada push.

## Criterio de selección

Exactitud verificable, independencia de cambios de comportamiento de scipy en los métodos
exactos, y un protocolo de cobertura con garantía teórica en las pruebas que deciden.

## Decisión

**S1. Alcance de ADR-014 en F3.** Sus componentes estadísticos: IC BCa de la diferencia media
pareada, desviación estándar e IQR. Las métricas de ADR-014 ya se verificaron en F1.

**S2. Precedencia.** Se implementa lo que fijan los ADR aprobados: prueba de signo exacta sin
condicionar y por escenario (ADR-017); sin rank-biserial. Las propuestas anteriores de la ronda
de diseño B4.4 quedan sustituidas.

**S3. δ de Cliff con IC BCa sin emparejar** (necesario para ADR-020 A6 en F4).

**S4. Protocolo de cobertura** (abajo).

**S5. Aritmética.** Las métricas por ejecución entran como numeradores enteros; los p-valores
exactos son `fractions.Fraction`; Holm opera con fracciones exactas. Solo el bootstrap usa
flotantes.

**S6. Bootstrap.** `scipy.stats.bootstrap`, método BCa, 9999 remuestreos por defecto
(configurable), nivel del 95 %; el generador lo proporciona quien llama. Con datos degenerados
el resultado es "no estimable", sin excepción.

**S7. Variabilidad.** Desviación estándar con `ddof=1`; IQR con cuantiles lineales de NumPy
(método 7 de Hyndman-Fan).

**S8. Eficiencia de C2.** θ y G_θ en F3; el área bajo la curva de validación, en F6.

**S9.** Estas decisiones se registran en este ADR.

**Definiciones de implementación** (concretan ADR-013 y ADR-017 sin cambiarlos):

- Elección de k en los IC exactos: el mayor k con nivel alcanzado ≥ 95 % (intervalo más corto
  que cumple el 95 %); se reporta el nivel alcanzado.
  - Mediana por signos: [d₍ₖ₎, d₍ₙ₋ₖ₊₁₎], nivel 1 − 2·P(B ≤ k − 1), B ~ Bin(n, ½).
  - Hodges-Lehmann de una muestra: mediana de las M = n(n+1)/2 medias de Walsh; IC
    [W₍ₖ₎, W₍ₘ₋ₖ₊₁₎] con k de la distribución nula exacta de T⁺ sin empates.
  - Hodges-Lehmann de dos muestras: mediana de las mn diferencias tratamiento − referencia; IC
    [D₍ₖ₎, D₍ₘₙ₋ₖ₊₁₎] con k de la distribución nula exacta de U sin empates.
- p bilateral de las pruebas de permutación (Wilcoxon de rangos con signo y suma de rangos de
  dos muestras, con rangos medios como enteros duplicados): proporción de las permutaciones
  equiprobables con |T − E[T]| ≥ |t_obs − E[T]|. Sin empates coincide con 2·mín de las colas.
- δ de Cliff: δ(a, b) = (#{a > b} − #{a < b}) / (n_a·n_b) = 2U/(n_a·n_b) − 1 con
  U = #{a > b} + ½·#{a = b}.
- Regla de no inferioridad (ADR-013), en este orden y con desigualdades estrictas: L > 0
  superior; L > −Δ no inferior; U < −Δ inferior; en otro caso no concluyente.
- Aviso de modelo de desplazamiento: razón entre el IQR mayor y el menor > 2; si un IQR es 0 y
  el otro no, hay aviso; si ambos son 0, no.
- Límites de las enumeraciones exactas: una muestra n ≤ 12; dos muestras n₁ + n₂ ≤ 20.

### Protocolo de cobertura Monte Carlo

**Reglas comunes.**

- Un intervalo cubre el valor verdadero cuando L ≤ valor ≤ U (intervalo cerrado).
- Error estándar de Monte Carlo: SE = √(L·(1 − L)/N), con L el nivel alcanzado.
- Umbral de aceptación de las pruebas confirmatorias: cobertura ≥ L − 3·SE.
- Semilla de cada configuración: `numpy.random.SeedSequence(entropy=(32, id))`, con `id` el
  número de fila de las tablas.
- Pruebas con la marca `slow`, ejecutadas en el CI de Ubuntu y Windows.
- **Solo las configuraciones confirmatorias determinan la aceptación de F3.** Las informativas
  reportan su cobertura observada y su SE y no pueden usarse para decidir el cierre.
- Semillas, distribuciones, tamaños, niveles, N y umbrales no se cambian después de ejecutar
  las pruebas.

**Confirmatorias** (N = 10 000; umbral L − 3·SE):

| id | Método | Distribución generadora | Valor verdadero | n | Nivel L | Umbral |
|---|---|---|---|---|---|---|
| 1–5 | IC por signos | Normal(0.4, 1), continua simétrica | Mediana 0.4 | 6…10 | 31/32; 63/64; 127/128; 123/128; 501/512 | 0.9635; 0.9807; 0.9896; 0.9551; 0.9742 |
| 6–10 | IC por signos | Exponencial(1), continua asimétrica | Mediana ln 2 | 6…10 | Igual | Igual |
| 11–15 | IC por signos | round(Normal(0.3, 2)), discreta con muchos ceros (mediana única: P(d ≤ 0) = 0.540, P(d ≥ 0) = 0.655) | Mediana 0 | 6…10 | Igual | Igual |
| 16–20 | IC por signos | Poisson(3) − 3, discreta asimétrica (0.647 y 0.577) | Mediana 0 | 6…10 | Igual | Igual |
| 21–25 | Hodges-Lehmann de una muestra | Normal(0.5, 1) | Centro 0.5 | 6…10 | 0.9688; 0.9531; 0.9609; 0.9609; 0.9512 | 0.9635; 0.9468; 0.9551; 0.9551; 0.9447 |
| 26–30 | Hodges-Lehmann de una muestra | Laplace(0.5, 1), colas pesadas | Centro 0.5 | 6…10 | Igual | Igual |
| 31 | Hodges-Lehmann de dos muestras | X ~ Normal(0, 1), Y = X′ + 0.7 | Δ = 0.7 | 6×6 | 443/462 | 0.9529 |
| 32 | Hodges-Lehmann de dos muestras | X ~ Exponencial(1), Y = X′ + 0.7 | Δ = 0.7 | 6×6 | 443/462 | 0.9529 |

Los niveles de Hodges-Lehmann de una muestra son, exactamente, 1 − 2·P(T⁺ ≤ k − 1): n = 6 (k = 1),
1 − 2·1/64; n = 7 (k = 3), 1 − 2·3/128; n = 8 (k = 4), 1 − 2·5/256; n = 9 (k = 6), 1 − 2·10/512;
n = 10 (k = 9), 1 − 2·25/1024.

**Informativas** (se reporta la cobertura ± SE; no deciden el cierre):

| id | Método | Distribución | Valor verdadero | N |
|---|---|---|---|---|
| 33–37 | Hodges-Lehmann de una muestra, datos discretos | Uniforme{−2, …, 4}, simétrica respecto de 1, con empates; n = 6…10 | 1 | 10 000 |
| 38 | Hodges-Lehmann de dos muestras, datos discretos | Poisson(3) frente a Poisson(3) + 1, 6×6 | Δ = 1 | 10 000 |
| 39 | BCa de la media pareada | Normal(0.3, 1), n = 50 | 0.3 | 10 000 |
| 40 | BCa de la media pareada | Exponencial(1) − 0.7, n = 50 | 0.3 | 10 000 |
| 41 | BCa del δ de Cliff, 50×50 | Normal(0, 1) frente a Normal(0.5, 1) | δ = 2Φ(0.5/√2) − 1 ≈ 0.2763 | **2 000** |

**Id 41.** Usa N = 2 000 por viabilidad computacional (≈ 80 s en el portátil del autor frente a
≈ 7 minutos con N = 10 000, en cada sistema y en cada push). Su SE con cobertura cercana al
95 % es ≈ 0.005. El cambio afecta solo al número de réplicas de Monte Carlo: no altera el nivel
de confianza (95 %), el número de remuestreos (9999) ni ningún otro parámetro del estimador. Es
exclusivamente informativa.

## Consecuencias

- Los p-valores exactos se comparan por igualdad (2/256, 18/256, 22/1024, 112/1024).
- Las pruebas de cobertura alargan el CI unos minutos.
- Las semillas del bootstrap en los análisis formales se derivarán en F8 (`analysis` no puede
  importar `application`, donde vive `SeedRegistry`).

## Verificación

F3: pruebas de T1–T7 (`tests/unit/analysis/`, `tests/stats/`); resultados de cobertura por
configuración registrados en `docs/phase_gates.md`.
