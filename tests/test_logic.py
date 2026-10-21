import os, sys, time, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import flowlite as fl

# Teclas: mantener, 2 toques (fija), 3 toques (pausa), atajo de otra app
log = []
active = {"on": True}
t = fl.TapKeys(lambda: log.append("start"), lambda: log.append("stop"), lambda: log.append("cancel"),
               lambda: log.append("pause"), lambda: active["on"])
t.down(0); t.up(1.0)
assert log == ["start", "stop"], log
log.clear()
now = time.time()
t.down(now); t.up(now + 0.1); t.down(now + 0.2); t.up(now + 0.3)
time.sleep(0.6)
assert log == ["start"] and t.latched, (log, t.latched)
t.down(time.time() + 5); t.up(time.time() + 5.1)
assert log == ["start", "stop"], log
log.clear()
now = time.time() + 20
for i in range(3):
    t.down(now + i * 0.2); t.up(now + i * 0.2 + 0.1)
time.sleep(0.6)
assert log == ["start", "cancel", "pause"], log
log.clear()
t.down(now + 30); t.abort(); t.up(now + 31)
assert log == ["start", "cancel"], log
print("TapKeys OK")

# Detección de reuniones
yes = ["Meet - abc-defg-hij - Google Chrome", "Meet – Costos y Precios - Google Chrome", "Zoom Meeting",
       "Reunión con Juan | Microsoft Teams", "Meet: Clase 8 - Microsoft​ Edge", "Sala - BigBlueButton - Google Chrome"]
no = ["Google Meet - Google Chrome", "Chat | General | Microsoft Teams", "Zoom Workplace", "WhatsApp", "Meeting notes.docx - Word"]
for s in yes:
    assert fl.MEETING_RX.search(s), s
for s in no:
    assert not fl.MEETING_RX.search(s), s
assert fl.meeting_name("Meet – Costos y Precios - Google Chrome") == "Costos y Precios", fl.meeting_name("Meet – Costos y Precios - Google Chrome")
assert fl.meeting_name("Meet - abc-defg-hij - Google Chrome") == ""
assert fl.meeting_name("Reunión con Juan | Microsoft Teams") == "Reunión con Juan"
print("Reuniones OK; ventanas visibles ahora:", fl.detect_meeting())

# Atajos de voz
fl.SNIPPETS_PATH = os.path.join(tempfile.mkdtemp(), "snippets.json")
assert fl.snippet_for("mi mail") is None
EX = {"mi mail": "yo@ejemplo.com", "mi dirección": "Calle Falsa 123"}
fl.save_snippets(EX)
assert fl.snippet_for("Mi mail.") == EX["mi mail"]
assert fl.snippet_for("Mi direccion") == EX["mi dirección"]
assert fl.snippet_for("mandale mi mail a Juan") is None
print("Atajos OK")

# Aprendizaje de correcciones y limpieza
assert fl.edits_to_learn("hablé con servi hoy", "hablé con servi hoy", "hablé con Servy hoy") == [("servi", "Servy")]
assert fl.edits_to_learn("a las cinco", "a las cinco", "a las seis") == []
assert fl.clean("eh  hola   mmm che") == "hola che", repr(fl.clean("eh  hola   mmm che"))
assert fl.clock(65) == "01:05" and fl.clock(3725) == "1:02:05"
print("App activa:", fl.foreground_app())
print("TODO OK")

# Eco de la ayuda y bucles (casos reales de la clase de Estadística)
for junk in ["FlowLite, WhatsApp, Groq, pádel.", "FlowLite, WhatsApp.", "Estadistica.",
             "FowLite, WhatsApp. FowLite, WhatsApp. FowLite, WhatsApp. FowLite, WhatsApp. FowLite, WhatsApp. FowLite, WhatsApp."]:
    assert fl.junk_text(junk, {"estadistica"}), junk
for ok in ["Buenas noches, ¿cómo les va?", "Voy a tomar asistencia.", "La media es la suma de los valores dividido n."]:
    assert not fl.junk_text(ok, {"estadistica"}), ok
assert fl.subject_key("Costos y Precios — clase 8") == fl.subject_key("Costos y Precios - Clase 9") == "costos y precios"
print("Filtro de eco OK")

# Cuaderno
h = fl.md_to_html("""::: formula Punto de equilibrio
PE = CF ÷ CMU
Para qué: saber cuántas unidades vender
Ejemplo: 100.000 ÷ 200 = 500
:::
>> ¡Esto lo toman siempre!
Costo fijo → no cambia con la producción y ==es clave==
::: flujo
Medir → Calcular → Decidir
:::
::: mapa
- Costos
  - Fijos
  - Variables
:::
::: pregunta ¿Qué es la CMU?
Precio − costo variable unitario.
:::
::: ojo Error común
No confundir CF con CV
:::
- [ ] Entregar TP 3
| Tipo | Ejemplo |
|---|---|
| Fijo | Alquiler |
> aviso suelto""")
for frag in ['class="formula"', 'class="f-eq">PE = CF ÷ CMU', '<span>Para qué</span>', 'aside class="margin"', 'class="ar"',
             '<mark>es clave</mark>', 'class="flujo"', 'class="mapa"', '<span class="node">Fijos</span>', 'details class="q"',
             'class="box ojo"', 'type="checkbox"', '<table>', '<td>Alquiler</td>']:
    assert frag in h, (frag, h)
assert "<script" not in fl.md_to_html("<script>alert(1)</script>")
print("Cuaderno OK")

# Restos de LaTeX que escribió Gemini en la prueba real
cases = {
    r"1. $CMgU = \$500 − \$300 = \$200$": "1. CMgU = $500 − $300 = $200",
    r"3. $PE (\$) = 500 \text{ unidades} × \$500 = \$250.000$": "3. PE ($) = 500  unidades × $500 = $250.000",
    r"(fórmula: $CFT ÷ CMgU$)": "(fórmula: CFT ÷ CMgU)",
    r"$\frac{CF}{CMU}$": "(CF) ÷ (CMU)",
    "P = $500, CVu = $300 → CMgU = $200": "P = $500, CVu = $300 → CMgU = $200",
    "PE ($) = PE (unidades) × P": "PE ($) = PE (unidades) × P",
    r"$PE \times P$": "PE × P",
}
for raw, want in cases.items():
    got = fl.clean_math(raw)
    assert got == want, (raw, got, want)
print("LaTeX OK")

# Bloque sin cerrar no se come el resto; capturas
h = fl.md_to_html("::: importante Ojo\n- algo\n## Siguiente tema\ntexto\n![Diapo](capturas/00065.jpg)\n![malo](../../secreto.jpg)")
assert "<h2>Siguiente tema</h2>" in h and h.index("</div>") < h.index("<h2>"), h
assert '<img src="capturas/00065.jpg"' in h and "secreto" not in h.split("<figure>")[-1].split("</figure>")[0] + "x"[:0]
assert '../../secreto.jpg' not in [x for x in h.split('"') if x.endswith(".jpg")], h
print("Bloques/capturas OK")
