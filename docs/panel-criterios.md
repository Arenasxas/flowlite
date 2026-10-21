# Panel de FlowLite: criterios de terminado

Se verifica con **capturas de la pantalla real** (`tests/test_panel_screen.py`), no con `widget.grab()`:
`grab()` dibuja en una imagen aparte y no muestra los restos de pintura que sí ve el usuario.

## Ventana
1. Fondo opaco, esquinas redondeadas y sombra **de Windows** (DWM). Nada de `WA_TranslucentBackground`
   ni `QGraphicsDropShadowEffect` en el panel ni en el aviso: con eso Qt deja restos de la sección anterior.
2. Cambiar de sección ida y vuelta (Historial → Apuntes → Personal → Ajustes → Historial) no deja
   ningún resto: cada captura muestra solo su sección.
3. Solo el botón de la sección activa está resaltado en la barra lateral.
4. Se abre cerca de la bolita sin salirse de la pantalla; Esc o ✕ lo cierran; se arrastra desde el título.

## Historial
5. Tarjetas de estadísticas con número y texto completos (nada cortado).
6. Cada dictado es una tarjeta del ancho completo: hora, estado de color, app, texto con salto de línea,
   botones Copiar y borrar a la derecha. Encabezados "Hoy" / "Ayer" / fecha.
7. Buscar y filtrar recalculan la lista sin parpadeos ni restos.

## Apuntes
8. Tarjeta principal con título, explicación y botón; lista de clases a ancho completo con Abrir / Rehacer / carpeta.

## Personal
9. Etiquetas del vocabulario completas y en varias filas si hace falta; tabla de atajos legible.

## Ajustes
10. Cada fila: título + explicación a la izquierda, control alineado a la derecha; interruptores y
    desplegables con flecha visible; la página se desplaza sin restos.

## Aviso de clase o llamada
11. Tarjeta redondeada abajo a la derecha, texto completo, botones visibles, entra con animación,
    sin restos al aparecer ni al irse.

## Funcional
12. Los cambios de Ajustes se aplican al instante (tecla, bolita, idioma) y el historial se
    actualiza solo con un dictado nuevo (`tests/test_main.py`).

## Estado (2026-10-18, v2.1)
Todos los puntos verificados con `tests/test_panel_screen.py` en pantalla real (1536×816):
- 1–3: sin `WA_TranslucentBackground` ni sombra de Qt; esquinas y borde de Windows (`native_round`).
  Los contenedores usan `paper()` (fondo pintado). Ida y vuelta entre secciones sin restos.
- 5–7: `Column` en vez de QListWidget; las filas viejas se sacan con hide + setParent(None),
  porque con deleteLater solo se acumulaban (12 → 16 → 20 filas vivas).
- 4: con la bolita en la esquina inferior derecha, el panel queda adentro de la pantalla; Esc lo cierra.
- 10: Ajustes se desplaza hasta abajo y vuelve sin restos. 11: aviso redondeado con borde violeta.
- 12: `tests/test_main.py` (main completo con teclado y bandeja simulados).

## Agregado v2.2 (tomado de Wispr Flow y mejorado)
13. Historial: dictado fallido muestra "↻ Reintentar" (audio guardado en pendientes/), al reintentar queda copiado.
14. Estadísticas: palabras hoy, velocidad (ppm), racha de días, tiempo ahorrado.
15. Apuntes: "Preguntale a tus clases" con respuesta citada; chips por materia; "Resumen para el parcial".
16. Notas rápidas: se guarda sola.
17. Ventana de clase: "✨ Ayuda" (¿qué me perdí? / pregunta para el profe) en una cajita legible.
