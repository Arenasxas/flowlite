// IA de FlowLite en el celular: Groq (transcribir, pulir, ayuda rápida) y Gemini (apuntes, revisión, preguntas).
// Mismos prompts que la PC (shared/prompts.json) y mismo cuaderno (shared/cuaderno.js).
import { cleanMath, clock, junkText, HALLUCINATIONS, plainWords } from "./shared/cuaderno.js";
import * as store from "./store.js";

const C = () => window.FLOWLITE_CONFIG;
export let P = null;
export async function loadPrompts() {
  P = await (await fetch("shared/prompts.json")).json();
  return P;
}
const keys = () => ({ groq: store.get("groq", ""), gemini: store.get("gemini", "") });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const fmt = (tpl, vals) => tpl.replace(/\{(\w+)\}/g, (m, k) => (k in vals ? vals[k] : m));

// ── Groq ──
async function groqFetch(path, init, tries = 1) {
  for (let i = 0; i < tries; i++) {
    const r = await fetch(C().groq + path, { ...init, headers: { ...(init.headers || {}), Authorization: `Bearer ${keys().groq}` } });
    if (r.status === 429 && i < tries - 1) {
      const wait = parseFloat(r.headers.get("retry-after") || "10");
      await sleep(Math.min(wait, 90) * 1000 + 1000);
      continue;
    }
    if (!r.ok) throw new Error(`Groq ${r.status}: ${(await r.text()).slice(0, 200)}`);
    return r.json();
  }
}

export async function groqChat(system, user, { model = "openai/gpt-oss-20b", maxTokens, tries = 1 } = {}) {
  const body = { model, temperature: 0.2, reasoning_effort: "low", include_reasoning: false,
    messages: [{ role: "system", content: system }, { role: "user", content: user }] };
  if (maxTokens) body.max_completion_tokens = maxTokens;
  const r = await groqFetch("/chat/completions", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) }, tries);
  return r.choices[0].message.content.trim();
}

const ext = (blob) => (blob.type.includes("mp4") || blob.type.includes("aac") ? "m4a" : blob.type.includes("wav") ? "wav" : "webm");

export async function transcribe(blob, { prompt = "", verbose = false, tries = 1 } = {}) {
  const f = new FormData();
  f.append("file", blob, `audio.${ext(blob)}`);
  f.append("model", "whisper-large-v3-turbo");
  f.append("response_format", verbose ? "verbose_json" : "json");
  f.append("temperature", "0");
  const lang = store.get("language", "es");
  if (lang && lang !== "auto") f.append("language", lang);
  if (prompt) f.append("prompt", prompt.slice(-600));
  return groqFetch("/audio/transcriptions", { method: "POST", body: f }, tries);
}

/** Como groq_transcribe_segments de la PC: [(segundo, texto)] sin silencios, frases inventadas ni eco de la ayuda. */
export async function transcribeSegments(blob, start, prompt, avoid) {
  const r = await transcribe(blob, { prompt, verbose: true, tries: 4 });
  const segs = r.segments && r.segments.length ? r.segments : [{ start: 0, text: r.text || "", no_speech_prob: 0 }];
  const out = [];
  for (const s of segs) {
    const text = (s.text || "").trim();
    if (!text || (s.no_speech_prob || 0) > 0.6 || HALLUCINATIONS.test(text) || (s.compression_ratio || 0) > 2.4 ||
        (s.avg_logprob || 0) < -1.0 || junkText(text, avoid)) continue;
    if (out.length >= 2 && out[out.length - 1][1] === text && out[out.length - 2][1] === text) continue;
    out.push([start + (s.start || 0), fixTech(text)]);
  }
  return out;
}

export async function polish(text) {
  const own = store.get("vocab", []), have = new Set(own.map((w) => w.toLowerCase()));
  const vocab = own.concat((P.tech_vocab || []).filter((w) => !have.has(w.toLowerCase()))).join(", ");
  return fixTech(await groqChat(fmt(P.polish, { vocab, app: "celular" }), text));
}

