"""Renderiza el panel y el aviso con datos de ejemplo. Uso: python tests/test_panel.py <carpeta de capturas>"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import flowlite as fl
from PySide6.QtWidgets import QApplication
from panel import Panel, MeetingToast

out = sys.argv[1]
app = QApplication([])
import fake_ctx
ctx, h, calls = fake_ctx.build()
p = Panel(ctx)
p.move(-4000, -4000)
p.refresh()
p.show()
for i, name in enumerate(("historial", "apuntes", "personal", "notas", "ajustes")):
    p.go(i)
    for _ in range(10):
        app.processEvents(); time.sleep(0.02)
    p.grab().save(os.path.join(out, f"panel_{name}.png"))
assert p.hist_rows == 4, p.hist_rows
p.search.setText("profesora")
assert p.hist_rows == 1, p.hist_rows
p.search.setText("")
p.filter.setCurrentIndex(p.filter.findData("error"))
assert p.hist_rows == 1, p.hist_rows
# personal: agregar palabra y atajo
p.go(2); p.word.setText("Pareto"); p.add_word(); assert "Pareto" in fl.VOCAB
r = p.snip.rowCount(); p.snip.insertRow(r); p._cell(r, 0).setText("mi cel"); p._cell(r, 1).setText("351 000 0000")
assert fl.load_snippets()["mi cel"] == "351 000 0000"
print("stats:", h.stats())
t = MeetingToast("Meet – Costos y Precios - Google Chrome", "Costos y Precios", lambda: calls.append("start"),
                 lambda: calls.append("opt"), lambda: calls.append("never"))
t.move(-4000, -4000); t.show()
for _ in range(10):
    app.processEvents(); time.sleep(0.02)
t.grab().save(os.path.join(out, "toast.png"))
print("PANEL OK")
