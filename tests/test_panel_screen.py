"""Muestra el panel EN PANTALLA y captura lo que ve el usuario (no grab()), sección por sección,
ida y vuelta, para detectar restos de pintura. Uso: python tests/test_panel_screen.py <carpeta>"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint
import fake_ctx
from panel import Panel, MeetingToast

out = sys.argv[1]
app = QApplication([])
ctx, h, calls = fake_ctx.build()


def settle(sec=0.5):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def shot(w, name):
    settle()
    g = w.frameGeometry()
    scr = QApplication.screenAt(g.center()) or QApplication.primaryScreen()
    pad = 24  # incluye el borde para ver esquinas y sombra
    img = scr.grabWindow(0, g.x() - scr.geometry().x() - pad, g.y() - scr.geometry().y() - pad,
                         g.width() + 2 * pad, g.height() + 2 * pad)
    img.save(os.path.join(out, f"scr_{name}.png"))


p = Panel(ctx)
geo = QApplication.primaryScreen().availableGeometry()
p.toggle_near(QPoint(geo.center().x() + p.width() // 2, geo.center().y() + p.height() // 2))
for i, name in ((0, "1_historial"), (1, "2_apuntes"), (2, "3_personal"), (3, "3b_notas"), (4, "4_ajustes"),
                (0, "5_historial_vuelta"), (2, "6_personal_vuelta")):
    p.go(i)
    shot(p, name)
p.go(0)
p.search.setText("profesora")
shot(p, "7_busqueda")
p.go(1)
p.ask.setText("¿cómo se calcula el punto de equilibrio?")
p.ask_classes()
settle(1.2)
shot(p, "7b_pregunta")
p.subject = "costos y precios"
p.load_notes()
shot(p, "7c_materia")
p.go(0)
p.search.setText("")
p.retry_row(ctx.hist.rows()[0][0] if ctx.hist.rows()[0][5] == "error" else [r for r in ctx.hist.rows() if r[5] == "error"][0][0])
settle(1.2)
assert not [r for r in ctx.hist.rows() if r[5] == "error"], "el reintento no actualizó la fila"
shot(p, "7d_reintentado")
p.go(4)
sc = p.stack.currentWidget()
sc.verticalScrollBar().setValue(sc.verticalScrollBar().maximum())
shot(p, "9_ajustes_abajo")
assert p.dir_row is not None
sc.verticalScrollBar().setValue(0)
shot(p, "10_ajustes_arriba_otra_vez")
p.hide()
# bolita en la esquina inferior derecha (donde arranca): el panel tiene que quedar adentro de la pantalla
corner = QPoint(geo.right() - 92, geo.bottom() - 92)
p.toggle_near(corner)
settle()
g = p.frameGeometry()
inside = geo.contains(g)
print("panel dentro de la pantalla:", inside, g.getRect(), "pantalla:", geo.getRect())
assert inside
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtCore import QEvent
app.sendEvent(p, QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
settle(0.2)
print("Esc cierra:", not p.isVisible())
assert not p.isVisible()
t = MeetingToast("Meet – Costos y Precios - Google Chrome", "Costos y Precios", lambda: None, lambda: None, lambda: None)
t.popup()
settle(1.0)
shot(t, "8_aviso")
t.dismiss()
settle(0.5)
t = MeetingToast("Llamada de WhatsApp", "Llamada de WhatsApp", lambda: None, lambda: None, lambda: None, kind="llamada")
t.popup()
settle(1.0)
shot(t, "8b_aviso_whatsapp")
t.dismiss()
settle(0.5)
t = MeetingToast("", "Estadistica", lambda: None, lambda: None, lambda: None, icon="🧩", heading="Quedó una clase sin terminar",
                 question="¿Armo los apuntes?", body="La grabación del 2026-10-16 se cortó antes de terminar (se cerró FlowLite o se apagó la PC). La transcripción está guardada.",
                 go_text="📝 Armar apuntes", options_text="Ver carpeta", never_text="")
t.popup()
settle(1.0)
shot(t, "8c_aviso_sin_terminar")
t.dismiss()
settle(0.5)
import flowlite as fl
d = fl.StartDialog("Llamada de WhatsApp", "llamada")
geo2 = QApplication.primaryScreen().availableGeometry()
d.move(geo2.center().x() - 280, geo2.top() + 60)
d.show()
shot(d, "11_inicio_con_tipo")
assert d.kind.currentData() == "llamada"
d.close()
print("capturas listas")