/** Errores típicos de Whisper con nombres de IA y tecnología ("Cloud Code" → "Claude Code"). Lista en prompts.json. */
let fixes = null;
export function fixTech(text) {
  fixes = fixes || (P.tech_fixes || []).map(([p, r]) => [new RegExp(`(?<![\\p{L}\\p{N}_])(?:${p})(?![\\p{L}\\p{N}_])`, "giu"), r]);
  for (const [rx, r] of fixes) text = text.replace(rx, r);
  return text;
}

/** Ayuda para Whisper en el dictado: primero IA y tecnología (si se corta, queda lo propio al final). */
export function dictationPrompt() {
  return (P.tech_vocab || []).concat(store.get("vocab", []).slice(-40)).join(", ");
}

/** Whisper con casi silencio a veces devuelve la lista de la ayuda. */
export function promptEcho(text) {
  const words = plainWords(text).split(" ").filter(Boolean);
  const known = new Set(plainWords(dictationPrompt()).split(" "));
  return words.length >= 3 && words.every((w) => known.has(w));
}

// ── Gemini ──
export async function geminiChat(system, user, { maxTokens = 8000, images = [], continuations = 2, tries = 4 } = {}) {
  const parts = [{ text: user }];
  for (const [label, b64] of images) parts.push({ text: label }, { inline_data: { mime_type: "image/jpeg", data: b64 } });
  let contents = [{ role: "user", parts }], model = "gemini-3.8-flash", out = "";
  for (let c = 0; c <= continuations; c++) {
    let r;
    for (let i = 0; i < tries; i++) {
      r = await fetch(`${C().gemini}/${model}:generateContent`, { method: "POST",
        headers: { "Content-Type": "application/json", "x-goog-api-key": keys().gemini },
        body: JSON.stringify({ systemInstruction: { parts: [{ text: system }] }, contents,
          generationConfig: { temperature: 0.2, maxOutputTokens: maxTokens } }) });
      if (r.status === 404 && model !== "gemini-flash-latest") { model = "gemini-flash-latest"; i--; continue; }
      if ([429, 500, 503].includes(r.status) && i < tries - 1) { await sleep(20000 * (i + 1)); continue; }
      break;
    }
    if (!r.ok) throw new Error(`Gemini ${r.status}: ${(await r.text()).slice(0, 200)}`);
    const cand = (await r.json()).candidates[0];
    const piece = (cand.content && cand.content.parts || []).filter((p) => !p.thought).map((p) => p.text || "").join("");
    out += piece;
    if (cand.finishReason !== "MAX_TOKENS" || !piece) break;
    contents = [contents[0], { role: "model", parts: [{ text: out }] },
      { role: "user", parts: [{ text: "Seguí exactamente desde donde te cortaste, sin repetir nada y con el mismo formato." }] }];
  }
  return out.trim();
}

// ── apuntes (igual que build_notes de la PC) ──
export function finalPrompt(kind = "clase", intro) {
  const t = P.types[kind] || P.types.clase;
  return `${intro || t.intro}\n${P.final_syntax}\n\n${t.structure}\n\n${P.final_rules}`;
}

export function sectionText(segs, marks = [], doubts = []) {
  const lines = segs.map(([t, x]) => [t, `[${clock(t)}] ${x}`]);
  if (segs.length) {
    const lo = segs[0][0], hi = segs[segs.length - 1][0] + 60;
    for (const m of marks) if (m >= lo && m < hi) lines.push([m, `[${clock(m)}] ⭐ (el alumno marcó este momento como importante)`]);
    for (const m of doubts) if (m >= lo && m < hi) lines.push([m, `[${clock(m)}] ❓ (el alumno NO entendió lo que se dijo justo antes: explicalo mejor)`]);
  }
  return lines.sort((a, b) => a[0] - b[0]).map((x) => x[1]).join("\n");
}

const blobToB64 = (blob) => new Promise((ok) => { const r = new FileReader(); r.onload = () => ok(r.result.split(",")[1]); r.readAsDataURL(blob); });
const SECTION_LIMIT = 15000;

