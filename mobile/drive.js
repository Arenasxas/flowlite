// Sincronización con Google Drive: la misma carpeta que usa la PC (Mi unidad/FlowLite/Apuntes/<clase>/).
// La PC escribe ahí con "Google Drive para escritorio"; el celular lee y sube con la API de Drive.
import * as store from "./store.js";

const C = () => window.FLOWLITE_CONFIG;
let token = null, tokenExp = 0;
const FOLDER = "application/vnd.google-apps.folder";

// En la app de Android el inicio de sesión de Google va por el sistema (Google no deja hacerlo dentro de un WebView)
const nativeAuth = () => window.FlowLiteAndroid && window.FlowLiteAndroid.requestDriveToken;

export function configured() { return !!(C().googleClientId || C().mock || nativeAuth()); }
export function connected() { return C().mock ? store.get("driveOn", false) : !!token && Date.now() < tokenExp; }

function loadGis() {
  return new Promise((ok, fail) => {
    if (window.google && google.accounts) return ok();
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.onload = ok;
    s.onerror = () => fail(new Error("No pude cargar el inicio de sesión de Google"));
    document.head.appendChild(s);
  });
}

/** Pide permiso a Google (una ventanita). En modo prueba, no hace falta. */
export async function connect(interactive = true) {
  if (C().mock) { store.set("driveOn", true); token = "mock"; tokenExp = Date.now() + 3600e3; return; }
  if (nativeAuth()) {
    return new Promise((ok, fail) => {
      window.flowliteOnDriveToken = (t, err) => {
        if (!t) return fail(new Error("Drive: " + (err || "sin permiso")));
        token = t; tokenExp = Date.now() + 50 * 60e3; store.set("driveOn", true); ok();
      };
      window.FlowLiteAndroid.requestDriveToken();
    });
  }
  if (!C().googleClientId) throw new Error("Falta configurar el ID de cliente de Google (ver la guía).");
  await loadGis();
  await new Promise((ok, fail) => {
    const client = google.accounts.oauth2.initTokenClient({
      client_id: C().googleClientId, scope: "https://www.googleapis.com/auth/drive",
      prompt: interactive ? "" : "none",
      callback: (r) => {
        if (r.error) return fail(new Error(r.error));
        token = r.access_token;
        tokenExp = Date.now() + (r.expires_in - 60) * 1000;
        store.set("driveOn", true);
        ok();
      },
    });
    client.requestAccessToken();
  });
}

async function api(path, init = {}) {
  if (!connected()) await connect(false);
  const r = await fetch(C().drive + path, { ...init, headers: { ...(init.headers || {}), Authorization: `Bearer ${token}` } });
  if (r.status === 401) { token = null; throw new Error("Se venció el permiso de Drive: tocá «Conectar Google Drive»."); }
  if (!r.ok) throw new Error(`Drive ${r.status}: ${(await r.text()).slice(0, 150)}`);
  return r;
}

const q = (s) => encodeURIComponent(s);
async function list(query, fields = "files(id,name,mimeType,modifiedTime)") {
  const out = [];
  let page = "";
  do {
    const r = await (await api(`/drive/v3/files?q=${q(query)}&fields=nextPageToken,${fields}&pageSize=1000${page ? "&pageToken=" + page : ""}`)).json();
    out.push(...r.files);
    page = r.nextPageToken;
  } while (page);
  return out;
}

async function child(parent, name, create = true) {
  const esc = name.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
  const found = await list(`'${parent}' in parents and name='${esc}' and mimeType='${FOLDER}' and trashed=false`);
  if (found.length) return found[0].id;
  if (!create) return null;
  const r = await api("/drive/v3/files", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, mimeType: FOLDER, parents: [parent] }) });
  return (await r.json()).id;
}

async function apuntesFolder() {
  const fl = await child("root", "FlowLite");
  return child(fl, "Apuntes");
}

async function download(id) { return (await api(`/drive/v3/files/${id}?alt=media`)).blob(); }

async function upload(parent, name, blob, existingId) {
  if (existingId) {
    await api(`/upload/drive/v3/files/${existingId}?uploadType=media`, { method: "PATCH", body: blob });
    return existingId;
  }
  const form = new FormData();
  form.append("metadata", new Blob([JSON.stringify({ name, parents: [parent] })], { type: "application/json" }));
  form.append("file", blob);
  return (await (await api("/upload/drive/v3/files?uploadType=multipart", { method: "POST", body: form })).json()).id;
}

// ── conversión clase ⇄ archivos (mismo formato que la PC) ──
const clockStr = (t) => { const s = Math.floor(t), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), p = (n) => String(n).padStart(2, "0"); return h ? `${h}:${p(m)}:${p(s % 60)}` : `${p(m)}:${p(s % 60)}`; };

