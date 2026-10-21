"""Apuntes reales: mete un .wav en el pipeline de ClassNotes (sin micrófono) y usa Groq/Gemini de verdad.
Uso: python tests/test_real_notes.py <carpeta con .env> <clase.wav> <carpeta salida> [groq|gemini]"""
import os, sys, time, wave, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import flowlite as fl

env = dict(l.strip().split("=", 1) for l in open(os.path.join(sys.argv[1], ".env"), encoding="utf-8") if "=" in l)
fl.GROQ_KEY = env["GROQ_API_KEY"]
fl.GEMINI_KEY = env.get("GEMINI_API_KEY") if (sys.argv[4:] or ["gemini"])[0] == "gemini" else None
fl.CONFIG.update(notes_dir=sys.argv[3], notes_section_minutes=1)
with wave.open(sys.argv[2]) as w:
    audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32767

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication
qapp = QApplication([])
fl.ClassNotes._record = lambda self, key: None  # sin captura: el audio lo metemos a mano
statuses, done = [], threading.Event()
res = {}
t0 = time.time()
n = fl.ClassNotes("Costos y Precios — clase de prueba", "pc", lambda t: print("  vivo:", t[:90]),
                  lambda s: (statuses.append(s), print("  estado:", s)), lambda p: (res.setdefault("p", p), done.set()),
                  prefs={"detail": "normal", "extra": "Poné cada fórmula con un ejemplo numérico."})
with n.lock:
    n.bufs["pc"].append(audio)
time.sleep(1)
n.mark()
n.doubts.append(80); n._append("[01:20] ❓ DUDA")  # "no entendí" en el prorrateo
while n.offset + 1 < len(audio) / fl.SR - fl.CONFIG["notes_chunk_seconds"]:
    time.sleep(0.5)
slide = os.path.join(os.path.dirname(sys.argv[2]), "slide.png")
if os.path.exists(slide):
    print("captura en", fl.clock(n.capture(QPixmap(slide))))
n.stop("[01:25] preguntar si el prorrateo puede ser x horas hombre\n[00:50] el ej. de la pyme es igual al del TP")
done.wait(600)
print(f"Total {time.time() - t0:.1f}s · motor apuntes: {'Gemini' if fl.GEMINI_KEY else 'Groq'} · archivo: {res.get('p')}")
