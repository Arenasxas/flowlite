"""Asistente con IA real. Uso: python tests/test_real_assist.py <carpeta con .env> <carpeta con clases ya armadas>"""
import os, sys, shutil, time, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import flowlite as fl

env = dict(l.strip().split("=", 1) for l in open(os.path.join(sys.argv[1], ".env"), encoding="utf-8") if "=" in l)
fl.GROQ_KEY, fl.GEMINI_KEY = env["GROQ_API_KEY"], env.get("GEMINI_API_KEY")
src = sys.argv[2]
classes = [os.path.join(src, n) for n in sorted(os.listdir(src)) if os.path.isdir(os.path.join(src, n))]
segs, _, _ = fl.read_transcript(classes[0])

t = time.time(); r = fl.live_help("recap", segs)
print(f"¿Qué me perdí? ({time.time() - t:.1f}s)\n{r}\n")
t = time.time(); q = fl.live_help("question", segs)
print(f"Pregunta para el profe ({time.time() - t:.1f}s)\n{q}\n")

t = time.time()
a = fl.ask_classes("¿Qué es el margen de seguridad y cuánto daba el ejemplo?", classes)
print(f"Preguntale a tus clases ({time.time() - t:.1f}s)\n{a}\n")
assert "37,5" in a or "37.5" in a, "no encontró el dato que estaba solo en la diapositiva"

tmp = tempfile.mkdtemp()
fl.CONFIG["notes_dir"] = tmp
t = time.time()
g = fl.study_guide(classes, "Costos y Precios", status=print)
page = open(g, encoding="utf-8").read()
n_formulas = page.count('class="formula"')
print(f"Resumen para el parcial ({time.time() - t:.1f}s): {g}  fichas de fórmula: {n_formulas}")
assert os.path.exists(g) and 'class="formula"' in page

# título automático: clase sin nombre
d = os.path.join(tmp, "2026-10-18 10.00 - Clase")
os.makedirs(d)
shutil.copy(os.path.join(classes[0], "transcripcion.txt"), d)
p = fl.redo_notes(d, print)
print("título automático →", os.path.basename(os.path.dirname(p)))
assert "Clase" != os.path.basename(os.path.dirname(p))[19:], p
shutil.copy(g, os.path.join(os.path.dirname(sys.argv[2]), "resumen_parcial.html"))
print("ASISTENTE OK")
