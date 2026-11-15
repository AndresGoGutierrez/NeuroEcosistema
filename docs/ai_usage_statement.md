# Declaración de uso de IA generativa

La propuesta académica (§8) exige declarar qué herramientas de IA generativa se usaron, para
qué, qué recomendaciones se aceptaron o rechazaron y qué validaciones se hicieron. Este archivo
se mantiene como registro durante todo el proyecto; la versión resumida irá en el informe (F9).

## Herramientas

| Herramienta | Uso |
|---|---|
| Claude Code (modelo Claude Opus 5.5, Anthropic) | Análisis de la propuesta, diseño de arquitectura y metodología, redacción de ADR, andamiaje del repositorio, implementación y pruebas del núcleo de simulación (F1), piloto P0, visor e inspector (F2) |

## Registro

### 2026-11-15: análisis y diseño (antes de F0)

**Uso:** análisis de la propuesta académica; propuesta de arquitectura, diseño de redes,
algoritmo de entrenamiento, metodología experimental y estadística; cinco rondas de revisión.

**Recomendaciones corregidas o rechazadas a partir de la revisión del autor:**

| Propuesta inicial de la IA | Problema señalado por el autor | Resolución |
|---|---|---|
| `spawn_key=(1, r, "evo")` | `SeedSequence` solo admite enteros no negativos | Claves de 6 enteros (ADR-028) |
| Sensores (p, sin φ, cos φ) | Discontinuidad en el borde de la visión | (p, p·sin φ, p·cos φ) (ADR-007) |
| Variables de entorno de BLAS antes de crear el pool | No tienen efecto si NumPy ya se importó | threadpoolctl + `spawn` + verificación (ADR-016) |
| `N(0, 1/fan_in)` sin precisar | Ambigüedad entre varianza y desviación estándar | Varianza 1/fan_in y prueba I1 (ADR-018) |
| R = 6 presentado como suficiente | No garantiza potencia | Regla de P3 y limitaciones explícitas (ADR-004) |
| Prueba de signo agrupando A, B y C | Posible pseudorreplicación y ocultamiento de efectos | Análisis por escenario (ADR-017) |
| Umbrales fijos δ ≥ 0.33 en P1 | Forzarían parámetros por ruido muestral | Criterios en clases A/B/C (ADR-020) |
| "Con R = 10 se admiten dos rangos negativos" | El p depende de los rangos, no del número de negativos | Decisión por p exacto y Holm (ADR-017) |
| Cobertura del IC por signos con n = 7 del 99.2 % | Error de cálculo | 98.4 % (ADR-017) |
| Prueba de signo excluyendo ceros para H₀: mediana = 0 | No contrasta la mediana con datos discretos | Prueba sin condicionar, dual con el IC (ADR-017) |

**Errores detectados por la propia IA durante las revisiones:** Holm con R = 6 hacía imposibles
los rechazos en C1/C3; Kaplan-Meier ignoraba el riesgo competitivo de inanición; errores de
dependencia en el plan de fases; empates en G_θ.

**Validaciones:** revisión crítica del autor en cada ronda; verificación de los cálculos
combinatorios y binomiales.

### 2026-11-15: F0 (andamiaje del repositorio)

**Uso:** generación de `pyproject.toml`, configuración de ruff, pytest e import-linter, pruebas
de arquitectura, CI, README y ADR.

**Validaciones:** `ruff`, `lint-imports` y `pytest` ejecutados localmente; los contratos de
arquitectura se comprobaron inyectando importaciones prohibidas en el dominio (los tres
mecanismos fallaron como se esperaba). Durante esa comprobación se detectó y corrigió que la
prueba AST fallaba con archivos guardados con BOM.

### 2026-11-15: F1 (núcleo de simulación y piloto P0)

**Uso:** propuesta del plan de tareas de F1; implementación del dominio (parámetros, geometría,
estado, reglas, interacciones, sensores, políticas, simulador), de los casos de uso (semillas,
métricas, evaluación), del cargador de configuraciones y de la CLI; pruebas unitarias, de
integración y de determinismo; comando y análisis del piloto P0; redacción del informe de P0.

**Recomendaciones corregidas o rechazadas a partir de la revisión del autor:**

| Propuesta de la IA | Observación del autor | Resolución |
|---|---|---|
| Referencia de P0: escenario C provisional (25 presas, 8 depredadores) | No es necesariamente el peor caso; la rejilla llega a 50 presas | Referencia 50/8 (A4), mantenida tras conocer los resultados |
| Aplicar O1–O4 dentro de F1 antes de cerrar | Sin cambios de comportamiento ni ampliaciones de alcance en el cierre | F1 se cierra por la alternativa "plan de optimización"; O1 y O4 antes de P0b (F6) |

**Errores detectados por la propia IA:**

