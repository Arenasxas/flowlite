# FlowLite: guía para seguir el desarrollo

Esta guía es para quien sigue el proyecto sin haber visto cómo se hizo. Explica qué hace cada parte, dónde está en el código,
cómo compilar y probar, por qué se decidió cada cosa y qué pasos tiene que hacer una persona a mano.

## 1. Qué es

FlowLite tiene dos funciones:
- **Dictado:** mantenés una tecla, hablás y el texto pulido aparece donde está el cursor, en cualquier programa.
- **Apuntes:** graba una clase, reunión o llamada. La transcribe en vivo y al final arma un cuaderno de estudio,
  con resumen, fichas de fórmulas, preguntas de autoevaluación, tareas y capturas.

| Parte | Carpeta | Tecnología |
|---|---|---|
| PC (Windows) | raíz: `flowlite.py`, `panel.py`, `build.py` | Python 3.11 + PySide6, compilado con PyInstaller |
| Celular (Android y iPhone) | `mobile/` | App web instalable (HTML + JS sin compilación), en GitHub Pages |
| Android nativo | `android/` | Kotlin: WebView de la app web + teclado + audio del celular |
| Compartido | `shared/` | Indicaciones para la IA (`prompts.json`), formato del cuaderno (`cuaderno.js`, `page.html`) |
| Documentación | `docs/` | Esta guía, auditoría, criterios del panel, Atajo de iPhone |

La IA que se usa:
- **Groq:** transcribe con Whisper y pule el dictado con gpt-oss. Es rápido (~1,3 s por dictado).
- **Gemini:** arma los apuntes. Le entra la clase entera de una vez y también lee las fotos.
  Sin clave de Gemini, los apuntes se arman con Groq por tramos.

## 2. La PC

### Mapa de `flowlite.py` (las funciones que importan)
| Qué | Dónde |
|---|---|
| Configuración (modelos, carpeta de apuntes) | `CONFIG` |
| Indicaciones para la IA (se cargan de `shared/prompts.json`) | `PROMPTS`, `final_prompt(kind)`, `NOTE_TYPES` |
| Llamadas a la IA | `groq_post`, `groq_transcribe`, `groq_chat`, `gemini_chat` (sigue sola si Gemini se corta por largo) |
| Dictado | `Recorder` (micrófono), `TapKeys` (mantener, 2 toques, 3 toques), `HOTKEYS`, `groq_polish`, `groq_command` (+ Shift), `paste` |
| Aprender del usuario | `learn`, `watch_edits`, `edits_to_learn` (si corregís lo dictado, aprende la palabra) |
| Historial | `History` (SQLite `history.db`), `setting`/`save_state` (`state.json`) |
| Detectar reuniones y llamadas | `detect_meeting` (títulos de ventana de Meet, Zoom y Teams), `apps_using_mic` + `mic_registry` (WhatsApp, Discord y otros: lee en el registro qué app usa el micrófono) |
| Grabar una clase | `ClassNotes`: audio de la PC y/o micrófono, tramos cortados en silencio, ⭐ ❓ 📸, mis notas |
| Transcribir tramos | `groq_transcribe_segments` + `junk_text` (descarta frases inventadas por Whisper, como «Subtítulos por Amara») |
| Armar apuntes | `build_notes` → `review_notes` (2.ª pasada: «profesor exigente» que completa lo que falta) → `make_pdf` |
| Sin Gemini | `groq_notes`, `make_sections`, `section_text` |
| Cuaderno | `md_to_html`, `md_block`, `md_inline`, `md_table`, `clean_math` (saca el LaTeX), `page_html` |
| Rehacer, clase sin terminar | `redo_notes`, `read_transcript`, `unfinished_classes` (aviso al abrir) |
| Asistente | `live_help` («¿Qué me perdí?» y «pregunta para el profe»), `ask_classes`, `study_guide` (resumen para el parcial) |
| Ventanas | `Orb` (la bolita), `StartDialog` (tipo, materia, detalle), `ClassWindow` (la clase en curso) |
| Arranque | `main()` |

En `panel.py`:
- `Panel` tiene las secciones Historial, Apuntes, Personal, Notas rápidas y Ajustes.
- `MeetingToast` es el aviso de «estás en una clase o llamada» y también el de «clase sin terminar».
- `Column`, `native_round` y `paper()` son el estilo visual.

### Formato del cuaderno
`Apuntes.md` es markdown con bloques propios. La PC (`md_to_html`) y el celular (`shared/cuaderno.js`) los convierten igual,
byte por byte. Eso lo controla `tests/parity.mjs`.