async function groqNotes(system, cls, status) {
  const span = 8 * 60, groups = [];
  let cur = [];
  for (const seg of cls.segments) {
    if (cur.length && (seg[0] - cur[0][0] >= span || cur.reduce((n, s) => n + s[1].length, 0) > SECTION_LIMIT * 0.7)) { groups.push(cur); cur = []; }
    cur.push(seg);
  }
  if (cur.length) groups.push(cur);
  let parts = [];
  for (let i = 0; i < groups.length; i++) {
    status(`Apuntes del tramo ${i + 1} de ${groups.length}…`);
    parts.push(await groqChat(P.section, sectionText(groups[i], cls.marks, cls.doubts), { model: "openai/gpt-oss-120b", tries: 5, maxTokens: 2000 }));
  }
  return groqFinal(system, parts, cls, status);
}

/** Une apuntes parciales (o los de varias clases) respetando el límite gratis de Groq, y escribe los finales. */
async function groqFinal(system, parts, cls, status) {
  while (parts.join("").length > SECTION_LIMIT && parts.length > 1) {
    status(`Resumiendo ${parts.length} partes…`);
    const next = [];
    for (let i = 0; i < parts.length; i += 3) {
      const g = parts.slice(i, i + 3);
      next.push(g.length === 1 ? g[0] : await groqChat(P.condense, g.join("\n\n---\n\n"), { model: "openai/gpt-oss-120b", tries: 5, maxTokens: 2500 }));
    }
    parts = next;
  }
  status("Escribiendo los apuntes finales…");
  let user = "APUNTES PARCIALES:\n\n" + parts.join("\n\n---\n\n");
  if ((cls.myNotes || "").trim()) user += "\n\nNOTAS DEL ALUMNO:\n" + cls.myNotes.trim();
  if (cls.marks.length) user += "\n\nMOMENTOS MARCADOS COMO IMPORTANTES (⭐): " + cls.marks.map(clock).join(", ");
  if (cls.doubts.length) user += "\n\nMOMENTOS QUE EL ALUMNO NO ENTENDIÓ (❓): " + cls.doubts.map(clock).join(", ");
  return groqChat(system, user, { model: "openai/gpt-oss-120b", tries: 5, maxTokens: 4000 });
}

export function genericTitle(t) {
  const k = plainWords(t || "").replace(/[\W\d_]/g, "");
  return ["", "clase", "reunion", "llamada", "charla"].includes(k) || /^llamadade\w+$/.test(k);
}

