// Repaso con tarjetas: las preguntas de autoevaluación (::: pregunta) de todos los apuntes,
// con repaso espaciado simple (cajas de Leitner: 1, 3, 7, 14 y 30 días).
import * as store from "./store.js";

const DAYS = [0, 1, 3, 7, 14, 30];

function hash(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return (h >>> 0).toString(36);
}

/** Saca las tarjetas de los apuntes: [{id, q, a, clase, materia}]. */
export function cards(classes) {
  const out = [];
  for (const c of classes) {
    if (!c.md) continue;
    const re = /^\s*:::\s*pregunta\s+(.+)\n([\s\S]*?)\n\s*:::\s*$/gm;
    const md = c.md.replace(/\r\n?/g, "\n"); // los apuntes de la PC (Windows) vienen con \r\n
    let m;
    while ((m = re.exec(md))) out.push({ id: hash(c.id + "|" + m[1]), q: m[1].trim(), a: m[2].trim(), clase: c.id, materia: store.subjectKey(c.title) });
  }
  return out;
}

const state = () => store.get("repaso", {});

/** Tarjetas para hoy (vencidas o nuevas), primero las que más cuestan. */
export function due(all, materia = null) {
  const st = state(), now = Date.now();
  return all.filter((c) => (!materia || c.materia === materia) && (!st[c.id] || st[c.id].due <= now))
    .sort((a, b) => ((st[a.id] || { box: 0 }).box - (st[b.id] || { box: 0 }).box));
}

export function answer(card, knew) {
  const st = state();
  const box = knew ? Math.min(((st[card.id] || {}).box || 0) + 1, DAYS.length - 1) : 1;
  st[card.id] = { box, due: Date.now() + DAYS[box] * 86400e3 - 3600e3 };
  store.set("repaso", st);
  return box;
}

export function stats(all) {
  const st = state();
  const learned = all.filter((c) => (st[c.id] || {}).box >= 3).length;
  return { total: all.length, learned, today: due(all).length };
}