| Bloque | Ejemplo |
|---|---|
| Fichas | `::: formula Título` … `:::` (también `mapa`, `flujo`, `pregunta`, `importante`, `ojo`, `ejemplo`, `tip`, `duda`, `resumen`) |
| Margen | `>> Esto entra en el parcial` |
| Resaltado | `==texto==` |
| Tareas | `- [ ] Entregar TP 3 — jueves 23` |
| Imagen | `![Diapositiva](capturas/00120.jpg)` (el número es el segundo de la clase) |

### Una clase en disco (igual en la PC y el celular)
`Apuntes/AAAA-MM-DD HH.MM - Título/`
- `transcripcion.txt`: líneas `[mm:ss] texto`, `⭐ MARCA`, `❓ DUDA` y `📸 CAPTURA capturas/NNNNN.jpg`.
- `mis_notas.txt`, `indicaciones.json` (tipo y detalle) y `capturas/*.jpg`.
- `Apuntes.md`, `Apuntes.html` y `Apuntes.pdf`.

### Tipos de apunte
Se eligen en `StartDialog` y se guardan por materia. Cada tipo tiene su estructura en `prompts.json → types`.

| Tipo | Qué arma |
|---|---|
| Clase | Cuaderno para estudiar |
| Reunión de trabajo | Decisiones y próximos pasos (quién, qué y cuándo) |
| Llamada | Datos clave, montos y fechas, y lo que tengo que hacer |
| Charla o webinar | Ideas clave, ejemplos, recursos y autoevaluación |

### Compilar e instalar
```
cd C:\dev\flowlite
.venv\Scripts\python build.py --instalar
```
- Compila en una carpeta temporal y deja **un solo** `Descargas\FlowLite.zip`, que se pisa en cada compilación.
- Con `--instalar`, además lo descomprime en `C:\FlowLite` y lo abre.
- La clave, el vocabulario, el historial y los apuntes del usuario están en `C:\FlowLite` y no se tocan.
- Para armar el entorno de cero: `py -3.11 -m venv .venv`, y después
  `.venv\Scripts\pip install -r requirements.txt` (versiones exactas con las que se probó).

### Pruebas
Se corren con `.venv\Scripts\python tests\<archivo>.py`. Cada una termina en «OK» si pasa.

| Prueba | Qué cubre | Claves reales |
|---|---|---|
| `test_logic.py` | Teclas, detección de reuniones, atajos de voz, aprender, filtro de eco y cuaderno | No |
| `test_notes.py` | Clase completa con audio, cortes de internet y rehacer | No |
| `test_f2.py` | Tipos, micrófono, revisión, continuación de Gemini, PDF y clase sin terminar | No |
| `test_paths.py`, `test_panel.py`, `test_gui.py`, `test_main.py` | Panel, ventanas y programa entero | No |
| `test_panel_screen.py` | Capturas de la pantalla real. Hay que mirarlas, ver `docs/panel-criterios.md` | No |
| `test_real_groq.py`, `test_real_notes.py`, `test_real_assist.py`, `test_real_long.py` | Contra Groq y Gemini de verdad. Leen las claves de `C:\FlowLite\.env` | Sí |

Del celular (Node 20 o más nuevo):

| Prueba | Qué hace |
|---|---|
| `node tests/parity.mjs` | El cuaderno de JS da idéntico al de Python. Antes corre `tests/parity_corpus.py` |
| `node tests/test_real_mobile_ai.mjs C:\FlowLite clase.wav` | La IA del celular con claves reales |
| `node tests/mock_server.mjs 8765 <carpeta>` | Sirve la app con Groq, Gemini y Drive simulados. Abrir `http://localhost:8765/?mock=1&seed=1` |
| `node tests/shots_mobile.mjs <salida>` | Capturas de las 6 pantallas en tamaño de celular |

Resultados de la última revisión: `docs/auditoria.md`.

## 3. El celular

### App web (`mobile/`)
Es una sola app para Android y iPhone. Se publica sola con `.github/workflows/pages.yml` en cada push a `main`
que toque `mobile/` o `shared/`, en https://arenasxas.github.io/flowlite/

| Archivo | Qué hace |
|---|---|
| `index.html`, `app.css`, `app.js` | Pantallas: Grabar, Mis clases, Repasar, Dictar y Ajustes |
| `record.js` | `ClassRecorder`: tramos de 60 s, transcripción en vivo, pausa, pantalla encendida y audio del celular en Android. `QuickRecorder` es el dictado |
| `ai.js` | Lo mismo que la PC: `buildNotes`, `reviewNotes`, `liveHelp`, `askClasses`, `studyGuide`, `polish` |
| `drive.js` | Sincroniza con `Mi unidad/FlowLite/Apuntes` (el mismo formato que la PC). `pull` baja lo nuevo, `push` sube lo del celular |
| `repaso.js` | Tarjetas de las `::: pregunta` con repaso espaciado: 1, 3, 7, 14 y 30 días |
| `store.js` | IndexedDB (clases) y localStorage (ajustes, prefijo `fl.`) |
| `sw.js` | Funciona sin internet. **Hay que cambiar `VERSION` en cada publicación**, así avisa «Hay una versión nueva» |
| `config.js` | Direcciones de las APIs, `googleClientId` (es público, no secreto) y links |

