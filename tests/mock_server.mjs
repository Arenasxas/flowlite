// Servidor de pruebas de la app del celular: sirve mobile/ + shared/ y simula Groq, Gemini y Google Drive.
// Uso: node tests/mock_server.mjs [puerto] [carpeta con clase.wav, slide.png y Apuntes.md de ejemplo]
// Abrir http://localhost:8765/?mock=1&fake=/test-audio/clase.wav&chunk=10
import { createServer } from "node:http";
import { readFileSync, existsSync, statSync } from "node:fs";
import { join, extname, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const PORT = +process.argv[2] || 8765;
const FIX = process.argv[3] || "";
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css", ".json": "application/json",
  ".png": "image/png", ".jpg": "image/jpeg", ".wav": "audio/wav", ".svg": "image/svg+xml" };
export const log = [];

// ── Drive simulado: árbol en memoria ──
let nextId = 1;
const files = new Map(); // id -> {id, name, mimeType, parents, data: Buffer, modifiedTime}
const FOLDER = "application/vnd.google-apps.folder";
function mk(name, parent, data = null, mimeType = data === null ? FOLDER : "application/octet-stream") {
  const id = "f" + nextId++;
  files.set(id, { id, name, mimeType, parents: [parent], data, modifiedTime: new Date().toISOString() });
  for (let p = parent; files.has(p); p = files.get(p).parents[0]) files.get(p).modifiedTime = new Date().toISOString();
  return id;
}
(function seed() {
  const fl = mk("FlowLite", "root"), ap = mk("Apuntes", fl);
  const cls = mk("2026-10-17 21.32 - Costos y Precios", ap);
  const md = FIX && existsSync(join(FIX, "Apuntes.md")) ? readFileSync(join(FIX, "Apuntes.md")) :
    Buffer.from("# Costos y Precios\n::: pregunta ¿Qué es el punto de equilibrio?\nVentas donde no se gana ni se pierde.\n:::\n![Diapo](capturas/00120.jpg)\n");
  mk("Apuntes.md", cls, md);
  mk("transcripcion.txt", cls, Buffer.from("[00:00] Hoy vemos punto de equilibrio.\n[01:00] ⭐ MARCA\n[02:00] 📸 CAPTURA capturas/00120.jpg\n"));
  mk("indicaciones.json", cls, Buffer.from('{"type":"clase","detail":"normal"}'));
  const caps = mk("capturas", cls);
  if (FIX && existsSync(join(FIX, "slide.png"))) mk("00120.jpg", caps, readFileSync(join(FIX, "slide.png")), "image/jpeg");
})();

