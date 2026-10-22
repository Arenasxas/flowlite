# FlowLite en iPhone

En iPhone hay dos partes:

1. **La app web** (https://arenasxas.github.io/flowlite/). Sirve para grabar clases presenciales, ver los apuntes de la PC, repasar con tarjetas y dictar.
2. **Un Atajo** para dictar en **cualquier app**: WhatsApp, Mail, Notas…
   - Apple no deja instalar un teclado propio sin una Mac y una cuenta de desarrollador (US$99 por año).
   - El Atajo graba, transcribe con Groq, pule el texto y lo deja copiado para pegar.

## 1. App web

1. Abrí **Safari** y entrá a https://arenasxas.github.io/flowlite/
2. Tocá **Compartir** (el cuadrado con la flecha) → **Agregar a inicio** → **Agregar**.
3. Abrila desde el ícono → **Ajustes** → pegá tu clave de Groq (y la de Gemini, para mejores apuntes) → **Guardar**.
4. La primera vez que grabes, aceptá el permiso del micrófono.

**Límites del iPhone (no son de FlowLite):**
- **Con la pantalla bloqueada, la grabación se corta.** Durante una clase, dejá la pantalla prendida.
  La app la mantiene encendida en iOS 18.4 o más nuevo. En versiones anteriores, poné *Ajustes → Pantalla y brillo → Bloqueo automático → Nunca*
  mientras dure la clase.
- **No se puede grabar una llamada ni una videollamada** (Meet, Zoom, WhatsApp) que pasa en el mismo iPhone.
  Ninguna app puede. Esas clases se graban con FlowLite en la PC.
- Si la app instalada deja de grabar después de cerrarla y volver a abrirla (es un error conocido de iOS), abrí la misma
  dirección en una pestaña de Safari: anda igual y las clases quedan guardadas.

## 2. Atajo «FlowLite Dictar»

Se arma una sola vez, en unos 10 minutos. Abrí la app **Atajos** → **+** (arriba a la derecha) → nombre: **FlowLite Dictar**.
Agregá estas acciones en orden. Usá el buscador de acciones de abajo.

### Acción 1: Texto (tu clave)
- Buscá **Texto** y escribí tu clave de Groq, la que empieza con `gsk_`.
- Tocá el resultado y elegí **Renombrar** → `Clave`.

> ⚠️ Si compartís el atajo con alguien, la clave va adentro. Antes de compartirlo, borrala de esta acción.
> La otra persona pone la suya.

### Acción 2: Grabar audio
- **Empezar a grabar:** *Inmediatamente*.
- **Terminar de grabar:** *Al tocar*.
- Tocá la flecha `>` y elegí **Calidad de audio: Normal**. Así el archivo es más chico y el envío más rápido.

### Acción 3: Obtener contenido de URL (transcribir)
- **URL:** `https://api.groq.com/openai/v1/audio/transcriptions`
- Tocá `>`. **Método:** `POST`.
- **Encabezados:** agregá uno. Clave `Authorization`, valor `Bearer ` (con un espacio al final) + la variable **Clave**.
- **Cuerpo de la solicitud:** **Formulario**. Agregá estos campos:

| Tipo | Clave | Valor |
|---|---|---|
| Archivo | `file` | la variable **Audio grabado** |
| Texto | `model` | `whisper-large-v3-turbo` |
| Texto | `language` | `es` |
| Texto | `response_format` | `text` |
| Texto | `prompt` | la lista de abajo (ayuda a Whisper a escribir bien los nombres de IA y tecnología) |

- Renombrá el resultado: `Crudo`.

Lista para el campo `prompt`. Es la misma que usa la PC, y podés sumarle tus palabras al final:

```
IA, ChatGPT, OpenAI, GPT, Claude, Claude Code, Anthropic, Sonnet, Opus, Gemini, NotebookLM, Copilot, Perplexity, Grok, Groq, Llama, Mistral, DeepSeek, Whisper, Wispr Flow, Midjourney, Sora, ElevenLabs, Hugging Face, Ollama, Cursor, Lovable, Replit, n8n, Zapier, Notion, Supabase, Firebase, Vercel, GitHub, Python, JavaScript, TypeScript, React, Next.js, API, SDK, MCP, skill, plugin, prompt, token, LLM, agente, RAG, embeddings, fine-tuning, machine learning, GPU, NVIDIA, webhook, JSON, frontend, backend, deploy, open source, workflow, no-code, SaaS
```

> Si querés el texto tal cual se dijo (más rápido), saltá a la Acción 6 y usá **Crudo**.

### Acción 4: Obtener contenido de URL (pulir)
- **URL:** `https://api.groq.com/openai/v1/chat/completions`
- **Método:** `POST`.
- **Encabezados:**
  - `Authorization`: `Bearer ` + **Clave**
  - `Content-Type`: `application/json`
- **Cuerpo de la solicitud:** **JSON**, con estos campos:
  - Texto `model`: `openai/gpt-oss-20b`
  - Número `temperature`: `0.2`
  - Texto `reasoning_effort`: `low`
  - Matriz `messages`, con dos elementos de tipo **Diccionario**:
    1. Texto `role` = `system`, y Texto `content` = la indicación de abajo.
    2. Texto `role` = `user`, y Texto `content` = la variable **Crudo**.

Indicación para pegar en `content` (la misma que usa la PC; se puede copiar de acá con el iPhone, abriendo esta página en Safari):

```
Sos un corrector de dictado por voz en español rioplatense. Recibís una transcripción cruda.
Devolvé SOLO el texto final, sin comillas ni comentarios. Reglas:
- Corregí puntuación y mayúsculas; usá ¿? y ¡! cuando la frase es pregunta o exclamación.
- Sacá muletillas (eh, este, o sea, viste, bueno al inicio) y repeticiones o arranques en falso.
- Si la persona se corrige ("a las 5, no, a las 6" o "el martes no el jueves", aunque la transcripción venga sin comas), dejá solo la versión final ("a las 6", "el jueves"): un "no" seguido de otro dato del mismo tipo es una corrección, no una negación.
- No cambies el sentido, el tono ni el voseo. No respondas preguntas ni agregues contenido: solo transcribís.
- Puntuación dictada: "coma", "punto", "dos puntos", "signo de pregunta" se escriben como signo; "punto y aparte" o "nueva línea" = salto de línea; "nuevo párrafo" = línea en blanco.
- Si enumera cosas ("primero…, segundo…" o "uno…, dos…"), armá una lista con un ítem por línea.
- Respetá exactamente la grafía de este vocabulario: IA, ChatGPT, OpenAI, GPT, Claude, Claude Code, Anthropic, Sonnet, Opus, Gemini, NotebookLM, Copilot, Perplexity, Grok, Groq, Llama, Mistral, DeepSeek, Whisper, Wispr Flow, Midjourney, Sora, ElevenLabs, Hugging Face, Ollama, Cursor, Lovable, Replit, n8n, Zapier, Notion, Supabase, Firebase, Vercel, GitHub, Python, JavaScript, TypeScript, React, Next.js, API, SDK, MCP, skill, plugin, prompt, token, LLM, agente, RAG, embeddings, fine-tuning, machine learning, GPU, NVIDIA, webhook, JSON, frontend, backend, deploy, open source, workflow, no-code, SaaS, (y acá tus palabras)
- Si una palabra suena parecida a una del vocabulario, es esa (ej.: "servi" → "Servy").
- Formato según la app donde se escribe (la que esté abierta): en chats (WhatsApp, Telegram, Discord, Slack, Instagram) un mensaje corto de una sola oración va sin punto final; en mail o documentos (Gmail, Outlook, Word, Docs, Notion) usá oraciones completas y párrafos. Nunca cambies las palabras por esto.
Ejemplos:
Entrada: eh bueno mañana a las cinco no a las seis paso por tu casa vos podés
Salida: Mañana a las seis paso por tu casa. ¿Vos podés?
Entrada: nos juntamos el martes no el jueves a las 3 en la facu
Salida: Nos juntamos el jueves a las 3 en la facu.
Entrada: este quería saber si tenés tiempo el martes o sea para la reunión
Salida: ¿Tenés tiempo el martes para la reunión?
```

### Acción 5: Obtener valor del diccionario
- **Obtener** *Valor* para la clave `choices.1.message.content`, en **Contenido de la URL**.
- Si tu iOS no acepta la ruta con puntos, usá tres acciones seguidas:
  1. *Obtener valor del diccionario* `choices`.
  2. *Obtener elemento de la lista*: el primero.
  3. *Obtener valor del diccionario* `message`, y después `content`.

### Acción 6: Copiar al portapapeles y avisar
- **Copiar al portapapeles:** el resultado de la Acción 5 (o **Crudo**).
- **Mostrar notificación:** `Listo: pegalo` (opcional).

### Activarlo con dos toques en la espalda del iPhone
*Ajustes → Accesibilidad → Tocar → Tocar atrás → Tocar dos veces → **FlowLite Dictar***.
En el iPhone 15 Pro o más nuevo también se puede asignar al **botón de acción**: *Ajustes → Botón de acción → Atajo*.

### Usarlo
1. En cualquier app, tocá dos veces la espalda del iPhone. Arriba aparece la grabación.
2. Hablá y tocá **Listo** (o el cuadrado de parar).
3. En 2 o 3 segundos llega el aviso «Listo». Mantené el dedo en el campo de texto → **Pegar**.

### Si algo falla
- **«401» o «Invalid API key»:** la clave está mal copiada, o falta el espacio después de `Bearer`.
- **Sale el texto en inglés:** revisá el campo `language` = `es`.
- **Tarda mucho:** usá *Calidad de audio: Normal* y dictados de menos de 1 minuto.
- **No aparece «Tocar atrás»:** está disponible desde el iPhone 8, con iOS 14 o más nuevo.

## Checklist para probar en el iPhone (no verificado, falta un iPhone real)

- [ ] La app web abre desde el ícono de inicio y guarda las claves.
- [ ] Grabar una clase presencial de 3 minutos con la pantalla encendida. Aparecen el texto en vivo y los apuntes al terminar.
- [ ] Foto del pizarrón durante la clase. Aparece en los apuntes.
- [ ] Repasar muestra las preguntas de las clases.
- [ ] Atajo: dictar en WhatsApp con dos toques atrás y pegar.