/** Arma los apuntes de una clase grabada. Devuelve {md, title}. */
export async function buildNotes(cls, status = () => {}) {
  if (!cls.segments.length) throw new Error("No hay nada transcripto: ¿se escuchaba la clase?");
  const prefs = cls.prefs || {}, kind = prefs.type || "clase", detail = prefs.detail || "normal";
  const duration = clock(cls.segments[cls.segments.length - 1][0]);
  const system = fmt(finalPrompt(kind), { title: cls.title, date: cls.id.slice(0, 16).replace(".", ":"), duration,
    detail: P.detail[detail] || P.detail.normal,
    extra: prefs.extra ? `Indicaciones del alumno para esta materia (seguilas): ${prefs.extra}\n` : "" });
  let md = null;
  if (keys().gemini) {
    status("Gemini está escribiendo los apuntes…");
    let user = "TRANSCRIPCIÓN COMPLETA:\n" + sectionText(cls.segments, cls.marks, cls.doubts);
    if ((cls.myNotes || "").trim()) user += "\n\nNOTAS DEL ALUMNO (con el minuto en que las escribió):\n" + cls.myNotes.trim();
    const caps = cls.captures || [];
    if (caps.length) user += `\n\nTE PASO ${caps.length} CAPTURAS DE LA CLASE, cada una con su minuto y su ruta.`;
    const images = [];
    for (const c of caps) images.push([`Captura del minuto ${clock(c.sec)} — ruta: ${c.rel}`, await blobToB64(c.blob)]);
    const big = detail === "detallado" ? 32000 : 16000;
    try {
      md = await geminiChat(system, user, { maxTokens: big, images });
      if (md && detail !== "resumido") md = await reviewNotes(md, cls, big, status);
    } catch (e) {
      console.warn("Gemini falló, sigo con Groq", e);
      md = null;
    }
  }
  if (!md) md = await groqNotes(system, cls, status);
  md = cleanMath(md);
  let title = cls.title;
  if (genericTitle(title)) {
    const m = md.match(/^#\s+(.+)$/m);
    if (m && !genericTitle(m[1])) title = m[1].trim().slice(0, 70);
  }
  const left = (cls.captures || []).filter((c) => !md.includes(c.rel));
  if (left.length) md += "\n\n## Capturas de la clase\n" + left.map((c) => `![Minuto ${clock(c.sec)}](${c.rel})`).join("\n");
  return { md, title };
}

export async function reviewNotes(md, cls, maxTokens, status = () => {}) {
  status("Revisando que no falte nada y desarrollando lo importante…");
  const user = `TRANSCRIPCIÓN:\n${sectionText(cls.segments, cls.marks, cls.doubts)}\n\n` +
    ((cls.myNotes || "").trim() ? `NOTAS DEL ALUMNO:\n${cls.myNotes.trim()}\n\n` : "") + `APUNTES A REVISAR:\n${md}`;
  try {
    const better = await geminiChat(P.review, user, { maxTokens });
    if (better.length < 0.8 * md.length || !better.trimStart().startsWith("#")) return md;
    return better;
  } catch (e) {
    console.warn("La revisión falló", e);
    return md;
  }
}

export async function liveHelp(kind, segs) {
  if (!segs.length) return "Todavía no hay transcripción: esperá un minuto.";
  const last = segs[segs.length - 1][0];
  const text = segs.filter((s) => s[0] >= last - 300).map(([t, x]) => `[${clock(t)}] ${x}`).join("\n").slice(-9000);
  return cleanMath(await groqChat(kind === "recap" ? P.recap : P.question, text, { tries: 2, maxTokens: 700 }));
}

export async function askClasses(question, classes) {
  const docs = classes.filter((c) => c.md || (c.segments || []).length).map((c) =>
    `### [${c.id.slice(19) || "Clase"} — ${c.id.slice(0, 10)}]\n${c.md || sectionText(c.segments)}`);
  if (!docs.length) return "Todavía no hay clases con apuntes para responder.";
  const user = `PREGUNTA: ${question}\n\nAPUNTES:\n\n`;
  if (keys().gemini) {
    try { return cleanMath(await geminiChat(P.ask, user + docs.join("\n\n").slice(0, 600000), { maxTokens: 2000 })); }
    catch (e) { console.warn("Gemini falló al responder", e); }
  }
  const q = new Set(plainWords(question).split(" "));
  const best = docs.map((d) => [plainWords(d.slice(0, 20000)).split(" ").filter((w) => q.has(w)).length, d])
    .sort((a, b) => b[0] - a[0]).slice(0, 3).map((x) => x[1].slice(0, 4000));
  return cleanMath(await groqChat(P.ask, user + best.join("\n\n"), { model: "openai/gpt-oss-120b", tries: 3, maxTokens: 1500 }));
}

export async function studyGuide(classes, subject, status = () => {}) {
  const parts = classes.filter((c) => c.md).sort((a, b) => (a.id < b.id ? -1 : 1))
    .map((c) => `## Clase del ${c.id.slice(0, 10)}\n${c.md}`);
  if (!parts.length) throw new Error("Esa materia todavía no tiene clases con apuntes.");
  const today = new Date().toISOString().slice(0, 10);
  const system = fmt(finalPrompt("clase", P.guide_intro), { title: `${subject} — resumen para el parcial`, date: today,
    duration: `${parts.length} clases`, detail: P.detail.normal, extra: "" });
  let md = null;
  if (keys().gemini) {
    status("Gemini está uniendo tus clases…");
    try { md = await geminiChat(system, "APUNTES DE LAS CLASES (en orden):\n\n" + parts.join("\n\n---\n\n"), { maxTokens: 20000 }); }
    catch (e) { console.warn(e); }
  }
  if (!md) md = await groqFinal(system, parts, { marks: [], doubts: [], myNotes: "" }, status);
  return cleanMath(md);
}

export async function keyOk(service, key) {
  try {
    const r = service === "groq"
      ? await fetch(`${C().groq}/models`, { headers: { Authorization: `Bearer ${key}` } })
      : await fetch(C().gemini, { headers: { "x-goog-api-key": key } });
    return [400, 401, 403].includes(r.status) ? false : r.ok ? true : null;
  } catch { return null; }
}