function driveQuery(q) {
  const parent = (q.match(/'([^']+)' in parents/) || [])[1];
  const name = (q.match(/name='((?:[^'\\]|\\.)*)'/) || [])[1];
  const onlyFolders = q.includes(`mimeType='${FOLDER}'`);
  return [...files.values()].filter((f) => (!parent || f.parents[0] === parent) &&
    (name === undefined || f.name === name.replace(/\\'/g, "'").replace(/\\\\/g, "\\")) && (!onlyFolders || f.mimeType === FOLDER))
    .map(({ id, name, mimeType, modifiedTime }) => ({ id, name, mimeType, modifiedTime }));
}

function multipart(buf, ctype) {
  const boundary = "--" + ctype.split("boundary=")[1];
  const parts = [];
  let i = buf.indexOf(boundary);
  while (i !== -1) {
    const next = buf.indexOf(boundary, i + boundary.length);
    if (next === -1) break;
    const part = buf.subarray(i + boundary.length + 2, next - 2);
    const sep = part.indexOf("\r\n\r\n");
    parts.push({ head: part.subarray(0, sep).toString(), body: part.subarray(sep + 4) });
    i = next;
  }
  return parts;
}

// ── IA simulada ──
let chunkNo = 0;
const LINES = ["Hoy vamos a ver costos fijos y variables.", "El costo fijo no cambia con la producción.",
  "La contribución marginal es precio menos costo variable unitario.", "El punto de equilibrio es costos fijos dividido contribución marginal.",
  "Entregar el TP 3 el jueves 23 de octubre.", "Presten atención que esto entra en el parcial."];
const NOTES = (title, caps) => `# ${title}
*fecha · 05:00*

::: resumen Si tenés 1 minuto
- Costos fijos y variables → punto de equilibrio
:::

## Desarrollo
### Punto de equilibrio
- El **punto de equilibrio** es donde no se gana ni se pierde.
>> Esto entra en el parcial.
::: formula Punto de equilibrio
PE = CF ÷ CMU
Para qué: saber cuántas unidades vender
Ejemplo: 100.000 ÷ 200 = 500 u
:::
${caps.map((r) => `![Foto del pizarrón](${r})`).join("\n")}

## Tareas, fechas y avisos
- [ ] Entregar el TP 3 — jueves 23 de octubre

## Autoevaluación
::: pregunta ¿Cómo se calcula el punto de equilibrio?
Costos fijos ÷ contribución marginal unitaria.
:::
::: pregunta ¿Qué es un costo fijo?
El que no cambia con la producción en el corto plazo.
:::`;

function ai(path, body) {
  if (path.endsWith("/models") || path === "/mock/gemini") return { data: [{ id: "x" }] };
  if (path.includes("/audio/transcriptions")) {
    const n = chunkNo++;
    return { text: LINES[n % LINES.length], segments: [{ start: 0, text: LINES[n % LINES.length], no_speech_prob: 0.01, avg_logprob: -0.2, compression_ratio: 1.2 },
      { start: 5, text: "Subtítulos realizados por la comunidad de Amara.org", no_speech_prob: 0.1 }] };
  }
  if (path.includes("/chat/completions")) {
    const sys = body.messages[0].content, user = body.messages[1].content;
    let out = "- (tramo)";
    if (sys.startsWith("Sos un corrector")) out = user.charAt(0).toUpperCase() + user.slice(1).replace(/^eh /i, "") + ".";
    else if (sys.includes("compañero de banco")) out = "- ⚠️ TP 3 el jueves 23\n- Punto de equilibrio = CF \\(\\div\\) CMU";
    else if (sys.includes("proponé 2 preguntas")) out = "• ¿Se puede usar horas hombre?\n• ¿Qué pasa si cambia el precio?";
    else if (sys.startsWith("Respondé la pregunta")) out = "**PE** = CF ÷ CMU [Costos y Precios — 2026-10-17]";
    else if (sys.includes("Estructura exacta")) out = NOTES("Clase", []);
    return { choices: [{ message: { content: out } }] };
  }
  if (path.includes(":generateContent")) {
    const sys = body.systemInstruction.parts[0].text, user = body.contents[0].parts[0].text;
    const caps = [...user.matchAll(/ruta: (capturas\/\d{5}\.jpg)/g)].map((m) => m[1]);
    const imgs = body.contents[0].parts.filter((p) => p.inline_data).length;
    let out;
    if (sys.includes("profesor exigente")) out = user.split("APUNTES A REVISAR:\n")[1] + "\n\n::: ojo Error común\nNo confundir CF con CV.\n:::";
    else if (sys.startsWith("Respondé la pregunta")) out = `**Punto de equilibrio** = CF ÷ CMU [Costos y Precios — 2026-10-17] (miré ${imgs} imágenes)`;
    else if (sys.includes("RESUMEN PARA EL PARCIAL")) out = NOTES("Costos y Precios — resumen para el parcial", []);
    else out = NOTES(sys.includes("Llamada") && user.includes("Llamada") ? "Llamada con el contador" : "Costos y punto de equilibrio", caps);
    return { candidates: [{ content: { parts: [{ text: out }] }, finishReason: "STOP" }] };
  }
  return null;
}

const server = createServer((req, res) => {
  const chunks = [];
  req.on("data", (c) => chunks.push(c));
  req.on("end", () => {
    const buf = Buffer.concat(chunks);
    const url = new URL(req.url, "http://x");
    const p = decodeURIComponent(url.pathname);
    const send = (code, data, type = "application/json") => {
      res.writeHead(code, { "Content-Type": type, "Access-Control-Allow-Origin": "*", "Cache-Control": "no-store" });
      res.end(typeof data === "string" || Buffer.isBuffer(data) ? data : JSON.stringify(data));
    };
    if (p.startsWith("/mock/")) log.push({ method: req.method, path: p, size: buf.length });
    try {
      if (p.startsWith("/mock/groq") || p.startsWith("/mock/gemini")) {
        let body = {};
        const ct = req.headers["content-type"] || "";
        if (ct.includes("json")) body = JSON.parse(buf.toString() || "{}");
        if (ct.includes("multipart")) {
          const parts = multipart(buf, ct);
          const file = parts.find((x) => x.head.includes("filename"));
          if (!file || file.body.length < 1000) return send(400, { error: "archivo de audio vacío" });
        }
        const out = ai(p, body);
        return out ? send(200, out) : send(404, { error: "no simulado" });
      }
      if (p.startsWith("/mock/drive")) {
        const dp = p.slice("/mock/drive".length);
        if (req.method === "GET" && dp === "/drive/v3/files") return send(200, { files: driveQuery(url.searchParams.get("q") || "") });
        const m = dp.match(/^\/drive\/v3\/files\/([^/]+)$/);
        if (req.method === "GET" && m) return files.has(m[1]) ? send(200, files.get(m[1]).data, "application/octet-stream") : send(404, {});
        if (req.method === "POST" && dp === "/drive/v3/files") {
          const meta = JSON.parse(buf.toString());
          return send(200, { id: mk(meta.name, meta.parents[0]) });
        }
        if (req.method === "POST" && dp === "/upload/drive/v3/files") {
          const parts = multipart(buf, req.headers["content-type"]);
          const meta = JSON.parse(parts[0].body.toString());
          return send(200, { id: mk(meta.name, meta.parents[0], parts[1].body) });
        }
        const u = dp.match(/^\/upload\/drive\/v3\/files\/([^/]+)$/);
        if (req.method === "PATCH" && u && files.has(u[1])) { files.get(u[1]).data = buf; files.get(u[1]).modifiedTime = new Date().toISOString(); return send(200, { id: u[1] }); }
        return send(404, { error: "drive no simulado: " + req.method + " " + dp });
      }
      if (p === "/mock/log") return send(200, log);
      if (p === "/mock/drivefiles") return send(200, [...files.values()].map(({ id, name, parents, data }) => ({ id, name, parent: parents[0], size: data ? data.length : null })));
      // archivos de la app
      let file = p.startsWith("/test-audio/") ? join(FIX, p.slice(12)) : p.startsWith("/shared/") ? join(ROOT, p) : join(ROOT, "mobile", p);
      if (existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
      if (!existsSync(file)) return send(404, "no existe", "text/plain");
      return send(200, readFileSync(file), TYPES[extname(file)] || "application/octet-stream");
    } catch (e) {
      return send(500, { error: String(e) });
    }
  });
});
server.listen(PORT, () => console.log(`FlowLite móvil (simulado) en http://localhost:${PORT}/?mock=1`));
