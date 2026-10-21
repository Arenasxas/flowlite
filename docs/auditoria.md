# Auditoría de FlowLite (PC) — 2026-10-20

Qué se revisó, cómo y con qué resultado. "Real" = con Groq/Gemini de verdad; "simulado" = con respuestas de prueba.

## Pruebas automáticas (todas en verde)
| Prueba | Qué cubre | Resultado |
|---|---|---|
| `tests/test_logic.py` | teclas (mantener, 2 y 3 toques, abortar), detección de Meet/Zoom/Teams, atajos de voz, aprender correcciones, filtro de eco de Whisper, cuaderno (todas las piezas), limpieza de LaTeX, bloques sin cerrar, rutas de capturas | OK |
| `tests/test_notes.py` | grabación real de la PC → tramos → reintento si se corta internet → apuntes (Groq y Gemini simulados) → rehacer | OK |
| `tests/test_paths.py` | imágenes del resumen para el parcial (no sale de la carpeta) | OK |
| `tests/test_f2.py` | tipos de apunte, detección de llamadas por micrófono, revisión de completitud, continuación de Gemini, PDF, clase sin terminar | OK |
| `tests/test_panel.py` | panel con datos de ejemplo: historial, búsqueda, filtro, vocabulario, atajos, reintentar | OK |
| `tests/test_main.py` | el programa entero (teclado y bandeja simulados): bolita → panel, cambiar la tecla a F9, dictado al historial, aviso de Meet | OK |
| `tests/test_gui.py` | diálogo de inicio, ventana de clase, bolita violeta | OK |
| `tests/test_panel_screen.py` | **capturas de la pantalla real**: 5 secciones ida y vuelta sin restos, búsqueda, preguntar, materias, reintentar, Ajustes desplazado, panel dentro de la pantalla, Esc, los 3 avisos, diálogo con Tipo | OK (capturas revisadas una por una) |

## Pruebas reales
| Prueba | Resultado |
|---|---|
| Dictado (`test_real_groq.py`) | "eh bueno mañana a las cinco no a las seis…" → "Mañana a las seis paso por tu casa. ¿Vos podés traer el apunte de costos?" en ~1,3 s. Modo comando OK. |
| Apuntes de una mini clase con diapositiva (`test_real_notes.py`) | Gemini 62 s, Groq 11 s. Gemini lee la diapositiva. |
| Asistente (`test_real_assist.py`) | ¿Qué me perdí? 2 s · pregunta para el profe 0,5 s · Preguntale a tus clases encontró el 37,5 % de la diapositiva · resumen para el parcial con 4 fichas · título automático. |
| **Clase real larga** (`test_real_long.py`, transcripción de Wispr Flow de Estadística, 47 min, 31 datos que dio el profe) | **Wispr Flow: 22/31** (374 palabras) · **FlowLite antes: 30/31** (2132 palabras) · **FlowLite con la revisión: 31/31** (3609 palabras, 6 fichas de fórmula, 7 preguntas, recuadros "ojo" con los errores comunes que marcó el profe) · 2 min · PDF generado. |

## Defectos encontrados y arreglados
1. **Una clase cortada quedaba sin apuntes** (pasó con Estadística el 16/10): ahora, al abrir FlowLite, aparece el aviso "Quedó una clase sin terminar → Armar apuntes".
2. **Salir durante una clase** esperaba solo 2 s y se perdía el final: ahora espera a que termine de transcribir y arme los apuntes (hasta 2 min).
3. **"¿Qué me perdí?" y "Preguntale a tus clases" mostraban LaTeX** (`\text{…}`, `\(500 \times 500\)`): ahora se limpian igual que los apuntes, y la limpieza reconoce `\( \)` y `\[ \]`.
4. **`generic_title` reconocía "clasedeprueba"** (resto de pruebas): sacado; ahora "Llamada de WhatsApp" también cuenta como título genérico y se reemplaza por uno sacado de la conversación.
5. **Clases largas en "Muy detallado"** podían cortarse a los 16 000 tokens: ahora 32 000, y si Gemini igual se corta, le pide que siga desde ahí.
6. **El PDF con Edge no respondía** cuando Edge tiene una actualización pendiente (pasaba en esta PC): ahora prueba Chrome y después Edge, cada uno con un perfil temporal propio.
7. **Autocorrección del dictado a veces no se aplicaba**: Whisper escribe "a las 5 no a las 6" sin comas y el pulido
   lo dejaba igual (1 de 3 veces). La regla de `polish` en `shared/prompts.json` ahora lo aclara con un ejemplo: 8 de 8 casos bien,
   sin tocar las negaciones reales ("no voy a poder ir", "el de costos, no el de estadística").

## Comportamientos revisados que están bien
- Ctrl+Alt+número (que en teclados en español escribe # o @) se reconoce como atajo de otra app y no graba (se ve en `flowlite.log`).
- Wispr Flow y FlowLite no cuentan como "llamada" aunque usen el micrófono.
- Discord se usa también para jugar: el aviso de llamada sale una sola vez por sesión y se apaga en Ajustes.

## Celular
| Prueba | Resultado |
|---|---|
| Paridad del cuaderno JS ↔ Python (`tests/parity.mjs`, 17 apuntes reales) | Idéntico byte por byte |
| Recorrido completo con Groq, Gemini y Drive simulados (`tests/mock_server.mjs`) | Claves, Drive (clase de la PC con imagen), grabación en vivo con audio, ⭐ ❓ 📸, ayuda, pausa, apuntes con revisión, visor, subida a Drive en el formato de la PC, preguntar, resumen, repasar y dictar |
| IA del celular con claves reales (`tests/test_real_mobile_ai.mjs`) | Transcripción, pulido, "¿Qué me perdí?", apuntes de la clase de prueba (7 de 7 datos clave, título automático, sin LaTeX) y preguntar |
| App publicada | https://arenasxas.github.io/flowlite/ responde (200), con `shared/` adentro |
| APK de Android | Compila en GitHub, pasa lint y queda firmado (huella SHA-1 64:45:E3…, igual a la del certificado creado) y publicado en Releases |
| Atajo de iPhone | Los dos pedidos a Groq de la guía, probados desde la PC con la clave real |

## Sin verificar de mi lado
- **Todo lo que necesita un teléfono real:** instalar el APK, el teclado de Android, grabar el audio del celular, la cámara, Drive desde Android,
  la app en iPhone y el Atajo. Ver los checklists de `docs/GUIA.md` y `docs/iphone-atajo.md`.
- La sincronización con un Drive real: falta crear el ID de cliente de Google (paso del usuario, en `docs/GUIA.md`).
- Una llamada real de WhatsApp/Discord (la detección se probó con el registro de Windows simulado y leyendo el real).
- Google Drive para escritorio (no está instalado en esta PC): la detección de la carpeta `Mi unidad` está programada pero no se pudo probar.
