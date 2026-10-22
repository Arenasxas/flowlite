// FlowLite en el celular: grabar clases y llamadas, ver y estudiar los apuntes, dictar y sincronizar con la PC.
import { mdToHtml, clock, escapeHtml, pageHtml, plainWords } from "./shared/cuaderno.js";
import * as ai from "./ai.js";
import * as store from "./store.js";
import * as drive from "./drive.js";
import * as repaso from "./repaso.js";
import { ClassRecorder, QuickRecorder } from "./record.js";

const C = window.FLOWLITE_CONFIG;
const $ = (sel, el = document) => el.querySelector(sel);
const view = $("#view");
const S = { tab: "grabar", live: null, subject: null, template: "", busy: false };
const android = () => window.FlowLiteAndroid && window.FlowLiteAndroid.isAvailable && window.FlowLiteAndroid.isAvailable();
const params = new URLSearchParams(location.search);

function h(html) { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content; }
function pill(text, kind = "") { const p = $("#pill"); p.textContent = text; p.className = "pill " + kind; }
function toast(text, ms = 4000) {
  const d = document.createElement("div");
  d.className = "toast";
  d.textContent = text;
  document.body.appendChild(d);
  setTimeout(() => d.remove(), ms);
}
const keysOk = () => !!store.get("groq", "");

// ── navegación ──
function go(tab) {
  if (S.live && tab !== "grabar") toast("Sigue grabando: volvé a «Grabar» para ver la transcripción.");
  S.tab = tab;
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  $("#title").textContent = { grabar: "Grabar", clases: "Mis clases", repasar: "Repasar", dictar: "Dictar", ajustes: "Ajustes" }[tab];
  ({ grabar: renderGrabar, clases: renderClases, repasar: renderRepasar, dictar: renderDictar, ajustes: renderAjustes })[tab]();
}
document.querySelectorAll("#nav button").forEach((b) => b.addEventListener("click", () => go(b.dataset.tab)));

// ── Grabar ──
function prefsFor(title) { return (store.get("notes_prefs", {}))[store.subjectKey(title)] || { type: "clase", detail: "normal", extra: "" }; }

function renderGrabar() {
  if (S.live) return renderLive();
  if (!keysOk()) {
    view.replaceChildren(h(`<div class="card notice"><h2>Falta tu clave de Groq</h2>
      <p class="muted">Para transcribir hace falta una clave gratis de Groq. Cargala en Ajustes.</p>
      <button class="btn primary big" id="toaj">Ir a Ajustes</button></div>`));
    $("#toaj").onclick = () => go("ajustes");
    return;
  }
  const types = Object.entries(ai.P.types).map(([k, v]) => `<option value="${k}">${v.label}</option>`).join("");
  view.replaceChildren(h(`
    <div class="card">
      <label for="title">Materia o tema</label>
      <input id="ttl" list="subjects" placeholder="Ej.: Costos y Precios — clase 8" autocomplete="off">
      <datalist id="subjects"></datalist>
      <label for="kind">Tipo</label><select id="kind">${types}</select>
      <label for="detail">Detalle</label>
      <select id="detail"><option value="resumido">Resumido: para repasar rápido</option><option value="normal">Normal: apuntes completos</option>
        <option value="detallado">Muy detallado: como para estudiar sin haber ido</option></select>
      <label for="src">Qué grabar</label>
      <select id="src"><option value="mic">Micrófono (clase presencial o algo que suena cerca)</option>
        ${android() ? '<option value="device">Audio del celular (videos, YouTube, clases grabadas)</option>' : ""}</select>
      <label for="extra">Cómo querés los apuntes (se recuerda por materia)</label>
      <textarea id="extra" placeholder="Opcional. Ej.: «Poné cada fórmula con un ejemplo numérico»"></textarea>
      <button class="btn primary big" id="start">🎙 Empezar a grabar</button>
    </div>
    <div class="card notice"><h2>¿Qué se puede grabar con el celular?</h2>
      <p class="muted">✅ Clases presenciales, y clases o videos que suenan en otro aparato cerca (por el micrófono).<br>
      ✅ ${android() ? "Videos, YouTube y clases grabadas que mirás en este celular (opción «Audio del celular»)." :
        "En Android, con la app FlowLite: videos y clases grabadas que mirás en el mismo celular."}<br>
      ⛔ Una llamada en vivo (Meet, Zoom, WhatsApp) en este mismo celular: ni Android ni iPhone dejan que otra app grabe ese audio.
      Para eso usá FlowLite en la PC, o poné la clase en altavoz y grabá con otro celular.<br>
      💡 Dejá la pantalla prendida mientras graba.</p></div>`));
  store.allClasses().then((all) => {
    const names = [...new Set(all.map((c) => c.title.split(/\s[-–—:|]\s/)[0]))];
    $("#subjects").replaceChildren(...names.map((n) => Object.assign(document.createElement("option"), { value: n })));
  });
  const load = () => { const p = prefsFor($("#ttl").value); $("#kind").value = p.type || "clase"; $("#detail").value = p.detail || "normal"; $("#extra").value = p.extra || ""; };
  $("#ttl").addEventListener("change", load);
  load();
  $("#start").onclick = () => startClass($("#ttl").value.trim() || "Clase", $("#src").value,
    { type: $("#kind").value, detail: $("#detail").value, extra: $("#extra").value.trim() });
}

