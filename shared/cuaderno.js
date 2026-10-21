// Cuaderno de FlowLite en JavaScript: el mismo resultado que md_to_html / clean_math / junk_text de flowlite.py.
// Lo usa la app del celular. tests/parity.mjs verifica que el HTML sea idéntico al de Python.

const W = "\\p{L}\\p{N}_"; // \w de Python (Unicode)

export function escapeHtml(s) {
  // igual que html.escape(s, quote=True) de Python
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#x27;");
}

export function splitlines(s) {
  // como str.splitlines() de Python
  const parts = s.split(/\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]/);
  if (parts.length && parts[parts.length - 1] === "") parts.pop();
  return parts;
}

function pyStrip(s, chars) {
  if (chars === undefined) return s.replace(/^\s+|\s+$/gu, "");
  let a = 0, b = s.length;
  while (a < b && chars.includes(s[a])) a++;
  while (b > a && chars.includes(s[b - 1])) b--;
  return s.slice(a, b);
}

export const BOX_ICONS = { importante: "⚠️", ojo: "👀", ejemplo: "✏️", tip: "💡", duda: "❓", resumen: "⏱️" };
export const LATEX = {
  times: "×", div: "÷", cdot: "·", approx: "≈", leq: "≤", geq: "≥", neq: "≠", pm: "±",
  sum: "Σ", sqrt: "√", alpha: "α", beta: "β", mu: "μ", sigma: "σ", Delta: "Δ", "%": "%", rightarrow: "→",
};

export function cleanMath(md) {
  md = md.replace(/\\[()\[\]]/g, "");
  md = md.replace(/\\frac\{([^{}]*)\}\{([^{}]*)\}/g, "($1) ÷ ($2)");
  md = md.replace(/\\(?:text|mathrm|textbf|mathbf)\{([^{}]*)\}/g, "$1");
  md = md.replace(/\\([A-Za-z]+|%)/g, (m, g) => (g in LATEX ? LATEX[g] : m));
  md = md.split("\\$").join("\x00").split("($)").join("(\x00)");
  md = md.replace(/\$(?!\d)/g, "");
  return md.split("\x00").join("$").split("\\,").join(" ");
}

export function mdInline(s) {
  s = escapeHtml(s);
  s = s.replace(/==(.+?)==/g, "<mark>$1</mark>");
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(new RegExp(`(?<![${W}*])\\*(?!\\s)(.+?)(?<!\\s)\\*(?![${W}*])`, "gu"), "<em>$1</em>");
  s = s.replace(/`(.+?)`/g, "<code>$1</code>");
  return s.replace(/\s*(?:→|⇒|-&gt;|=&gt;)\s*/gu, ' <b class="ar">→</b> ');
}

export function mdBlock(kind, title, inner) {
  const lines = inner.filter((l) => pyStrip(l));
  if (kind === "formula") {
    const rows = lines.slice(1).map((l) => {
      const m = l.match(/^\s*[-*]?\s*([^:]{2,20}):\s*(.+)/u);
      return m ? `<div class="f-row"><span>${mdInline(m[1])}</span>${mdInline(m[2])}</div>` : `<p>${mdInline(pyStrip(l))}</p>`;
    });
    const eq = lines.length ? mdInline(pyStrip(lines[0])) : "";
    return `<div class="formula"><div class="f-name">📐 ${mdInline(title || "Fórmula")}</div>` +
      `<div class="f-eq">${eq}</div>${rows.join("")}</div>`;
  }
  if (kind === "flujo") {
    return lines.map((l) => {
      const steps = l.split(/→|⇒|->/).map((x) => pyStrip(x, " -*")).filter((x) => x);
      return '<div class="flujo">' + steps.map((x) => `<span class="node">${mdInline(x)}</span>`).join(' <b class="ar">→</b> ') + "</div>";
    }).join("");
  }
  if (kind === "mapa") return `<div class="mapa">${mdToHtml(inner.join("\n"), true)}</div>`;
  if (kind === "pregunta") {
    return `<details class="q"><summary>${mdInline(title || "Pregunta")}</summary>` +
      `<div class="a">${mdToHtml(inner.join("\n"))}</div></details>`;
  }
  const icon = BOX_ICONS[kind] || "📌";
  const head = title ? `<div class="box-t">${icon} ${mdInline(title)}</div>` : `<div class="box-t">${icon}</div>`;
  return `<div class="box ${escapeHtml(kind)}">${head}${mdToHtml(inner.join("\n"))}</div>`;
}

