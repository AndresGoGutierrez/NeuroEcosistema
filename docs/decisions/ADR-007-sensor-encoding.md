# ADR-007: Codificación de los sensores

- **Estado:** Aceptada
- **Fecha:** 2026-11-15
- **Decisión de diseño:** D7
- **Eje de la bitácora:** Representación del entorno
- **Requisitos relacionados:** §4 (definición documentada de entradas), §5 (qué percibe cada agente; qué variables se excluyeron)

## Contexto

Cada agente percibe objetos cercanos dentro de su radio de visión R_v. La codificación debe
ser continua, egocéntrica y con un número fijo de entradas coherente con la red.

## Alternativas consideradas

| Alternativa | Entradas por objeto | ¿Continua en el borde de la visión? | Valoración |
|---|---|---|---|
| A: (p, sin φ, cos φ) | 3 | No: (sin, cos) salta a (0, 0) al salir del radio | Descartada |
| **B: (p, p·sin φ, p·cos φ)** | 3 | Sí | Elegida |
| C: (p·sin φ, p·cos φ) | 2 | Sí | p queda implícita como norma, difícil de recuperar en la primera capa |
| D: sectores tipo retina | m | Parcial | Más entradas; posible mejora futura |

## Evidencia disponible

Analítica: con la opción A, el salto en el borde se propaga a la preactivación de la primera
capa con magnitud de hasta ‖w‖, y una red puede cambiar de comportamiento bruscamente en ese borde.

## Criterio de selección

Continuidad de las entradas, acceso lineal a la urgencia del estímulo y dimensiones fijas.

## Decisión

Por objeto percibido: `proximity` p = 1 − d/R_v (0 si no se percibe), `left` = p·sin φ y
`forward` = p·cos φ, donde φ es el rumbo relativo a la orientación propia, en (−π, π].
Si d < ε: forward = p, left = 0. Se perciben los K = 2 objetos más cercanos de la especie
relevante; empates por índice menor.

**Presa, 10 entradas:** planta más cercana (3), depredadores 1 y 2 (3 + 3), `energy` = e/E_max.
**Depredador, 7 entradas:** presas 1 y 2 (3 + 3), `energy` = e/E_max.

**Excluidas:** posición y orientación absolutas, velocidad de otros agentes, agentes de la
misma especie, plantas para el depredador, paso de tiempo, recuentos globales.

La dimensión de entrada de cada red se deriva del esquema de sensores (lista ordenada de
nombres con versión); no se configura a mano.

## Consecuencias

- Discontinuidades restantes, inherentes a "los K más cercanos": intercambio de ranuras con
  d₁ = d₂ y desaparición del objetivo al comerse o capturarse. Se documentan.
- Un objeto lejano da una señal de dirección débil (ponderada por la urgencia).

## Verificación

F1: pruebas de rangos, continuidad en el borde, desempate por índice y longitud 10/7.
F5: un modelo con esquema distinto se rechaza al cargarse.
