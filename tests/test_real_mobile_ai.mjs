// La IA de la app del celular con Groq y Gemini de verdad, desde Node (sin navegador).
// Uso: node tests/test_real_mobile_ai.mjs <carpeta con .env> <clase.wav>
import { readFileSync, mkdtempSync, cpSync } from "node:fs";
import { join, dirname } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const env = Object.fromEntries(readFileSync(join(process.argv[2], ".env"), "utf8").split(/\r?\n/).filter((l) => l.includes("="))
  .map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1).trim()]));
// armar la app como queda publicada (mobile/ + shared/ adentro)
const site = mkdtempSync(join(tmpdir(), "fl-site-"));
cpSync(join(ROOT, "mobile"), site, { recursive: true });
cpSync(join(ROOT, "shared"), join(site, "shared"), { recursive: true });
const mem = {};
globalThis.localStorage = { getItem: (k) => (k in mem ? mem[k] : null), setItem: (k, v) => (mem[k] = String(v)) };
globalThis.window = { FLOWLITE_CONFIG: { groq: "https://api.groq.com/openai/v1", gemini: "https://generativelanguage.googleapis.com/v1beta/models" } };
globalThis.location = { search: "" };
const realFetch = fetch;
globalThis.fetch = (u, init) => (typeof u === "string" && u.startsWith("shared/") ? Promise.resolve(new Response(readFileSync(join(site, u)))) : realFetch(u, init));

const store = await import(pathToFileURL(join(site, "store.js")));
const ai = await import(pathToFileURL(join(site, "ai.js")));
const { mdToHtml } = await import(pathToFileURL(join(site, "shared", "cuaderno.js")));
store.set("groq", env.GROQ_API_KEY);
store.set("gemini", env.GEMINI_API_KEY || "");
await ai.loadPrompts();

console.log("claves:", await ai.keyOk("groq", env.GROQ_API_KEY), await ai.keyOk("gemini", env.GEMINI_API_KEY));
let t = Date.now();
const wav = new Blob([readFileSync(process.argv[3])], { type: "audio/wav" });
const segs = await ai.transcribeSegments(wav, 0, "Costos y Precios.", new Set(["costos", "precios"]));
console.log(`transcripción: ${segs.length} frases en ${((Date.now() - t) / 1000).toFixed(1)}s →`, segs.slice(0, 2).map((s) => s[1]));
t = Date.now();
console.log("pulido:", await ai.polish("eh bueno mañana a las cinco no a las seis paso por tu casa vos podés traer el apunte"), `(${((Date.now() - t) / 1000).toFixed(1)}s)`);
console.log("¿qué me perdí?:", (await ai.liveHelp("recap", segs)).slice(0, 160).replace(/\n/g, " | "));
const cls = { id: "2026-10-20 22.00 - Clase", title: "Clase", prefs: { type: "clase", detail: "normal" }, segments: segs, marks: [70], doubts: [80],
  myNotes: "[01:25] preguntar si el prorrateo puede ser por horas hombre", captures: [] };
t = Date.now();
const { md, title } = await ai.buildNotes(cls, (s) => console.log("  ·", s));
const html = mdToHtml(md);
console.log(`apuntes en ${((Date.now() - t) / 1000).toFixed(0)}s · título automático: «${title}» · ${md.split(/\s+/).length} palabras · fórmulas ${(md.match(/::: formula/g) || []).length} · preguntas ${(md.match(/::: pregunta/g) || []).length} · margen ${(html.match(/class="margin"/g) || []).length} · LaTeX ${/\\(frac|text|\()/.test(md)}`);
const hits = ["100.000", "500", "250.000", "horas m", "23 de octubre", "20 de noviembre", "Horngren"].filter((k) => md.includes(k));
console.log("datos clave encontrados:", hits.length, "de 7", hits);
cls.md = md;
console.log("preguntale a tus clases:", (await ai.askClasses("¿qué criterio de prorrateo usa la cátedra?", [cls])).slice(0, 200).replace(/\n/g, " | "));
console.log("MOBILE AI OK");
