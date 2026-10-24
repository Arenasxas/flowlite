"""Los apuntes ignoran la música que se coló en la grabación. Clase corta + un estribillo inventado (no es de ninguna
canción real) intercalado, con Gemini real. Uso: python tests/test_real_music.py <carpeta con .env>"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import flowlite as fl

env = dict(l.strip().split("=", 1) for l in open(os.path.join(sys.argv[1], ".env"), encoding="utf-8") if "=" in l)
fl.GROQ_KEY, fl.GEMINI_KEY = env["GROQ_API_KEY"], env.get("GEMINI_API_KEY")
CLASE = ["Hoy vemos el punto de equilibrio.", "El punto de equilibrio es costos fijos dividido la contribución marginal unitaria.",
         "Si los costos fijos son cien mil pesos y la contribución marginal es doscientos, el equilibrio es quinientas unidades.",
         "La contribución marginal es el precio menos el costo variable unitario.",
         "Para el parcial del veinte de noviembre entra todo el capítulo cuatro."]
CORO = ["Luna de neón, bailo sin control", "Esta noche no hay razón, luna de neón", "Bailo sin control, sin control",
        "Dame tu calor, luna de neón"]
segs, t = [], 0
for i, line in enumerate(CLASE):
    segs.append((t, line)); t += 20
    for c in CORO[i % 2::2]:
        segs.append((t, c)); t += 4
folder = tempfile.mkdtemp()
os.makedirs(os.path.join(folder, "x"), exist_ok=True)
path = fl.build_notes(folder, "Costos y Precios", segs, [], "", prefs={"type": "clase", "detail": "resumido"})
md = open(os.path.join(os.path.dirname(path), "Apuntes.md"), encoding="utf-8").read().lower()  # la carpeta se renombra con el título
leaks = [w for w in ("neón", "neon", "bailo", "sin control", "calor") if w in md]
keep = [w for w in ("equilibrio", "500", "noviembre") if w in md or (w == "500" and "quinientas" in md)]
print("se coló de la canción:", leaks or "nada", "· datos de la clase:", keep)
assert not leaks and len(keep) == 3
print("MÚSICA OK")
