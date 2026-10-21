// Paridad del cuaderno: el HTML que arma la app del celular (shared/cuaderno.js) tiene que ser idéntico
// al de la PC (flowlite.py). Uso: node tests/parity.mjs <corpus.json>   (corpus = salida de tests/parity_corpus.py)
import { readFileSync } from "node:fs";
import { mdToHtml, cleanMath, junkText, plainWords, clock } from "../shared/cuaderno.js";

const corpus = JSON.parse(readFileSync(process.argv[2], "utf8"));
let bad = 0;
const check = (kind, name, got, want) => {
  if (got !== want) {
    bad++;
    let i = 0;
    while (i < got.length && got[i] === want[i]) i++;
    console.log(`DIFIERE ${kind} ${name} en ${i}:\n  js: ${JSON.stringify(got.slice(Math.max(0, i - 60), i + 80))}\n  py: ${JSON.stringify(want.slice(Math.max(0, i - 60), i + 80))}`);
  }
};
for (const c of corpus.md) {
  check("html", c.name, mdToHtml(c.md), c.html);
  check("latex", c.name, cleanMath(c.md), c.clean);
}
for (const c of corpus.junk) {
  check("junk", c.text, String(junkText(c.text, new Set(c.avoid))), String(c.junk));
  check("plain", c.text, plainWords(c.text), c.plain);
}
for (const c of corpus.clock) check("clock", String(c.s), clock(c.s), c.out);
console.log(bad ? `${bad} diferencias` : `PARIDAD OK (${corpus.md.length} apuntes, ${corpus.junk.length} frases, ${corpus.clock.length} horas)`);
process.exit(bad ? 1 : 0);
