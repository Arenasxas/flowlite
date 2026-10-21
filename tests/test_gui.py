import os, sys, time, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import flowlite as fl
from PySide6.QtWidgets import QApplication

out = sys.argv[1]
app = QApplication([])
fl.CONFIG["notes_dir"] = tempfile.mkdtemp()
fl.groq_post = lambda *a, **k: {"segments": [], "choices": [{"message": {"content": "- x"}}]}

dlg = fl.StartDialog("Costos y Precios")
dlg.move(-4000, -4000); dlg.show(); app.processEvents()
dlg.grab().save(os.path.join(out, "dialog.png"))

n = fl.ClassNotes("Costos y Precios", "pc", print, print, print)
w = fl.ClassWindow(n, n.stop)
w.move(-4000, -4000)
w.mine.setPlainText("Preguntar por el ejercicio 3\nRepasar punto de equilibrio")
w.add_text("[00:12] Hoy vamos a ver costos fijos y variables.\n[00:40] El costo fijo no depende del nivel de producción.")
w.mark()
w.set_status("Escuchando… la transcripción aparece cada ~1 minuto.")
for _ in range(20):
    app.processEvents(); time.sleep(0.05)
w.grab().save(os.path.join(out, "window.png"))

orb = fl.Orb(level=lambda: 0.0)
orb.move(-4000, -4000)
orb.set_class(True)
for _ in range(10):
    orb._tick(); app.processEvents()
orb.grab().save(os.path.join(out, "orb_class.png"))
assert orb.state == "class"
orb.set("rec"); assert orb.state == "rec"
orb.set("idle"); assert orb.state == "class"
orb.set_class(False); assert orb.state == "idle"
n.stop()
print("GUI OK")
