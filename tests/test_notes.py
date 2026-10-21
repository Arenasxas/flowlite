"""Prueba sin Groq real: simula las respuestas y verifica grabación, tramos, reintentos y apuntes."""
import os, sys, time, threading, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import flowlite as fl

calls = {"stt": 0, "chat": []}


class FakeResp:
    status_code = 200
    headers = {}


def fake_post(path, timeout=30, tries=1, **kw):
    if "transcriptions" in path:
        calls["stt"] += 1
        if calls["stt"] == 1:
            raise ConnectionError("sin internet (simulado)")
        assert kw["data"]["response_format"] == "verbose_json"
        return {"segments": [
            {"start": 0.5, "text": f"Hoy vemos costos fijos, tramo {calls['stt']}.", "no_speech_prob": 0.05},
            {"start": 2.0, "text": "Subtítulos realizados por la comunidad de Amara.org", "no_speech_prob": 0.1},
            {"start": 3.0, "text": "Esto entra en el parcial del 20 de noviembre.", "no_speech_prob": 0.1},
            {"start": 4.0, "text": "silencio", "no_speech_prob": 0.95}]}
    system = kw["json"]["messages"][0]["content"]
    calls["chat"].append(system[:30])
    if system.startswith("Sos un muy buen alumno"):
        return {"choices": [{"message": {"content":
            "# Costos\n*fecha · 00:20*\n\n## Resumen\nCostos **fijos** y *variables*.\n\n## Temas\n### Costos\n- uno\n  - sub\n1. primero\n\n## Tareas, fechas y avisos\n- Parcial 20/11"}}]}
    return {"choices": [{"message": {"content": "- **Costo fijo**: no varía con la producción\n- ⚠️ Parcial 20/11"}}]}


fl.groq_post = fake_post
fl.GROQ_KEY = "test"
fl.SILENCE_RMS = -1  # transcribir aunque la PC esté en silencio
tmp = tempfile.mkdtemp()
fl.CONFIG.update(notes_dir=tmp, notes_chunk_seconds=4, notes_section_minutes=0.1)

for source in ("pc", "both"):
    calls["stt"] = 0
    texts, statuses, done = [], [], threading.Event()
    result = {}
    n = fl.ClassNotes("Costos y Precios: clase 8", source, texts.append, statuses.append,
                      lambda p: (result.setdefault("path", p), done.set()))
    time.sleep(6)
    n.mark()
    time.sleep(7)
    n.stop("Mi nota: repasar punto de equilibrio")
    assert done.wait(60), "no terminó"
    path = result["path"]
    print(source, "→", path, "| stt calls", calls["stt"], "| status:", statuses[-1:])
    assert path and os.path.exists(path), statuses
    files = sorted(os.listdir(n.folder))
    print("  archivos:", files)
    assert "transcripcion.txt" in files and "Apuntes.md" in files and "mis_notas.txt" in files
    assert not [f for f in files if f.startswith("pendiente_")], "quedó audio pendiente"
    tr = open(os.path.join(n.folder, "transcripcion.txt"), encoding="utf-8").read()
    assert "Amara" not in tr and "silencio" not in tr and "⭐ MARCA" in tr, tr
    page = open(path, encoding="utf-8").read()
    assert "<h2>Resumen</h2>" in page and "<strong>fijos</strong>" in page and "<em>variables</em>" in page
    assert "<ul>" in page and "<ol>" in page and "Transcripción completa" in page
    segs, marks, doubts = fl.read_transcript(n.folder)
    assert segs and len(marks) == 1, (segs, marks)
    print("  segmentos", len(segs), "marcas", marks, "llamadas LLM", len(calls["chat"]))

# Rehacer apuntes desde la carpeta (incluye un pendiente_*.wav)
import numpy as np
with open(os.path.join(n.folder, "pendiente_00099.wav"), "wb") as f:
    f.write(fl.wav_bytes(np.random.uniform(-0.2, 0.2, fl.SR * 2).astype(np.float32)))
calls["stt"] = 5
p2 = fl.redo_notes(n.folder, print)
assert os.path.exists(p2) and not os.path.exists(os.path.join(n.folder, "pendiente_00099.wav"))
print("redo OK", p2)
# Gemini: una sola llamada con la transcripción entera; si falla, vuelve a Groq
fl.GEMINI_KEY = "x"
seen = {}
fl.gemini_chat = lambda system, user, **k: seen.setdefault("user", user) and "# Gemini\n## Resumen\nok"
p3 = fl.redo_notes(n.folder, print)
assert "TRANSCRIPCIÓN COMPLETA" in seen["user"] and "⭐" in seen["user"] and "Gemini" in open(p3, encoding="utf-8").read()
def boom(*a, **k): raise RuntimeError("cuota")
fl.gemini_chat = boom
p4 = fl.redo_notes(n.folder, print)
assert "Costos" in open(p4, encoding="utf-8").read()
print("Gemini OK (y vuelta a Groq si falla)")
shutil.rmtree(tmp)
print("TODO OK")