async function startClass(title, source, prefs) {
  const all = store.get("notes_prefs", {});
  all[store.subjectKey(title)] = prefs;
  store.set("notes_prefs", all);
  const cls = { id: store.folderName(title), title, prefs, segments: [], marks: [], doubts: [], captures: [], myNotes: "",
    md: "", origin: "celular", dirty: true };
  await store.saveClass(cls);
  const vocab = store.get("vocab", []).filter((w) => !["flowlite", "whatsapp", "groq", "padel"].includes(plainWords(w)));
  const avoid = new Set(plainWords(`${title} ${vocab.join(" ")}`).split(" "));
  const live = { cls, lineTimes: [], helper: "", paused: false };
  live.rec = new ClassRecorder({
    source, avoid,
    fakeAudioUrl: params.get("fake"),
    prompt: () => `${title}. ${vocab.length ? vocab.join(", ") + ". " : ""}${cls.segments.slice(-3).map((s) => s[1]).join(" ")}`,
    onSegments: (segs) => {
      cls.segments.push(...segs);
      cls.segments.sort((a, b) => a[0] - b[0]);
      store.saveClass(cls); // se guarda en cada tramo: si se cierra la app, la clase queda
      if (S.tab === "grabar") renderLive();
    },
    onStatus: (t) => { live.status = t; if (S.tab === "grabar") renderLive(); },
  });
  S.live = live;
  try {
    await live.rec.start();
  } catch (e) {
    S.live = null;
    toast("No pude empezar a grabar: " + e.message, 6000);
    return renderGrabar();
  }
  live.tick = setInterval(() => { const t = $("#timer"); if (t) t.textContent = clock(live.rec.elapsed()); }, 1000);
  pill("● Grabando", "rec");
  renderLive();
}

function stampedNotes(live, text) {
  const lines = text.split("\n");
  while (live.lineTimes.length < lines.length) live.lineTimes.push(null);
  const out = [];
  lines.forEach((l, i) => {
    if (l.trim() && live.lineTimes[i] === null) live.lineTimes[i] = live.rec.elapsed();
    if (l.trim()) out.push(`[${clock(live.lineTimes[i])}] ${l.trim()}`);
  });
  return out.join("\n");
}

