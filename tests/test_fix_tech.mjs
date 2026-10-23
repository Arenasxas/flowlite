// Reemplazos de IA y tecnología en la app del celular: mismo resultado que fix_tech de la PC. Uso: node tests/test_fix_tech.mjs
import { readFileSync, mkdtempSync, cpSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
// armar la app como queda publicada (mobile/ + shared/ adentro)
const site = mkdtempSync(join(tmpdir(), "fl-site-"));
cpSync(join(ROOT, "mobile"), site, { recursive: true });
cpSync(join(ROOT, "shared"), join(site, "shared"), { recursive: true });
globalThis.localStorage = { getItem: () => null, setItem: () => {} };
globalThis.window = { FLOWLITE_CONFIG: {} };
globalThis.location = { search: "" };
globalThis.fetch = async (u) => new Response(readFileSync(join(site, u)));
const ai = await import(pathToFileURL(join(site, "ai.js")));
await ai.loadPrompts();

const CASES = [["instalé un servidor eme ce pe en Cloud Code", "instalé un servidor MCP en Claude Code"],
  ["lo armé con su pa base y chat GPT", "lo armé con Supabase y ChatGPT"],
  ["conectalo con n8n y subilo a git hub", "conectalo con n8n y subilo a GitHub"],
  ["probé deep seek y Copailot", "probé DeepSeek y Copilot"], ["armé una esquil nueva", "armé una skill nueva"]];
const SAME = ["Subí las fotos a la nube y vemos el código", "mañana voy al súper, a pie", "la abuela va a misa",
  "el prompt quedó bien", "nos vemos en el open de tenis", "vamos a la playa en enero"];
for (const [raw, want] of CASES) if (ai.fixTech(raw) !== want) throw new Error(`${raw} → ${ai.fixTech(raw)}`);
for (const s of SAME) if (ai.fixTech(s) !== s) throw new Error(`cambió: ${s} → ${ai.fixTech(s)}`);
if (!ai.promptEcho("ChatGPT, OpenAI, Claude, Gemini.") || ai.promptEcho("Abrí Claude y pedile el resumen")) throw new Error("eco");
if (!ai.polishAnswered("Si querés podés darme un prompt exacto para que ellos mismos lo instalen, así que dámelo o decime qué tengo que hacer yo.",
  "Instala y configura los agentes paso a paso: 1. **Instala Node.js y npm** - Descarga la última versión LTS desde https://nodejs.org. " +
  "- Ejecuta el instalador y verifica con `node -v`.\n2. **Crea un proyecto**\n```bash\nmkdir agente-ia\n```"))
  throw new Error("no detectó la respuesta");
if (ai.polishAnswered("primero pan segundo leche tercero queso cuarto fideos", "1. Pan\n2. Leche\n3. Queso\n4. Fideos")) throw new Error("lista");
console.log("FIX TECH OK");