export function mdTable(rows) {
  const cells = rows.filter((r) => !/^\s*\|?[\s:|-]+\|?\s*$/u.test(r))
    .map((r) => pyStrip(pyStrip(r), "|").split("|").map((c) => pyStrip(c)));
  if (!cells.length) return "";
  const head = cells[0].map((c) => `<th>${mdInline(c)}</th>`).join("");
  const body = cells.slice(1).map((r) => "<tr>" + r.map((c) => `<td>${mdInline(c)}</td>`).join("") + "</tr>").join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

export function mdToHtml(md, node = false) {
  const out = [], lists = [];
  const lines = splitlines(md);
  const closeLists = (depth = 0) => { while (lists.length > depth) out.push(`</${lists.pop()}>`); };
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    i += 1;
    const b = line.match(/^\s*:::\s*([A-Za-záéíóúñ]+)\s*(.*)$/u);
    if (b) {
      closeLists();
      const inner = [];
      while (i < lines.length && !/^\s*:::\s*$/u.test(lines[i])) {
        if (/^#{1,3}\s/u.test(lines[i])) { i -= 1; break; }
        inner.push(lines[i]);
        i += 1;
      }
      i += 1;
      out.push(mdBlock(b[1].toLowerCase(), pyStrip(b[2]), inner));
      continue;
    }
    if (line.replace(/^\s+/u, "").startsWith("|")) {
      closeLists();
      const rows = [line];
      while (i < lines.length && lines[i].replace(/^\s+/u, "").startsWith("|")) { rows.push(lines[i]); i += 1; }
      out.push(mdTable(rows));
      continue;
    }
    const img = line.match(/^\s*!\[(.*?)\]\(((?:\.\.\/[^/\\()]+\/)?capturas\/\d{5}\.jpg)\)/u);
    if (img) {
      closeLists();
      out.push(`<figure><img src="${escapeHtml(img[2])}" alt="${escapeHtml(img[1])}" loading="lazy">` +
        `<figcaption>📸 ${mdInline(img[1])}</figcaption></figure>`);
      continue;
    }
    const mg = line.match(/^\s*&?gt;&?gt;\s*(.*)|^\s*>>\s*(.*)/u);
    if (mg) { out.push(`<aside class="margin">${mdInline(mg[1] || mg[2] || "")}</aside>`); continue; }
    const m = line.match(/^(\s*)([-*•]|\d+[.)])\s+(.*)/u);
    if (m) {
      const depth = Math.floor(m[1].split("\t").join("  ").length / 2) + 1;
      const tag = /\d/.test(m[2][0]) ? "ol" : "ul";
      closeLists(depth);
      if (lists.length === depth && lists[lists.length - 1] !== tag) closeLists(depth - 1);
      while (lists.length < depth) { lists.push(tag); out.push(`<${tag}>`); }
      const text = m[3];
      const task = text.match(/^\[( |x|X)\]\s*(.*)/u);
      if (task) {
        const done = task[1] !== " " ? " checked" : "";
        out.push(`<li class="task"><label><input type="checkbox"${done}> ${mdInline(task[2])}</label></li>`);
      } else if (node) out.push(`<li><span class="node">${mdInline(text)}</span></li>`);
      else out.push(`<li>${mdInline(text)}</li>`);
      continue;
    }
    closeLists();
    const h = line.match(/^(#{1,4})\s+(.*)/u);
    const q = line.match(/^\s*>\s?(.*)/u);
    if (h) out.push(`<h${h[1].length}>${mdInline(h[2])}</h${h[1].length}>`);
    else if (/^\s*(-{3,}|\*{3,})\s*$/u.test(line)) out.push("<hr>");
    else if (q) out.push(`<div class="box ojo">${mdInline(q[1])}</div>`);
    else if (pyStrip(line)) out.push(`<p>${mdInline(pyStrip(line))}</p>`);
  }
  closeLists();
  return out.join("\n");
}

// ── filtros de la transcripción (iguales a los de la PC) ──
export const DEFAULT_VOCAB = new Set(["flowlite", "whatsapp", "groq", "padel"]);
export const HALLUCINATIONS = new RegExp(
  "amara\\.org|subt[ií]tulos (realizados|por|hechos)|suscr[ií]b[ae]te|gracias por (ver|mirar)|" +
  "^[^\\p{L}\\p{N}_]*(m[uú]sica|aplausos)[^\\p{L}\\p{N}_]*$", "iu");

export function plainWords(s) {
  s = s.toLowerCase().normalize("NFD").replace(/[^\x00-\x7f]/g, "");
  return (s.match(/\w+/g) || []).join(" ");
}

export function junkText(text, avoid = new Set()) {
  const words = plainWords(text).split(" ").filter(Boolean);
  if (!words.length || words.every((w) => avoid.has(w) || DEFAULT_VOCAB.has(w))) return true;
  return words.length >= 12 && new Set(words).size / words.length < 0.3;
}

export function clock(sec) {
  sec = Math.floor(sec);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const p = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${p(m)}:${p(s)}` : `${p(m)}:${p(s)}`;
}

export function pageHtml(template, title, body, transcript = "", version = "") {
  // como page_html de Python: str.replace reemplaza todas las apariciones y sin interpretar "$&"
  const rep = (s, a, b) => s.split(a).join(b);
  return rep(rep(rep(rep(template, "%%TITLE%%", title), "%%VERSION%%", version), "%%TRANSCRIPT%%", transcript), "%%BODY%%", body);
}