function renderLive() {
  const L = S.live, c = L.cls;
  const notes = $("#mine") ? $("#mine").value : L.rawNotes || "";
  view.replaceChildren(h(`
    <div class="card">
      <div class="row"><div><div class="muted">${escapeHtml(c.title)} · ${escapeHtml(ai.P.types[c.prefs.type || "clase"].label)}</div>
        <div class="timer" id="timer">${clock(L.rec.elapsed())}</div></div></div>
      <div class="muted" id="status">${escapeHtml(L.status || (L.paused ? "En pausa" : "Escuchando… la transcripción aparece cada ~1 minuto."))}</div>
      ${L.helper ? `<div class="helper">${L.helper}</div>` : ""}
      <div class="grid">
        <button class="btn" id="mark">⭐ Importante</button><button class="btn" id="doubt">❓ No entendí</button>
        <label class="btn" style="text-align:center;margin:0;color:var(--text)">📸 Foto<input id="photo" type="file" accept="image/*" capture="environment" hidden></label>
        <button class="btn" id="recap">⏪ ¿Qué me perdí?</button><button class="btn" id="ask">💬 Pregunta</button>
        <button class="btn" id="pause">${L.paused ? "▶ Seguir" : "⏸ Pausar"}</button>
      </div>
      <button class="btn primary big" id="stop">⏹ Terminar y armar apuntes</button>
    </div>
    <div class="card"><h2>Mis notas</h2><textarea id="mine" placeholder="Lo que escribas acá va al margen del tema de ese minuto."></textarea></div>
    <div class="card"><h2>Transcripción en vivo</h2><div class="live" id="live">${c.segments.length ? "" : '<p class="muted">Todavía nada…</p>'}${
      c.segments.slice(-60).map(([t, x]) => `<p><time>${clock(t)}</time>${escapeHtml(x)}</p>`).join("")}</div></div>`));
  const lv = $("#live"); lv.scrollTop = lv.scrollHeight;
  const mine = $("#mine");
  mine.value = notes;
  mine.oninput = () => { L.rawNotes = mine.value; c.myNotes = stampedNotes(L, mine.value); };
  $("#mark").onclick = () => { c.marks.push(L.rec.elapsed()); toast("⭐ Marcado como importante"); store.saveClass(c); };
  $("#doubt").onclick = () => { c.doubts.push(L.rec.elapsed()); toast("❓ Lo explico mejor en los apuntes"); store.saveClass(c); };
  $("#photo").onchange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const sec = L.rec.elapsed();
    const blob = await compress(f);
    const rel = `capturas/${String(Math.floor(sec)).padStart(5, "0")}.jpg`;
    c.captures.push({ sec, rel, blob });
    await store.saveClass(c);
    toast("📸 Foto guardada: va a los apuntes explicada");
  };
  const help = async (kind) => {
    L.helper = "✨ Pensando…"; renderLive();
    try {
      const t = await ai.liveHelp(kind, c.segments);
      L.helper = `<b>${kind === "recap" ? "Lo último de la clase" : "Preguntas para hacer"}</b>${mdToHtml(t)}`;
    } catch (e) { L.helper = "No pude ayudarte ahora: " + escapeHtml(e.message); }
    renderLive();
  };
  $("#recap").onclick = () => help("recap");
  $("#ask").onclick = () => help("question");
  $("#pause").onclick = () => { L.paused = !L.paused; L.rec.pause(L.paused); pill(L.paused ? "⏸ En pausa" : "● Grabando", L.paused ? "warn" : "rec"); renderLive(); };
  $("#stop").onclick = () => finishClass();
}

async function compress(file, max = 1600) {
  const img = await createImageBitmap(file);
  const k = Math.min(1, max / img.width);
  const cv = Object.assign(document.createElement("canvas"), { width: Math.round(img.width * k), height: Math.round(img.height * k) });
  cv.getContext("2d").drawImage(img, 0, 0, cv.width, cv.height);
  return new Promise((ok) => cv.toBlob(ok, "image/jpeg", 0.82));
}

async function finishClass() {
  const L = S.live, c = L.cls;
  clearInterval(L.tick);
  view.replaceChildren(h(`<div class="card"><h2>⏳ Armando los apuntes…</h2><p class="muted" id="st">Termino de transcribir el último tramo.</p></div>`));
  pill("Armando apuntes", "warn");
  const missing = await L.rec.stop();
  S.live = null;
  c.myNotes = L.rawNotes ? stampedNotes(L, L.rawNotes) : c.myNotes;
  await store.saveClass(c);
  await makeNotes(c, (t) => { const st = $("#st"); if (st) st.textContent = t; }, missing);
  pill("Listo");
}

async function makeNotes(c, status, missing = 0) {
  try {
    const { md, title } = await ai.buildNotes(c, status);
    c.md = md + (missing ? `\n\n> ⚠️ Faltan ${missing} tramo(s) de audio sin transcribir.` : "");
    if (title !== c.title) {
      await store.deleteClass(c.id);
      c.id = c.id.slice(0, 19) + store.folderName(title).slice(19);
      c.title = title;
    }
    c.dirty = true;
    await store.saveClass(c);
    if (drive.connected()) drive.push(() => {}, renderPage).then(() => toast("☁️ Subido a Google Drive")).catch((e) => toast(e.message));
    openViewer(c);
  } catch (e) {
    toast("No pude armar los apuntes: " + e.message + ". La transcripción quedó guardada: probá «Armar apuntes» en Mis clases.", 8000);
  }
  go("clases");
}

