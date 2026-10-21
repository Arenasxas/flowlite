// Guardado en el celular: las clases (con fotos) en IndexedDB; claves y ajustes en localStorage.
// Una clase usa el mismo formato que la PC: id = nombre de carpeta "AAAA-MM-DD HH.MM - Título".

const DB = "flowlite", STORE = "classes";
let dbp = null;

function db() {
  if (!dbp) {
    dbp = new Promise((ok, fail) => {
      const r = indexedDB.open(DB, 1);
      r.onupgradeneeded = () => r.result.createObjectStore(STORE, { keyPath: "id" });
      r.onsuccess = () => ok(r.result);
      r.onerror = () => fail(r.error);
    });
  }
  return dbp;
}

async function tx(mode, fn) {
  const d = await db();
  return new Promise((ok, fail) => {
    const t = d.transaction(STORE, mode);
    const req = fn(t.objectStore(STORE));
    t.oncomplete = () => ok(req && req.result);
    t.onerror = () => fail(t.error);
  });
}

export const saveClass = (c) => tx("readwrite", (s) => s.put({ ...c, updated: Date.now() }));
export const getClass = (id) => tx("readonly", (s) => s.get(id));
export const deleteClass = (id) => tx("readwrite", (s) => s.delete(id));
export const allClasses = async () => (await tx("readonly", (s) => s.getAll())).sort((a, b) => (a.id < b.id ? 1 : -1));

export function folderName(title, date = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  const stamp = `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())} ${p(date.getHours())}.${p(date.getMinutes())}`;
  const safe = (title || "Clase").replace(/[<>:"/\\|?*\x00-\x1f]/g, "").trim().replace(/^\.+|\.+$/g, "").slice(0, 60) || "Clase";
  return `${stamp} - ${safe}`;
}

// ── ajustes ──
const K = "fl.";
export const get = (k, def = "") => { try { const v = localStorage.getItem(K + k); return v === null ? def : JSON.parse(v); } catch { return def; } };
export const set = (k, v) => { try { localStorage.setItem(K + k, JSON.stringify(v)); } catch { /* modo privado */ } };

export function subjectKey(title) {
  const t = (title || "").split(/\s[-–—:|]\s/)[0];
  const plain = t.toLowerCase().normalize("NFD").replace(/[^\x00-\x7f]/g, "");
  return (plain.match(/\w+/g) || []).join(" ").replace(/\b(clase|unidad|tema|parte)\b|\d+/g, " ").trim() || "general";  // igual que subject_key de la PC
}
