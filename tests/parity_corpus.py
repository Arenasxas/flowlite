"""Arma el corpus para tests/parity.mjs: apuntes reales y casos difíciles, renderizados por la PC.
Uso: python tests/parity_corpus.py <salida.json> [carpetas con Apuntes.md ...]"""
import glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import flowlite as fl

HARD = {
    "sintaxis": open(os.path.join(os.path.dirname(__file__), "test_logic.py"), encoding="utf-8").read().split('h = fl.md_to_html("""')[1].split('""")')[0],
    "bloque_sin_cerrar": "::: importante Ojo\n- algo\n## Siguiente tema\ntexto\n![Diapo](capturas/00065.jpg)\n![malo](../../secreto.jpg)",
    "html_y_comillas": "<script>alert('x')</script> & \"comillas\" 'simples' y $& y $' y ==resaltado== y **negrita** y *cursiva*",
    "unicode_cursiva": "café*té* *ñandú* a*b*c 2*3*4 **ñ** _x_",
    "listas": "1. uno\n   - sub\n2. dos\n- viñeta\n\t- tab\n- [ ] tarea\n- [x] hecha\n* asterisco\n• punto",
    "tabla": "| A | B |\n|---|:--:|\n| á | → |\n| x |",
    "flechas": "a -> b => c → d ⇒ e\n::: flujo\n- uno -> dos → tres\n:::",
    "mapa": "::: mapa\n- Centro\n  - Hijo\n    - Nieto\n:::",
    "latex": r"$\frac{a}{b}$ y \(x \times y\) y \text{hola} y \$500 y PE ($) y $500 y \alpha\beta",
    "margen": ">> nota\n&gt;&gt; rara\n> cita",
    "vacios": "\n\n# Título\n\n\n---\n***\n#### Cuatro\n##### Cinco",
}
md_items = [{"name": k, "md": v} for k, v in HARD.items()]
for d in sys.argv[2:]:
    for f in glob.glob(os.path.join(d, "**", "*.md"), recursive=True):
        md_items.append({"name": os.path.relpath(f, d), "md": open(f, encoding="utf-8").read()})
for it in md_items:
    it["html"] = fl.md_to_html(it["md"])
    it["clean"] = fl.clean_math(it["md"])
junk = []
for t, avoid in (("FlowLite, WhatsApp, Groq, pádel.", []), ("Estadistica.", ["estadistica"]),
                 ("FowLite, WhatsApp. " * 8, []), ("Buenas noches, ¿cómo les va?", []),
                 ("La media es la suma de los valores dividido n.", []), ("Ñandú CAFÉ über naïve", []), ("", [])):
    junk.append({"text": t, "avoid": avoid, "junk": fl.junk_text(t, set(avoid)), "plain": fl.plain_words(t)})
clocks = [{"s": s, "out": fl.clock(s)} for s in (0, 5, 65, 599.9, 3599, 3600, 3725, 86399)]
json.dump({"md": md_items, "junk": junk, "clock": clocks}, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False)
print(f"corpus: {len(md_items)} apuntes")