// ── Visor del cuaderno ──
function renderPage(c, urls = {}) {
  let body = mdToHtml(c.md);
  for (const [rel, url] of Object.entries(urls)) body = body.split(`src="${rel}"`).join(`src="${url}"`);
  const tr = c.segments.map(([t, x]) => `<p><span>${clock(t)}</span>${escapeHtml(x)}</p>`).join("\n");
  return pageHtml(S.template, escapeHtml(c.title), body, tr, C.version);
}

function openViewer(c, md) {
  const urls = {};
  for (const p of c.captures || []) urls[p.rel] = URL.createObjectURL(p.blob);
  const page = md ? pageHtml(S.template, escapeHtml(c.title), mdToHtml(md), "", C.version) : renderPage(c, urls);
  $("#vtitle").textContent = c.title;
  $("#vframe").srcdoc = page;
  $("#viewer").classList.remove("hidden");
  $("#vback").onclick = () => { $("#viewer").classList.add("hidden"); $("#vframe").srcdoc = ""; Object.values(urls).forEach(URL.revokeObjectURL); };
  $("#vshare").onclick = async () => {
    const file = new File([md ? page : await standalonePage(c)], `${c.title}.html`, { type: "text/html" });
    if (navigator.canShare && navigator.canShare({ files: [file] })) navigator.share({ files: [file], title: c.title }).catch(() => {});
    else { const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(file), download: file.name }); a.click(); }
  };
}

async function standalonePage(c) {
  // para compartir: las fotos van adentro del archivo
  const urls = {};
  for (const p of c.captures || []) urls[p.rel] = await new Promise((ok) => { const r = new FileReader(); r.onload = () => ok(r.result); r.readAsDataURL(p.blob); });
  return renderPage(c, urls);
}

