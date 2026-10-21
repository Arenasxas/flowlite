"""Mejoras de apuntes: tipos de llamada, detección por micrófono, revisión de completitud, continuación de Gemini,
PDF, clase sin terminar. Sin claves reales (todo simulado salvo el PDF, que usa el Edge de Windows)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import flowlite as fl

# Títulos genéricos (se reemplazan por uno sacado de la clase)
for t in ("", "Clase", "Reunión", "Llamada de WhatsApp", "llamada de discord", "Clase 3"):
    assert fl.generic_title(t), t
for t in ("Costos y Precios", "Estadística — clase 8", "Consulta con el contador"):
    assert not fl.generic_title(t), t
print("Títulos OK")

# Detección de llamadas por el micrófono (registro simulado)
fake = lambda: [("5319275A.WhatsAppDesktop_cv1g1gvanyjgm", 0), ("C:#FlowLite#FlowLite.exe", 0),
                ("C:#ProgramData#usuario#WisprFlow#app-1.6.1209#Wispr Flow.exe", 0),
                ("C:#Users#usuario#AppData#Local#Discord#app-1.0.9238#Discord.exe", 1234),
                ("C:#Program Files (x86)#Overwatch#_retail_#Overwatch.exe", 0)]
assert fl.apps_using_mic(fake) == {"WhatsApp": "llamada"}, fl.apps_using_mic(fake)
assert isinstance(fl.apps_using_mic(), dict)  # el registro real se puede leer
print("Micrófono OK; ahora mismo:", fl.apps_using_mic())

# Tipos de apunte
for kind, must in (("clase", "## Autoevaluación"), ("reunion", "## Próximos pasos"), ("llamada", "## Datos clave"),
                   ("charla", "## Recursos mencionados")):
    pr = fl.final_prompt(kind).format(title="T", date="D", duration="1", detail="x", extra="")
    assert must in pr and "::: formula" in pr and "nunca LaTeX" in pr, kind
assert "Decisiones tomadas" not in fl.final_prompt("clase")
print("Tipos OK:", list(fl.NOTE_TYPES))

# LaTeX con \( \)
assert fl.clean_math(r"Ejemplo: \(500 \times 500 = 250\,000\) pesos") == "Ejemplo: 500 × 500 = 250 000 pesos", \
    fl.clean_math(r"Ejemplo: \(500 \times 500 = 250\,000\) pesos")
print("LaTeX \\( \\) OK")

# Revisión de completitud
orig = "# Clase\n- uno\n- dos"
fl.gemini_chat = lambda *a, **k: "# Clase\n- uno\n- dos\n- tres (agregado)"
assert fl.review_notes(orig, [(0, "x")], [], [], "", 1000, print).endswith("(agregado)")
fl.gemini_chat = lambda *a, **k: "# Clase"
assert fl.review_notes(orig, [(0, "x")], [], [], "", 1000, print) == orig  # más corta: se descarta
def boom(*a, **k): raise RuntimeError("429")
fl.gemini_chat = boom
assert fl.review_notes(orig, [(0, "x")], [], [], "", 1000, print) == orig  # falla: quedan los de antes
print("Revisión OK")

# Continuación cuando Gemini se corta por largo
import importlib
fl2 = importlib.reload(fl)
calls = []
class R:
    def __init__(self, data): self.data, self.status_code, self.ok, self.text = data, 200, True, ""
    def json(self): return self.data
replies = [{"candidates": [{"content": {"parts": [{"text": "primera mitad "}]}, "finishReason": "MAX_TOKENS"}]},
           {"candidates": [{"content": {"parts": [{"text": "segunda mitad"}]}, "finishReason": "STOP"}]}]
class H:
    def post(self, url, **kw):
        calls.append(kw["json"]["contents"])
        return R(replies[len(calls) - 1])
fl2.http = lambda: H()
fl2.GEMINI_KEY = "x"
assert fl2.gemini_chat("s", "u") == "primera mitad segunda mitad"
assert len(calls) == 2 and calls[1][1]["role"] == "model" and "Seguí" in calls[1][2]["parts"][0]["text"]
print("Continuación OK")

# PDF real con Edge
tmp = tempfile.mkdtemp()
html_path = os.path.join(tmp, "Apuntes.html")
md = "# Prueba\n::: pregunta ¿Cuánto es 2+2?\n4\n:::\n::: formula Suma\nA + B\nPara qué: sumar\n:::"
open(html_path, "w", encoding="utf-8").write(fl2.page_html("Prueba", fl2.md_to_html(md)))
t0 = time.time()
pdf = fl2.make_pdf(html_path)
assert pdf and os.path.getsize(pdf) > 5000, pdf
assert not os.path.exists(os.path.join(tmp, "Apuntes.imprimir.html"))
print(f"PDF OK ({os.path.getsize(pdf) // 1024} KB, {time.time() - t0:.1f}s)")

# Clase sin terminar
fl2.CONFIG["notes_dir"] = tmp2 = tempfile.mkdtemp()
a = os.path.join(tmp2, "2026-10-20 18.00 - Estadistica"); os.makedirs(a)
open(os.path.join(a, "transcripcion.txt"), "w", encoding="utf-8").write("\n".join(f"[{i:02d}:00] La covarianza mide la relación entre dos variables y su signo indica la dirección." for i in range(12)))
b = os.path.join(tmp2, "2026-10-20 19.00 - Saludos"); os.makedirs(b)
open(os.path.join(b, "transcripcion.txt"), "w", encoding="utf-8").write("[00:01] Hola.\n[00:02] Buenas.")
c = os.path.join(tmp2, "2026-10-19 10.00 - Terminada"); os.makedirs(c)
open(os.path.join(c, "transcripcion.txt"), "w", encoding="utf-8").write(open(os.path.join(a, "transcripcion.txt"), encoding="utf-8").read())
open(os.path.join(c, "Apuntes.html"), "w").close()
assert fl2.unfinished_classes() == [a], fl2.unfinished_classes()
print("Clase sin terminar OK")
print("F2 OK")