export function transcriptText(c) {
  const lines = c.segments.map(([t, x]) => [t, `[${clockStr(t)}] ${x}`]);
  c.marks.forEach((m) => lines.push([m, `[${clockStr(m)}] ⭐ MARCA`]));
  c.doubts.forEach((m) => lines.push([m, `[${clockStr(m)}] ❓ DUDA`]));
  (c.captures || []).forEach((p) => lines.push([p.sec, `[${clockStr(p.sec)}] 📸 CAPTURA ${p.rel}`]));
  return lines.sort((a, b) => a[0] - b[0]).map((x) => x[1]).join("\n") + "\n";
}

export function parseTranscript(text) {
  const segs = [], marks = [], doubts = [];
  for (const line of text.split(/\r?\n/)) {
    const m = line.trim().match(/^\[(?:(\d+):)?(\d+):(\d+)\]\s?(.*)/);
    if (!m) continue;
    const sec = (+m[1] || 0) * 3600 + +m[2] * 60 + +m[3];
    if (m[4].startsWith("⭐")) marks.push(sec);
    else if (m[4].startsWith("❓")) doubts.push(sec);
    else if (m[4].startsWith("📸")) continue;
    else if (m[4]) segs.push([sec, m[4]]);
  }
  return { segs, marks, doubts };
}

/** Baja de Drive las clases nuevas o cambiadas (de la PC u otro celular). Devuelve cuántas trajo. */
export async function pull(onStatus = () => {}) {
  const root = await apuntesFolder();
  const folders = await list(`'${root}' in parents and mimeType='${FOLDER}' and trashed=false`);
  let n = 0;
  for (const f of folders) {
    if (f.name.startsWith("_")) continue;
    const local = await store.getClass(f.name);
    if (local && local.driveTime && local.driveTime >= f.modifiedTime) continue;
    if (local && local.dirty) continue; // tiene cambios del celular sin subir: no se pisan (se suben en push)
    onStatus(`Bajando «${f.name.slice(19) || f.name}»…`);
    const files = await list(`'${f.id}' in parents and trashed=false`);
    const by = Object.fromEntries(files.map((x) => [x.name, x]));
    const text = async (name) => (by[name] ? (await (await download(by[name].id)).text()).replace(/\r\n?/g, "\n") : "");
    const tr = parseTranscript(await text("transcripcion.txt"));
    const caps = [];
    if (by.capturas) {
      for (const img of await list(`'${by.capturas.id}' in parents and trashed=false`)) {
        if (/^\d{5}\.jpg$/.test(img.name)) caps.push({ sec: +img.name.slice(0, 5), rel: `capturas/${img.name}`, blob: await download(img.id) });
      }
    }
    let prefs = {};
    try { prefs = JSON.parse(await text("indicaciones.json") || "{}"); } catch { /* vacío */ }
    await store.saveClass({ ...(local || {}), id: f.name, title: f.name.slice(19) || "Clase", segments: tr.segs, marks: tr.marks,
      doubts: tr.doubts, myNotes: await text("mis_notas.txt"), prefs, captures: caps, md: await text("Apuntes.md") || (local && local.md) || "",
      origin: local ? local.origin : "drive", driveTime: f.modifiedTime, dirty: false });
    n++;
  }
  return n;
}

/** Sube las clases hechas en el celular que todavía no están en Drive (o que cambiaron). */
export async function push(onStatus = () => {}, renderHtml) {
  const root = await apuntesFolder();
  let n = 0;
  for (const c of await store.allClasses()) {
    if (!c.dirty) continue;
    onStatus(`Subiendo «${c.title}»…`);
    const dir = await child(root, c.id);
    const existing = Object.fromEntries((await list(`'${dir}' in parents and trashed=false`)).map((x) => [x.name, x.id]));
    const put = (name, content, type = "text/plain") => upload(dir, name, new Blob([content], { type }), existing[name]);
    await put("transcripcion.txt", transcriptText(c));
    if (c.myNotes) await put("mis_notas.txt", c.myNotes);
    await put("indicaciones.json", JSON.stringify(c.prefs || {}), "application/json");
    if (c.md) {
      await put("Apuntes.md", c.md);
      if (renderHtml) await put("Apuntes.html", renderHtml(c), "text/html");
    }
    if ((c.captures || []).length) {
      const capDir = await child(dir, "capturas");
      const have = new Set((await list(`'${capDir}' in parents and trashed=false`)).map((x) => x.name));
      for (const p of c.captures) {
        const name = p.rel.split("/")[1];
        if (!have.has(name)) await upload(capDir, name, p.blob);
      }
    }
    await store.saveClass({ ...c, dirty: false, driveTime: new Date().toISOString() });
    n++;
  }
  return n;
}