**Seguridad:**
- Las claves de Groq y Gemini quedan solo en ese celular y no se sincronizan.
- El cuaderno escapa todo el texto antes de mostrarlo.
- No hay librerías de terceros.

### Android nativo (`android/`)
`.github/workflows/android.yml` lo compila en GitHub y publica `FlowLite.apk` en *Releases*.

| Archivo | Qué hace |
|---|---|
| `MainActivity.kt` | Abre la app web en un WebView y da permisos de micrófono y cámara. Tiene el puente `FlowLiteAndroid`, y el inicio de sesión de Google para Drive va por el sistema, porque Google no deja hacerlo dentro de un WebView |
| `FlowKeyboard.kt` | Teclado para dictar en cualquier app. Mantener y hablar → texto pulido. Con texto seleccionado, lo dicho es una orden sobre ese texto |
| `CaptureService.kt` | Graba el audio que suena en el celular (videos, YouTube, clases grabadas) en tramos de 60 s |
| `Groq.kt` | Transcribir y pulir, con las mismas indicaciones (`prompts.json` entra en el APK) |

El puente que ve la app web es `window.FlowLiteAndroid`:
- Métodos: `isAvailable`, `saveKeys`, `saveSettings`, `startDeviceAudio`, `stopDeviceAudio`, `openKeyboardSettings` y `requestDriveToken`.
- Respuestas de Android: `flowliteOnDeviceChunk(b64, segundo)`, `flowliteOnDeviceStatus(texto)` y `flowliteOnDriveToken(token, error)`.

**Firma del APK:**
- Está como secretos del repo: `FLOWLITE_KEYSTORE_B64` y `FLOWLITE_KEY_PASS`. Con la misma firma, cada versión se instala encima de la anterior.
- Hay una copia de respaldo en `C:\FlowLite\firma-android\` de la PC de quien la creó. **No subirla nunca al repo.**
- Huella SHA-1: `64:45:E3:4A:7D:A2:28:56:53:FC:DB:72:DC:63:C8:53:D6:F5:71:5D`. Hace falta para Google Cloud.

### iPhone
- La app web, más un Atajo para dictar en cualquier app: `docs/iphone-atajo.md`.
- Un teclado propio necesita una Mac y una cuenta de desarrollador de Apple (US$99 por año).

### Límites reales (no son de FlowLite)
| Qué | Android | iPhone |
|---|---|---|
| Grabar una llamada o videollamada en vivo (Meet, Zoom, WhatsApp) del mismo celular | **No** (Android no lo deja; llega silencio) | **No** |
| Grabar videos, YouTube y clases grabadas que se ven en el celular | Sí, con la app de Android | No |
| Grabar clases presenciales por micrófono | Sí | Sí, con la pantalla encendida |
| Dictar en cualquier app | Teclado FlowLite | Atajo + pegar |

Las clases virtuales en vivo se graban con FlowLite en la PC.
Con Google Drive, los apuntes aparecen solos en el celular para leerlos y repasarlos.

## 4. Decisiones de diseño (y por qué)
- **Gemini para apuntes y Groq para dictado.** Gemini lee la clase entera y las fotos, y escribe mejor los apuntes largos. Groq es el más rápido para dictar.
- **Revisión «profesor exigente».** En una clase real de Estadística de 47 min, contra 31 datos que dio el profesor:
  - Wispr Flow encontró 22.
  - FlowLite sin la revisión, 30.
  - FlowLite con la revisión, 31.
  - El detalle está en `docs/auditoria.md`.
- **Indicaciones en `shared/prompts.json`.** Es una sola fuente para la PC, la web y Android: si se mejora una, mejora en los tres.
- **Nada en Documentos ni en el Escritorio.** El «Acceso controlado a carpetas» de Windows Defender bloquea programas sin firma en esas carpetas, por eso todo va a `C:\FlowLite`.
- **Sin transparencias ni sombras en Qt.** En Windows dejaban restos y parpadeos. Se usan bordes redondeados nativos (`native_round`).
- **Bug del BOM.** El `vocabulary.json` original venía con BOM (una marca invisible al principio del archivo) y el programa no lo podía leer. Ahora se abre con `encoding="utf-8-sig"`.
- **PDF con Chrome sin ventana** (y Edge si no hay Chrome), con un perfil temporal. Edge falla en silencio cuando tiene una actualización pendiente.
- **Autocorrecciones del dictado.** Whisper escribe «a las 5 no a las 6» sin comas. La regla de `polish` aclara que un «no» seguido de otro dato del mismo tipo es una corrección. Probado con negaciones reales, que no se tocan.

## 5. Pasos que tiene que hacer una persona

### En cada PC
1. Instalar FlowLite: descomprimir `FlowLite.zip` en `C:\FlowLite`, abrir `FlowLite.exe` y pegar la clave de Groq.
   La clave de Gemini se agrega después, en Ajustes.
2. **Google Drive para escritorio**, para que el celular vea las clases:
   - Bajarlo de https://www.google.com/drive/download/, instalarlo e iniciar sesión.
   - En FlowLite: ⚙️ Ajustes → «Carpeta de apuntes» → **Usar Google Drive**.
   - Si Windows Defender avisa que bloqueó FlowLite: Seguridad de Windows → Protección contra ransomware → Permitir una aplicación → `C:\FlowLite\FlowLite.exe`.

### Google Cloud (una sola vez, para la sincronización con Drive)
1. Entrar a https://console.cloud.google.com → **Nuevo proyecto** «FlowLite».
2. *APIs y servicios → Biblioteca* → **Google Drive API** → Habilitar.
3. *Pantalla de consentimiento de OAuth:*
   - Tipo **Externo**, nombre FlowLite y tu mail.
   - En **Usuarios de prueba**, agregar el mail de cada persona que lo va a usar (vos y tu papá).
   - Dejarlo en modo «Prueba». El permiso de Drive completo sin verificación de Google solo anda para los usuarios de prueba, y alcanza.
4. *Credenciales → Crear credenciales → ID de cliente de OAuth*, dos veces:
   - **Aplicación web:**
     - Origen autorizado de JavaScript: `https://arenasxas.github.io`.
     - Copiar el ID (termina en `.apps.googleusercontent.com`) y ponerlo en `mobile/config.js` → `googleClientId`.
     - Hacer push. Ese ID es público por diseño.
   - **Android:**
     - Paquete: `ar.flowlite`.
     - SHA-1: `64:45:E3:4A:7D:A2:28:56:53:FC:DB:72:DC:63:C8:53:D6:F5:71:5D`.
     - No hay que copiar nada en el código: Google lo reconoce por el paquete y la firma.