// ── Mis clases ──
async function renderClases() {
  const all = await store.allClasses();
  const subs = {};
  for (const c of all) (subs[store.subjectKey(c.title)] = subs[store.subjectKey(c.title)] || { name: c.title.split(/\s[-–—:|]\s/)[0], list: [] }).list.push(c);
  const shown = S.subject && subs[S.subject] ? subs[S.subject].list : all;
  view.replaceChildren(h(`
    <div class="card"><div class="row">
      ${drive.connected() ? '<button class="btn" id="sync">☁️ Sincronizar con la PC</button>' :
        `<button class="btn" id="conn">☁️ Conectar Google Drive</button>`}</div>
      <p class="muted" id="syncst">${drive.configured() ? "Las clases de la PC (guardadas en Google Drive) aparecen acá, y las del celular van a la PC." :
        "Para ver las clases de la PC falta configurar Google Drive (ver la guía)."}</p></div>
    <div class="card"><div class="row"><input id="q" placeholder="💬 Preguntale a tus clases…"><button class="btn primary" id="askb" style="flex:0">Preguntar</button></div>
      <div class="answer hidden" id="ans"></div></div>
    <div class="chips" id="chips"></div>
    ${S.subject ? '<button class="btn primary big" id="guide" style="margin-top:0">📚 Resumen para el parcial</button>' : ""}
    <div id="list"></div>`));
  const chips = $("#chips");
  for (const [k, v] of [[null, { name: "Todas", list: [] }], ...Object.entries(subs).sort((a, b) => (a[1].name < b[1].name ? -1 : 1))]) {
    const b = Object.assign(document.createElement("button"), { className: "chip" + (k === S.subject ? " on" : ""), textContent: v.name + (k ? ` ${v.list.length}` : "") });
    b.onclick = () => { S.subject = k; renderClases(); };
    chips.appendChild(b);
  }
  const list = $("#list");
  if (!shown.length) list.appendChild(h('<p class="muted">Todavía no hay clases. Grabá una o sincronizá con la PC.</p>'));
  for (const c of shown) {
    const card = h(`<div class="card cls"><div class="t"><b></b><span class="muted"></span><div class="badges"></div></div>
      <button class="btn act"></button></div>`).firstElementChild;
    $("b", card).textContent = c.title;
    $(".muted", card).textContent = c.id.slice(0, 16).replace(".", ":");
    $(".badges", card).innerHTML = `<span class="badge">${c.origin === "celular" ? "📱 este celular" : "☁️ Drive"}</span>` +
      (c.md ? "" : '<span class="badge warn">sin apuntes</span>') + (c.dirty && drive.connected() ? '<span class="badge">sin subir</span>' : "");
    const act = $(".act", card);
    act.textContent = c.md ? "Abrir" : "Armar apuntes";
    if (c.md) act.classList.add("primary");
    act.onclick = (e) => { e.stopPropagation(); c.md ? openViewer(c) : rebuild(c); };
    card.addEventListener("contextmenu", (e) => { e.preventDefault(); classMenu(c); });
    let press;
    card.addEventListener("touchstart", () => { press = setTimeout(() => classMenu(c), 650); }, { passive: true });
    card.addEventListener("touchend", () => clearTimeout(press));
    list.appendChild(card);
  }
  if (all.length) list.appendChild(h('<p class="muted">Mantené apretada una clase para rehacer los apuntes o borrarla del celular.</p>'));
  if ($("#sync")) $("#sync").onclick = () => sync();
  if ($("#conn")) $("#conn").onclick = async () => { try { await drive.connect(); await sync(); } catch (e) { toast(e.message, 6000); } };
  const ask = async () => {
    const q = $("#q").value.trim();
    if (!q) return;
    const ans = $("#ans");
    ans.classList.remove("hidden");
    ans.innerHTML = '<p class="muted">✨ Buscando en tus clases…</p>';
    try { ans.innerHTML = mdToHtml(await ai.askClasses(q, shown)); } catch (e) { ans.textContent = "No pude responder: " + e.message; }
  };
  $("#askb").onclick = ask;
  $("#q").addEventListener("keydown", (e) => e.key === "Enter" && ask());
  if ($("#guide")) $("#guide").onclick = async () => {
    const g = $("#guide");
    g.disabled = true; g.textContent = "⏳ Uniendo tus clases… (1-2 min)";
    try {
      const md = await ai.studyGuide(subs[S.subject].list, subs[S.subject].name, (t) => { g.textContent = "⏳ " + t; });
      openViewer({ title: `${subs[S.subject].name} — resumen para el parcial`, captures: [], segments: [] }, md);
    } catch (e) { toast(e.message, 6000); }
    g.disabled = false; g.textContent = "📚 Resumen para el parcial";
  };
}

function classMenu(c) {
  const choice = prompt(`«${c.title}»\n\n1 = Rehacer los apuntes\n2 = Borrar del celular (en Drive y la PC queda)\n\nEscribí 1 o 2:`);
  if (choice === "1") rebuild(c);
  if (choice === "2" && confirm("¿Borrar esta clase del celular?")) store.deleteClass(c.id).then(renderClases);
}

async function rebuild(c) {
  view.replaceChildren(h(`<div class="card"><h2>⏳ Armando los apuntes…</h2><p class="muted" id="st"></p></div>`));
  await makeNotes(c, (t) => { const st = $("#st"); if (st) st.textContent = t; });
}

async function sync() {
  const st = $("#syncst");
  const say = (t) => { if (st) st.textContent = t; };
  try {
    const up = await drive.push(say, renderPage);
    const down = await drive.pull(say);
    say(`Listo: ${down} clase(s) traída(s) de Drive y ${up} subida(s).`);
    store.set("lastSync", Date.now());
    if (S.tab === "clases") setTimeout(renderClases, 1200);
  } catch (e) { say("No pude sincronizar: " + e.message); }
}

