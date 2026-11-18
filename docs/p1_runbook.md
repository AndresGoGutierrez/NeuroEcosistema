# Guía de operación de la calibración P1 (T5)

Procedimiento de cada paso real de P1 (ADR-033, P1-18 y P1-19). Los formatos y las
comprobaciones están en [p1_data_dictionary.md](p1_data_dictionary.md); las decisiones, en
[phase_gates.md](phase_gates.md).

## Antes de la primera iteración (T5-0, una sola vez)

1. Árbol limpio en `main`, sincronizado con `origin/main` y con el CI del último commit en verde
   en Ubuntu y Windows.
2. Pausar las actualizaciones del sistema operativo durante toda P1 (D-T4d-2): la versión del
   sistema forma parte de la huella del entorno y un cambio es STOP.
3. `configs/pilots/p1.yaml` es la tabla aprobada (la prueba `test_p1_spec_loader` lo fija).
4. `uv run neuroeco pilot p1-reserve` escribe `results/pilots/p1/RESERVED.json` con las huellas
   de referencia; commit y push. Desde ese momento ningún archivo de `src/` ni `uv.lock` puede
   cambiar hasta el congelamiento: cualquier cambio es STOP.
5. Todo P1 se ejecuta en esta misma máquina, desde la raíz del repositorio y con las rutas
   canónicas.

## Cada paso

| # | Paso | Quién | Comando o acción |
|---|---|---|---|
| 1 | Proponer el paso: tipo (iteración, ronda, entrada, confirmación), parámetro, magnitud y motivo con referencia al resultado anterior | Claude propone; **el autor decide** | — |
| 2 | Registrar la especificación (`configs/pilots/p1/iterations/NNN.yaml` o `rounds/RR.yaml`) y, si la puerta la exige, la decisión del autor (`configs/pilots/p1_decisions/NNN.yaml`) | Claude redacta; **el autor la aprueba** | — |
| 3 | Commit y push del registro (P1-19: anterioridad pública) | Claude, con la autorización del autor | `git commit`, `git push` |
| 4 | Si el commit solo añade registros, decisiones o resultados (sin código ni pruebas), no se espera el CI: P1-19 exige anterioridad pública y la puerta exige HEAD = origin. Esos commits llevan `[skip ci]`. Un commit con código o pruebas sí espera su CI en verde | Automático | — |
| 5 | Ejecutar el bloque | Claude | `uv run neuroeco pilot p1 --iteration configs/pilots/p1/iterations/NNN.yaml` (o `--round … --phase …`, `--entry-evaluation --values-from …`) |
| 6 | Evaluar los criterios | Claude | `uv run neuroeco pilot p1-criteria --result results/pilots/p1/calibration/…` |
| 7 | Verificar la secuencia | Claude | `uv run neuroeco pilot p1-sequence` |
| 8 | Revisar resultados, procedencia (A2, huellas, `sequence_gate`) y redactar la entrada de `pilot_report.md` | Claude informa; **el autor revisa** | — |
| 9 | Commit y push de resultados, criterios y entrada del informe; esperar el CI | Claude, con el visto bueno del autor | `git commit`, `git push` |
| 10 | Autorizar el paso siguiente | **El autor** | — |

Dentro de un paso autorizado, los puntos 4 a 7 continúan sin intervención (desde la iteración 7, a petición del autor, sin esperar el CI de los commits de solo datos). Las rondas se
ejecutan en sus tres fases (`prey`, `predator` y, si cambió algún valor, `reevaluation`), cada
una con sus pasos 5 a 9; las rejillas no tienen criterios (paso 6 solo para A_rev).

## Cuándo se detiene todo

El proceso se detiene y espera la decisión del autor ante:

- cualquier STOP de la puerta o de `pilot p1-sequence` (presupuesto agotado, violación A2,
  `InitializationError`, intento sin registro reconocible, huella distinta, decisión modificada,
  entrada fallida);
- un veredicto `author_confirmation_required` (vía E5 de D9: hace falta una decisión `d9_e5`) o
  `author_authorization_required` (la entrada cumplió la clase A: la confirmación necesita la
  revisión `entry_review` y `--author-authorized`);
- criterios B incumplidos con S_X cumplido (hace falta una decisión `b_criteria`);
- cualquier rechazo inesperado de `pilot p1` o `pilot p1-criteria`.

Ningún STOP se levanta desde la herramienta: requiere un procedimiento aprobado por el autor
(D-T4d-1).

## Recuperación de un directorio parcial

Ver "Recuperación de un directorio parcial" en el diccionario de datos (D18): nunca se borra un
`failure.json` ni se escribe uno a mano.
