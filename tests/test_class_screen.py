"""Diálogo de inicio y ventana de clase EN PANTALLA (captura lo que ve el usuario): normal, con marcas, ayuda,
aviso de silencio, modo mini y terminado. Sin grabar audio real. Uso: python tests/test_class_screen.py <carpeta>"""
import os, sys, time, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication
import flowlite as fl

out = sys.argv[1]
app = QApplication([])
fl.CONFIG["notes_dir"] = tempfile.mkdtemp()
for n in ("2026-10-20 18.00 - Régimen Legal dia 20102026", "2026-10-17 21.32 - Costos y Precios — clase 8",
          "2026-10-16 19.00 - Estadística", "2026-10-15 10.00 - Clase"):
    os.makedirs(os.path.join(fl.CONFIG["notes_dir"], n.replace("/", "-")))


def settle(sec=0.5):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def shot(w, name):
    settle()
    g = w.frameGeometry()
    scr = QApplication.screenAt(g.center()) or QApplication.primaryScreen()
    pad = 20
    scr.grabWindow(0, g.x() - scr.geometry().x() - pad, g.y() - scr.geometry().y() - pad,
                   g.width() + 2 * pad, g.height() + 2 * pad).save(os.path.join(out, f"cls_{name}.png"))


geo = QApplication.primaryScreen().availableGeometry()
rec = fl.recent_subjects()
assert rec[:3] == ["Régimen Legal", "Costos y Precios", "Estadística"], rec  # sin fecha, sin «Clase» genérica
d = fl.StartDialog("Google Meet", "clase")
assert d.title.text() == "", d.title.text()
d.move(geo.center().x() - 280, geo.top() + 40)
d.show()
shot(d, "1_inicio")
d.title.setText("Costos y Precios")
d.extra.show()
d.extra.setPlainText("El prorrateo de la cátedra es por horas máquina")
d.source.select("both")
shot(d, "2_inicio_eligiendo")
assert d.source.currentData() == "both" and d.kind.currentData() == "clase" and d.detail.currentData() == "normal"
d.close()


class FakeNotes:
    """Lo que la ventana usa de ClassNotes, sin grabar."""
    def __init__(self):
        import threading
        self.title, self.source, self.prefs, self.folder = "Régimen Legal", "pc", {"type": "clase"}, fl.CONFIG["notes_dir"]
        self.stop_ev, self.segments, self.my_notes, self.levels, self.t0, self.paused = threading.Event(), [], "", {"pc": 0.02}, time.time() - 754, False
    def elapsed(self): return time.time() - self.t0
    def mark(self, doubt=False): return self.elapsed()
    def pause(self, on): self.paused = on
    def capture(self, pix): return self.elapsed()


n = FakeNotes()
w = fl.ClassWindow(n, lambda notes: n.stop_ev.set())
w.move(geo.center().x() - 300, geo.top() + 30)
lines = "[11:02] El contrato de transporte es consensual, se perfecciona con el acuerdo.\n[11:40] La carta de porte es el documento que prueba el contrato.\n[12:10] El transportista responde por la pérdida o avería desde que recibe la carga."
n.segments = [(0, l[8:]) for l in lines.splitlines()]
w.add_text(lines)
w.mark(); w.doubt()
w.mine.setPlainText("Preguntar si la carta de porte puede ser digital")
w.helper.setText("<b>✨ Lo último de la clase</b><br>• Contrato de transporte: consensual<br>• Carta de porte = prueba")
w.helper.show()
shot(w, "3_clase")
n.levels["pc"] = 0.0
w.quiet_since = time.time() - 40
w.helper.hide(); w.helper.setText("")
settle(0.6)
assert w.warn.isVisible(), "no avisó el silencio"
shot(w, "4_silencio")
w.toggle_mini()
settle(0.4)
shot(w, "5_mini")
assert w.height() < 200, w.height()
w.toggle_mini()
w.stop()
w.set_status("Gemini está ocupado ahora (error 503): reintento en 20 s (intento 2 de 4)…")
w.build_start -= 191
settle(1.2)
assert "suele tardar" in w.warn.text() and w.warn.isVisible() and "ARMANDO APUNTES · 03:1" in w.pill.text(), w.pill.text()
shot(w, "5b_armando")
html = os.path.join(n.folder, "Apuntes.html")
open(html, "w").write("x")
w.done(html)
shot(w, "6_listo")
assert w.done_box.isVisible() and not w.stop_btn.isVisible()
print("CLASE PANTALLA OK")