// ── Repasar ──
async function renderRepasar() {
  const all = repaso.cards(await store.allClasses());
  const st = repaso.stats(all);
  const subs = [...new Set(all.map((c) => c.materia))];
  const pending = repaso.due(all, S.repasoSub || null);
  view.replaceChildren(h(`
    <div class="card"><div class="row"><div><div class="timer">${st.today}</div><div class="muted">para repasar hoy</div></div>
      <div><div class="timer">${st.learned}/${st.total}</div><div class="muted">tarjetas aprendidas</div></div></div>
      ${subs.length > 1 ? `<label>Materia</label><select id="rsub"><option value="">Todas</option>${subs.map((s) => `<option${s === S.repasoSub ? " selected" : ""}>${escapeHtml(s)}</option>`).join("")}</select>` : ""}</div>
    <div id="deck"></div>`));
  if ($("#rsub")) $("#rsub").onchange = (e) => { S.repasoSub = e.target.value || null; renderRepasar(); };
  const deck = $("#deck");
  if (!all.length) return deck.appendChild(h('<div class="card"><p class="muted">Las preguntas de autoevaluación de tus apuntes aparecen acá como tarjetas.</p></div>'));
  if (!pending.length) return deck.appendChild(h('<div class="card"><h2>🎉 Nada para hoy</h2><p class="muted">Volvé mañana: las tarjetas vuelven cuando estás por olvidarlas.</p></div>'));
  const card = pending[0];
  const el = h(`<div class="card qcard"><div class="muted"></div><div class="q"></div><div class="answer hidden" id="a"></div>
    <button class="btn primary big" id="show">Ver la respuesta</button>
    <div class="row hidden" id="rate"><button class="btn" id="no">😕 No la sabía</button><button class="btn primary" id="yes">✅ La sabía</button></div></div>`).firstElementChild;
  $(".muted", el).textContent = `${pending.length} por repasar · ${card.clase.slice(19)}`;
  $(".q", el).textContent = card.q;
  $("#a", el).innerHTML = mdToHtml(card.a);
  $("#show", el).onclick = () => { $("#a", el).classList.remove("hidden"); $("#show", el).classList.add("hidden"); $("#rate", el).classList.remove("hidden"); };
  $("#no", el).onclick = () => { repaso.answer(card, false); renderRepasar(); };
  $("#yes", el).onclick = () => { repaso.answer(card, true); renderRepasar(); };
  deck.appendChild(el);
}

// ── Dictar y notas rápidas ──
function renderDictar() {
  const hist = store.get("dictados", []);
  view.replaceChildren(h(`
    <button class="hold" id="hold"><span>🎙</span>Mantené apretado y hablá</button>
    <div class="card hidden" id="out"><div id="otext"></div><button class="btn primary big" id="copy">📋 Copiar</button></div>
    <div class="card"><h2>Dictar en cualquier app</h2><p class="muted">${android() ? 'Activá el «Teclado FlowLite»: tiene el botón para dictar en WhatsApp, mail o lo que sea. Si hay texto seleccionado, lo que digas es una orden sobre ese texto («hacelo más formal»). <button class="btn" id="kbset" style="margin-top:8px">⌨️ Activar el teclado</button>' :
      /iphone|ipad/i.test(navigator.userAgent) ? `En iPhone: armá el Atajo «FlowLite Dictar» y activalo tocando dos veces la parte de atrás del celular. <a href="${C.iphoneGuide}" target="_blank" style="color:var(--accent2)">Ver cómo</a>.` :
      `En Android: instalá la app FlowLite y usá su teclado. <a href="${C.androidApk}" target="_blank" style="color:var(--accent2)">Bajar la app</a>.`}</p></div>
    <div class="card"><h2>Notas rápidas</h2><textarea id="quick" placeholder="Se guarda sola."></textarea></div>
    <div class="card"><h2>Últimos dictados</h2><div id="hist">${hist.length ? "" : '<p class="muted">Todavía nada.</p>'}</div></div>`));
  if ($("#kbset")) $("#kbset").onclick = () => window.FlowLiteAndroid.openKeyboardSettings();
  for (const d of hist.slice(0, 20)) {
    const p = h('<p style="margin:6px 0"></p>').firstElementChild;
    p.textContent = d.text;
    p.onclick = () => copy(d.text);
    $("#hist").appendChild(p);
  }
  $("#quick").value = store.get("quick", "");
  $("#quick").oninput = (e) => store.set("quick", e.target.value);
  const btn = $("#hold");
  let rec = null;
  const down = async (e) => {
    e.preventDefault();
    if (!keysOk()) return toast("Cargá tu clave de Groq en Ajustes.");
    btn.classList.add("on"); btn.lastChild.textContent = "Escuchando… soltá para terminar";
    rec = new QuickRecorder();
    try { await rec.start(); } catch (err) { rec = null; btn.classList.remove("on"); toast("Sin permiso de micrófono"); }
  };
  const up = async () => {
    if (!rec) return;
    const r = rec; rec = null;
    btn.classList.remove("on"); btn.lastChild.textContent = "⏳ Transcribiendo…";
    try {
      const blob = await r.stop();
      let text = (await ai.transcribe(blob, { prompt: ai.dictationPrompt() })).text.trim();
      text = ai.promptEcho(text) ? "" : ai.fixTech(text);
      if (text.split(/\s+/).length > 3) text = await ai.polish(text).catch(() => text);
      if (text) {
        store.set("dictados", [{ text, at: Date.now() }, ...hist].slice(0, 50));
        $("#otext").textContent = text;
        $("#out").classList.remove("hidden");
        $("#copy").onclick = () => copy(text);
        copy(text, true);
      }
    } catch (err) { toast("No pude transcribir: " + err.message, 6000); }
    btn.lastChild.textContent = "Mantené apretado y hablá";
  };
  btn.addEventListener("pointerdown", down);
  btn.addEventListener("pointerup", up);
  btn.addEventListener("pointerleave", up);
  btn.addEventListener("pointercancel", up);
}

