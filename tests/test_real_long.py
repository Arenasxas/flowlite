"""Completitud con una clase real larga (transcripción de Wispr Flow de la clase de Estadística, 47 min).
Uso: python tests/test_real_long.py <carpeta con .env> <transcripcion.txt> <carpeta salida> [detalle]
Mide cuántos de los datos clave que dio el profe aparecen en los apuntes."""
import os, re, sys, time, unicodedata
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import flowlite as fl

# Datos concretos que dio el profe (sacados de la transcripción). Cada uno: (nombre, regex sobre el texto normalizado)
FACTS = [
    ("covarianza 16.5", r"16[.,]5"), ("promedio x 22.5", r"22[.,]5"), ("promedio y 3.5", r"3[.,]5\b"),
    ("varianza x 87.5", r"87[.,]5"), ("varianza y 4.7", r"4[.,]7\b"), ("desvio x 9.35", r"9[.,]35"),
    ("desvio y 2.17", r"2[.,]17"), ("producto desvios 20.29", r"20[.,]29"), ("r 0.81", r"0[.,]81"),
    ("umbral 0.80 fuerte", r"0[.,]8\b|0[.,]80"), ("debil hasta 0.79", r"0[.,]79"),
    ("r mismo signo que cov", r"mismo signo"), ("pendiente 0.19", r"0[.,]19"), ("ordenada -0.77", r"0[.,]77"),
    ("estimacion 46.15", r"46[.,]15"), ("despeje 8.77", r"8[.,]77"),
    ("n-1 muestra / n poblacion", r"poblaci"), ("serie simple sin frecuencia", r"serie simple"),
    ("formula pendiente cov/var", r"pendiente"), ("ordenada = ybar - b xbar", r"ordenada"),
    ("P(alta|capital)=0.666", r"0[.,]66"), ("palabras clave siendo que/o/y", r"siendo que|dado que"),
    ("mutuamente excluyentes", r"mutuamente excluyentes"), ("probabilidad 1 evento cierto", r"cierto"),
    ("no porcentaje", r"porcentaje"), ("asimetria derecha 305/300", r"305"), ("desvio 121.84", r"121[.,]84"),
    ("parcial miercoles 18 hs", r"18[:.]?00|18 ?h"), ("sin formulas, memorizar", r"memoriz|sin (ninguna )?formula"),
    ("sumando punto 21:40", r"21[:.]40"), ("calculadora", r"calculadora"),
]


def norm(t):
    return unicodedata.normalize("NFD", t.lower()).encode("ascii", "ignore").decode()


def score(text):
    t = norm(text)
    hits = [n for n, rx in FACTS if re.search(rx, t)]
    return hits, [n for n, _ in FACTS if n not in hits]


if __name__ == "__main__":
    env = dict(l.strip().split("=", 1) for l in open(os.path.join(sys.argv[1], ".env"), encoding="utf-8") if "=" in l)
    fl.GROQ_KEY, fl.GEMINI_KEY = env["GROQ_API_KEY"], env.get("GEMINI_API_KEY")
    lines = [l.strip() for l in open(sys.argv[2], encoding="utf-8") if l.strip()]
    total, dur, pos, segs = sum(len(l) for l in lines), 47 * 60, 0, []
    for l in lines:  # minuto aproximado según cuánto texto va
        segs.append((pos / total * dur, re.sub(r"^Speaker (\d+):\s*", lambda m: "Profe: " if m.group(1) == "1" else "Alumno: ", l)))
        pos += len(l)
    detail = sys.argv[4] if len(sys.argv) > 4 else "normal"
    out = sys.argv[3]
    folder = os.path.join(out, f"2026-09-18 20.16 - Estadistica ({detail})")
    os.makedirs(folder, exist_ok=True)
    t0 = time.time()
    path = fl.build_notes(folder, "Estadistica", segs, [], "", prefs={"detail": detail, "extra": ""}, status=print)
    md = open(os.path.join(os.path.dirname(path), "Apuntes.md"), encoding="utf-8").read()
    hits, miss = score(md)
    print(f"FlowLite ({detail}, {time.time() - t0:.0f}s, {len(md.split())} palabras): {len(hits)}/{len(FACTS)}")
    print("  faltan:", miss)
    print("  fichas de fórmula:", md.count("::: formula"), "· preguntas:", md.count("::: pregunta"))
