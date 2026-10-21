"""Arranca main() de verdad con lo peligroso simulado (no escribe en tus apps, no usa tus claves).
Uso: python tests/test_main.py <carpeta de capturas>"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from types import SimpleNamespace
import keyboard, pystray
import flowlite as fl
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

out = sys.argv[1]
tmp = tempfile.mkdtemp()
fl.HERE, fl.STATE_PATH, fl.VOCAB_PATH = tmp, os.path.join(tmp, "state.json"), os.path.join(tmp, "vocabulary.json")
fl.CONFIG["notes_dir"] = os.path.join(tmp, "Apuntes")
fl.GROQ_KEY, fl.GEMINI_KEY = "x", None
fl.key_ok = lambda *a: True
fl.ctypes.windll.kernel32.GetLastError = lambda: 0  # que no choque con el FlowLite abierto
hooks, pasted, notified = [], [], []
keyboard.hook = hooks.append
keyboard.unhook_all = lambda: None
keyboard.is_pressed = lambda k: False
pystray.Icon.run_detached = lambda self: None
pystray.Icon.notify = lambda self, msg, title="": notified.append(msg)
pystray.Icon.update_menu = lambda self: None
pystray.Icon.stop = lambda self: None
fl.groq_transcribe = lambda audio: "hola esto es una prueba del panel nuevo"
fl.groq_polish = lambda text, app="": "Hola, esto es una prueba del panel nuevo."
fl.paste = lambda text: (pasted.append(text), False)[1]  # simula "no había dónde pegar"
fl.watch_edits = lambda *a: None
fl.foreground_app = lambda: "notepad.exe — Sin título"
fl.detect_meeting = lambda: "Meet – Costos y Precios - Google Chrome"
fl.save_state(orb=[-3000, -3000])
results = {}
real_exec = QApplication.exec


def find(cls):
    return next(w for w in QApplication.topLevelWidgets() if type(w).__name__ == cls)


def ev(name, kind):
    for h in hooks:
        h(SimpleNamespace(name=name, event_type=kind))


def step1():
    orb = find("Orb")
    orb.clicked.emit()
    QTimer.singleShot(600, step2)


def step2():
    panel = find("Panel")
    results["panel_visible"] = panel.isVisible()
    panel.move(-3000, -3000)
    panel.ctx.set_hotkey("f9")  # cambiar el atajo desde Ajustes
    results["label"] = panel.ctx.hotkey_label()
    ev("ctrl", "down"); ev("alt", "down"); ev("alt", "up"); ev("ctrl", "up")  # el atajo viejo ya no graba
    results["old_ignored"] = find("Orb").state != "rec"
    ev("f9", "down")
    QTimer.singleShot(900, lambda: (ev("f9", "up"), QTimer.singleShot(2500, step3)))


def step3():
    panel = find("Panel")
    rows = panel.ctx.hist.rows()
    results["hist"] = rows[:1]
    panel.go(0)
    panel.grab().save(os.path.join(out, "main_panel.png"))
    QTimer.singleShot(9000, step4)  # el detector de reuniones mira cada 8 s


def step4():
    toasts = [w for w in QApplication.topLevelWidgets() if type(w).__name__ == "MeetingToast" and w.isVisible()]
    results["toast"] = bool(toasts)
    if toasts:
        toasts[0].grab().save(os.path.join(out, "main_toast.png"))
    QApplication.quit()


def fake_exec(self=None):
    QTimer.singleShot(1500, step1)
    return real_exec()


QApplication.exec = fake_exec
fl.main()
print(results)
print("pegado (simulado):", pasted, "| avisos:", notified[-1:] if notified else [])
assert results["panel_visible"] and results["label"] == "F9" and results["old_ignored"], results
assert results["hist"] and results["hist"][0][3] == "Hola, esto es una prueba del panel nuevo." and results["hist"][0][5] == "copiado"
assert results["hist"][0][4].startswith("notepad.exe"), results["hist"]
assert results["toast"], "no apareció el aviso de reunión"
print("MAIN OK")