async function copy(text, quiet = false) {
  try { await navigator.clipboard.writeText(text); if (!quiet) toast("Copiado"); else toast("Copiado: pegalo donde quieras"); }
  catch { if (!quiet) toast("Mantené apretado el texto para copiarlo"); }
}

// ── Ajustes ──
function renderAjustes() {
  view.replaceChildren(h(`
    <div class="card"><h2>Claves</h2>
      <p class="muted">Quedan solo en este celular. Groq es gratis: <a href="https://console.groq.com/keys" target="_blank" style="color:var(--accent2)">console.groq.com/keys</a>.
      Gemini (opcional, mejores apuntes): <a href="https://aistudio.google.com/apikey" target="_blank" style="color:var(--accent2)">aistudio.google.com/apikey</a>.</p>
      <label>Clave de Groq</label><input id="kgroq" type="password" autocomplete="off" placeholder="gsk_…">
      <label>Clave de Gemini (opcional)</label><input id="kgem" type="password" autocomplete="off">
      <button class="btn primary big" id="savek">Guardar y probar</button><p class="muted" id="kst"></p></div>
    <div class="card"><h2>Google Drive</h2><p class="muted" id="dst"></p><button class="btn big" id="dconn">☁️ ${drive.connected() ? "Volver a conectar" : "Conectar Google Drive"}</button></div>
    <div class="card"><h2>Idioma y vocabulario</h2>
      <label>Idioma en que hablás</label><select id="lang"><option value="es">Español</option><option value="auto">Detectar</option><option value="en">English</option><option value="pt">Português</option></select>
      <label>Palabras que tiene que escribir bien (separadas por coma)</label><textarea id="vocab" placeholder="Horngren, prorrateo, CMgU"></textarea></div>
    <div class="card"><h2>Instalar</h2><p class="muted" id="inst"></p><button class="btn big hidden" id="instb">📲 Instalar FlowLite</button></div>
    <div class="card"><p class="muted">FlowLite ${C.version} · <a href="${C.androidApk}" target="_blank" style="color:var(--accent2)">App de Android</a> ·
      <a href="${C.iphoneGuide}" target="_blank" style="color:var(--accent2)">Dictado en iPhone</a></p>
      <button class="btn danger" id="wipe">Borrar todo del celular</button></div>`));
  $("#kgroq").value = store.get("groq", "");
  $("#kgem").value = store.get("gemini", "");
  $("#savek").onclick = async () => {
    const g = $("#kgroq").value.trim(), m = $("#kgem").value.trim();
    $("#kst").textContent = "Probando…";
    const okg = g ? await ai.keyOk("groq", g) : null, okm = m ? await ai.keyOk("gemini", m) : null;
    if (okg === false) return ($("#kst").textContent = "❌ Esa clave no funciona en Groq (empieza con gsk_).");
    if (okm === false) return ($("#kst").textContent = "❌ Esa clave no funciona en Gemini.");
    store.set("groq", g); store.set("gemini", m);
    if (window.FlowLiteAndroid && window.FlowLiteAndroid.saveKeys) window.FlowLiteAndroid.saveKeys(g, m);
    $("#kst").textContent = `✅ Guardadas.${okg === null && g ? " (No pude comprobar Groq: ¿sin internet?)" : ""}${m ? " Apuntes con Gemini." : " Apuntes con Groq."}`;
  };
  $("#dst").textContent = drive.connected() ? "✅ Conectado. Las clases se sincronizan con la carpeta FlowLite/Apuntes de tu Drive." :
    drive.configured() ? "Conectalo para ver las clases de la PC y mandarle las del celular." :
      "Falta configurar el acceso a Drive (una vez, ver docs/GUIA.md → «Google Cloud»).";
  $("#dconn").onclick = async () => { try { await drive.connect(); renderAjustes(); toast("☁️ Google Drive conectado"); } catch (e) { toast(e.message, 6000); } };
  $("#lang").value = store.get("language", "es");
  // el teclado de Android usa el mismo idioma y vocabulario
  const toKeyboard = () => window.FlowLiteAndroid && window.FlowLiteAndroid.saveSettings &&
    window.FlowLiteAndroid.saveSettings(store.get("language", "es"), store.get("vocab", []).join(", "));
  $("#lang").onchange = (e) => { store.set("language", e.target.value); toKeyboard(); };
  $("#vocab").value = store.get("vocab", []).join(", ");
  $("#vocab").onchange = (e) => { store.set("vocab", e.target.value.split(",").map((s) => s.trim()).filter(Boolean)); toKeyboard(); };
  const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  $("#inst").textContent = standalone ? "✅ Ya está instalada." : /iphone|ipad/i.test(navigator.userAgent) ?
    "En Safari: tocá Compartir (el cuadrado con la flecha) → «Agregar a inicio»." : "Instalala para usarla como una app, sin abrir el navegador.";
  if (S.installEvt && !standalone) { $("#instb").classList.remove("hidden"); $("#instb").onclick = () => S.installEvt.prompt(); }
  $("#wipe").onclick = async () => {
    if (!confirm("¿Borrar todas las clases, claves y ajustes de este celular? (En Drive y en la PC no se borra nada)")) return;
    for (const c of await store.allClasses()) await store.deleteClass(c.id);
    localStorage.clear();
    location.reload();
  };
}

