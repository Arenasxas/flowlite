"""Prueba con Groq real. Uso: python tests/test_real_groq.py <carpeta con .env> <carpeta de audios>"""
import os, sys, time, wave
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import flowlite as fl

env = dict(l.strip().split("=", 1) for l in open(os.path.join(sys.argv[1], ".env"), encoding="utf-8") if "=" in l)
fl.GROQ_KEY = env["GROQ_API_KEY"]
fl.GEMINI_KEY = env.get("GEMINI_API_KEY")
audio_dir = sys.argv[2]


def load(name):
    with wave.open(os.path.join(audio_dir, name)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32767


for name in ("dictado.wav", "corto.wav"):
    a = load(name)
    t0 = time.time(); raw = fl.groq_transcribe(a); t1 = time.time()
    polished = fl.groq_polish(raw, "whatsapp.exe — WhatsApp") if len(raw.split()) > 3 else raw
    t2 = time.time()
    print(f"{name} ({len(a)/fl.SR:.1f}s audio): Whisper {t1-t0:.2f}s · LLM {t2-t1:.2f}s")
    print("   crudo :", raw)
    print("   final :", fl.clean(polished))

# Conexión reutilizada vs nueva (3 transcripciones cortas cada una)
a = load("corto.wav")
def timed(fn):
    ts = []
    for _ in range(3):
        t = time.time(); fn(); ts.append(time.time() - t)
    return sum(ts) / len(ts)
reuse = timed(lambda: fl.groq_transcribe(a))
def fresh():
    fl._http.__dict__.clear()
    fl.groq_transcribe(a)
new = timed(fresh)
print(f"Whisper promedio: conexión reutilizada {reuse:.2f}s vs nueva {new:.2f}s")

t = time.time()
out = fl.groq_command("pasalo a formal para un mail a la profesora", "che profe no llego con el tp lo puedo mandar el lunes", "outlook.exe")
print(f"Modo comando ({time.time()-t:.2f}s):", out)