- Prueba de un límite de K1 escrita con un literal que dependía del redondeo binario.
- Expectativa de paso de muerte por inanición que suponía aritmética exacta.
- Una aserción de las métricas que fallaría con valores NaN y una aserción de DET-5 que no
  comprobaba nada; se sustituyó por una prueba de que la huella del estado detecta cambios.
- La procedencia de P0 marcaba el árbol como modificado porque se capturaba después de escribir
  los resultados.
- En la revisión pedida por el autor: el informe de P0 afirmaba que O2 no cambiaba ningún
  resultado. Es falso en coma flotante (difieren el 28.2 % de las distancias, en como máximo un ulp); O2 se
  descartó. También se corrigió la redacción del perfil ("la mayor parte del tiempo propio" era
  en realidad un 33 %).

**Validaciones:** `ruff`, `lint-imports` y `pytest` (209 pruebas) antes de cada commit; CI en
Ubuntu y Windows después de cada tarea; pruebas de determinismo DET-1, DET-2 y DET-5;
comprobación numérica independiente de la antisimetría del desplazamiento toroidal; revisión por
el autor del criterio de aceptación de P0.

### 2026-11-15: F2 (visualización)

**Uso:** propuesta del plan de F2 y de las decisiones V1–V9; redacción de ADR-031;
implementación de los fotogramas de sesión, el inspector, el visor pygame, el registro de la
sesión y el comando `view`; pruebas de no interferencia, de correspondencia con la traza y del
registro; capturas de comprobación.

**Decisiones del autor:** aprobó V1–V9 tal como se propusieron. Añadió como condiciones de
aceptación obligatorias que se demostrara por separado que dibujar, pausar, avanzar y
seleccionar no alteran la trayectoria, que las políticas aleatorias conservan sus resultados,
que `view` y `run` coinciden y que el inspector respeta la diferencia entre S_t y S_t+1. Exigió
su verificación visual manual antes del cierre.

**Errores detectados por la propia IA:**

- Una aserción vacía (`... or True`) en una prueba de selección, sustituida por una comprobación
  real antes del commit.
- Dos defectos de formato del panel del inspector, detectados por las pruebas antes del commit.
- En la prueba de no interferencia, una llamada que habría dejado el visor esperando
  indefinidamente al final del episodio; se corrigió antes de ejecutarla en CI.

**Validaciones:** `ruff`, `lint-imports` (4 contratos) y `pytest` (273 pruebas) antes de cada
commit; CI en Ubuntu y Windows después de cada tarea; comprobación de que la prueba de hashes
falla ante una interferencia inyectada y de que el contrato de pygame detecta una importación
prohibida; revisión de capturas; verificación visual del autor en su equipo.

### 2026-11-15: F3 (estadística)

**Uso:** revisión de ADR-013, ADR-014, ADR-017 y ADR-020 para el plan de F3; propuesta de las
decisiones S1–S9 y del protocolo de cobertura; redacción de ADR-032; implementación de
`analysis/stats.py` (datos por ejecución, prueba de signo, IC exactos, Holm, Wilcoxon,
Hodges-Lehmann, permutación de dos muestras, δ de Cliff, reglas de C2, BCa, variabilidad) y de
sus pruebas, incluidas las de cobertura Monte Carlo.

**Recomendaciones corregidas o ajustadas por el autor:**

| Propuesta de la IA | Observación del autor | Resolución |
|---|---|---|
| Protocolo de cobertura descrito solo en términos generales | Exigió documentar antes de ejecutar distribuciones, parámetros, tamaños, semillas, N, fórmula del SE, umbral y qué es confirmatorio | Protocolo completo en ADR-032 antes de la primera ejecución |
| N = 10 000 en todas las configuraciones | La IA detectó, antes de implementar, que el id 41 costaría unos 7 minutos por sistema y push; el autor eligió entre las alternativas | Id 41 con N = 2 000, solo informativo |

**Errores detectados por la propia IA:**

- Dos fracciones de ADR-032 (colas de Hodges-Lehmann para n = 8 y 9) mal transcritas;
  detectadas por enumeración y corregidas antes del commit.
- El plan afirmaba que el paquete `analysis` no existía; se detectó al crear el archivo y se
  conservó el original.
- Una prueba con un cálculo superfluo de scipy y recálculos innecesarios, reescrita antes del
  commit; avisos de pytest por generadores en `parametrize`, corregidos sin cambiar resultados.

**Validaciones:** p-valores exactos comparados por igualdad de fracciones; contraste con scipy
y con enumeraciones ingenuas independientes; dualidad prueba-intervalo; reproducibilidad del
bootstrap; protocolo de cobertura ejecutado sin cambios tras su registro; `ruff`,
`lint-imports` (4 contratos) y `pytest` (438 pruebas) antes de cada commit; CI en Ubuntu y
Windows después de cada tarea.
