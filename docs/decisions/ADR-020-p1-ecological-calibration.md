# ADR-020: Criterios de calibración ecológica de los escenarios (P1)

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D20
- **Eje de la bitácora:** Diseño experimental / Representación del entorno
- **Requisitos relacionados:** §6 (tres escenarios con "diferencias medibles")

## Contexto

Los parámetros del entorno se calibran antes de entrenar redes. Criterios demasiado rígidos
(umbrales fijos de tamaño del efecto) obligarían a recalibrar por ruido y a forzar parámetros.

## Alternativas consideradas

| Alternativa | Inconvenientes |
|---|---|
| Umbrales fijos de δ ≥ 0.33 como condiciones obligatorias | Con 30 contra 30 episodios (EE ≈ 0.13–0.15), un δ real de 0.40 fallaría en ~30 % de las calibraciones |
| Calibrar y confirmar con las mismas semillas | Sobreajuste a esas semillas |
| **Tres clases de criterios, sin umbrales de δ, bloque de confirmación independiente** | — |

## Evidencia disponible

Analítica: error estándar aproximado del δ de Cliff con 30 contra 30 episodios.

## Criterio de selección

Validez del simulador sin forzar tamaños del efecto ni p-valores.

## Decisión

**Procedimiento:** solo políticas por reglas, aleatoria y sondas (nunca redes). Calibración en un
bloque PILOT; confirmación en un bloque PILOT nuevo de **50 semillas**, con **un `seed_group`
por escenario** (episodios independientes entre escenarios y pareados dentro de cada uno).
Orden: restricciones analíticas → A → ajuste de la política por reglas (alternando como máximo
3 veces) → B (solo N_plants) → C (solo n_pred). Máximo 5 iteraciones por etapa; si no se
cumplen los criterios, se detiene y se consulta al autor. Un solo intento de confirmación (un
segundo solo tras una recalibración documentada).

**Clase A, obligatorias (bloquean el cierre de F4):**
- A1: restricciones K1–K4, E1, E2 y E5 (ADR-030).
- A2: invariantes en todos los episodios piloto (vivas + capturadas + muertas de hambre = n; 0 < e ≤ E_max; sin capturas en t = 0).
- A3: rango intercuartílico de la métrica primaria > 0.
- A4: alimentación, captura e inanición ocurren donde se esperan.
- A5: supervivencia media de la presa por reglas en [0.05, 0.95].
- A6: diferencias medibles A–B y A–C: el IC 95 % del δ (sin emparejar, BCa) excluye 0 **en la
  dirección esperada** (menor supervivencia en B y en C). Es una afirmación conjuntiva:
  intersección-unión (Berger, 1982), sin Bonferroni, válida con cualquier dependencia. Para
  corregir un fallo solo se ajusta el factor del escenario.

**Clase B, deseables** (si fallan: decisión documentada; recalibrar solo con causa paramétrica
identificable, nunca para alcanzar un tamaño del efecto): B1 supervivencia en [0.20, 0.90];
B2 margen de aprendizaje (reglas > aleatoria, ambas especies); B3 mediana de supervivencia del
depredador ≥ 0.5·T_max; B4 mecanismo de B (más inanición; tasa neta de energía > 0 en A y ≤ 0 en B);
B5 mecanismo de C (mayor incidencia de captura); B6 el depredador necesita ≥ 2 capturas para
llegar a T_max; B7 margen de reacción K5.

**Clase C, alertas** (se investigan y documentan): C1 una sonda iguala o supera a la política
por reglas; C2 más del 10 % de las capturas en el primer 5 % de T_max; C3 mediana de duración
< 0.25·T_max; C4 en A, más del 90 % de las muertes por inanición o casi sin capturas.

**Cierre de F4:** clase A completa en la confirmación; cada B cumplido o aceptado mediante ADR;
cada C investigado y documentado. Configuración congelada con la etiqueta `env-frozen-v1`.

## Consecuencias

El entorno nunca se ajusta en función del rendimiento de las redes.

## Verificación

F4: `docs/pilot_report.md` (sección P1) con todas las iteraciones y el resultado de la confirmación.