// ── arranque ──
window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); S.installEvt = e; });
if ("serviceWorker" in navigator && !C.mock) {
  navigator.serviceWorker.register("sw.js").then((reg) => {
    reg.addEventListener("updatefound", () => {
      const nw = reg.installing;
      nw.addEventListener("statechange", () => {
        if (nw.state === "installed" && navigator.serviceWorker.controller) {
          const d = h('<div class="toast">Hay una versión nueva de FlowLite. <button class="btn primary" id="upd">Actualizar</button></div>').firstElementChild;
          document.body.appendChild(d);
          $("#upd", d).onclick = () => location.reload();
        }
      });
    });
  });
}

(async () => {
  await ai.loadPrompts();
  S.template = await (await fetch("shared/page.html")).text();
  if (C.mock && params.get("seed")) { // pruebas: claves falsas + clases del Drive simulado, y abrir una pantalla
    store.set("groq", "gsk_prueba"); store.set("gemini", "prueba");
    await drive.connect();
    await drive.pull();
    window.flowlite = { S, store, ai, drive, repaso, go };
    go(params.get("tab") || "clases");
    if (params.get("open")) openViewer((await store.allClasses())[+params.get("open") - 1]);
    if (params.get("show")) setTimeout(() => $("#show") && $("#show").click(), 300);
    return;
  }
  const unfinished = (await store.allClasses()).filter((c) => !c.md && (c.segments || []).length > 3);
  go(unfinished.length ? "clases" : keysOk() ? "grabar" : "ajustes");
  if (unfinished.length) toast(`🧩 Tenés ${unfinished.length} clase(s) sin apuntes armados: tocá «Armar apuntes».`, 6000);
  if (drive.connected() && Date.now() - store.get("lastSync", 0) > 10 * 60e3) sync();
  window.flowlite = { S, store, ai, drive, repaso, go }; // para pruebas automáticas
})();