### En cada celular
1. Abrir https://arenasxas.github.io/flowlite/ → menú → **Agregar a pantalla de inicio**.
2. Abrirla → Ajustes → pegar las claves → Guardar → **Conectar Google Drive**.
3. **Android:**
   - Bajar `FlowLite.apk` de https://github.com/Arenasxas/flowlite/releases/latest y abrirlo.
   - Permitir «instalar apps desconocidas» para el navegador.
   - Abrir FlowLite y aceptar el micrófono.
   - Dictar → **Activar el teclado** → prender «Teclado FlowLite».
   - En cualquier app, cambiar al teclado con el ícono 🌐 o el de teclado de la barra de abajo.
4. **iPhone:** armar el Atajo con `docs/iphone-atajo.md`.

### Checklist para probar en un Android (no verificado, falta un teléfono real)
- [ ] El APK se instala y abre la app.
- [ ] Grabar una clase con el micrófono durante 3 minutos y armar los apuntes.
- [ ] «Audio del celular» con un video de YouTube sonando: llegan los tramos con texto.
- [ ] Teclado: dictar en WhatsApp. Seleccionar texto y decir «hacelo más formal».
- [ ] Conectar Drive desde la app de Android (necesita el ID de cliente Android creado).
- [ ] Foto con la cámara durante la clase.
- [ ] Instalar un APK nuevo encima del anterior, sin desinstalar.

## 6. Cómo publicar un cambio
1. Cambiar el código y correr las pruebas de la sección 2.
2. Si cambió algo del celular, subir `VERSION` en `mobile/sw.js` (y `version` en `mobile/config.js`).
3. Antes de cada push, revisar que no haya claves:
   `git grep -nE "gsk_[A-Za-z0-9]{10}|AIza[0-9A-Za-z_-]{20}"` tiene que salir vacío.
4. `git commit` y `git push`. GitHub publica la web y el APK solo, en la pestaña *Actions*.
5. PC: `build.py --instalar` y pasar `Descargas\FlowLite.zip`.

## 7. Ideas para seguir
- Modo comando y vocabulario del teclado de Android sincronizados con la PC por Drive.
- En iPhone, un teclado propio si algún día hay Mac y cuenta de desarrollador.
- Pasar la app web a TypeScript si crece mucho. Hoy son ~1500 líneas legibles sin compilación, y así es más fácil de mantener.
