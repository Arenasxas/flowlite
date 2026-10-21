"""Panel de FlowLite (se abre tocando la esfera) y aviso de clase/reunión detectada.

Solo interfaz: todo lo que hace lo recibe en `ctx` (funciones de flowlite.py), así no hay imports circulares.
"""
import os
import tempfile
import threading
from datetime import datetime, timedelta

from PySide6.QtCore import QEasingCurve, QObject, QPoint, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractButton, QPlainTextEdit, QApplication, QComboBox, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLayout, QLineEdit, QSizePolicy,
                               QMessageBox, QProgressBar, QPushButton, QScrollArea, QStackedWidget, QTextBrowser,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

C = {"bg": "#14121b", "card": "#1e1b28", "card2": "#262233", "line": "#302b40", "text": "#ece8f5", "muted": "#9c95b0",
     "accent": "#8b5cf6", "accent2": "#22d3ee", "ok": "#34d399", "warn": "#fbbf24", "bad": "#f87171"}

ARROW = os.path.join(tempfile.gettempdir(), "flowlite_arrow.svg").replace("\\", "/")
with open(ARROW, "w", encoding="utf-8") as _f:
    _f.write('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12"><path d="M2 4l4 4 4-4" '
             'fill="none" stroke="#9c95b0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')

QSS = f"""
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif; font-size: 13px; color: {C['text']}; }}
#root, #col {{ background: {C['bg']}; }}
QScrollArea {{ background: {C['bg']}; border: none; }}
#side {{ background: transparent; }}
QLabel#h1 {{ font-size: 18px; font-weight: 700; }}
QLabel#h2 {{ font-size: 15px; font-weight: 700; margin-top: 6px; }}
QLabel#muted, QLabel[muted="true"] {{ color: {C['muted']}; }}
QFrame#card {{ background: {C['card']}; border: 1px solid {C['line']}; border-radius: 14px; }}
QPushButton {{ background: {C['card2']}; border: 1px solid {C['line']}; border-radius: 10px; padding: 7px 12px; }}
QPushButton:hover {{ background: #312b42; border-color: {C['accent']}; }}
QPushButton:pressed {{ background: #3a3250; }}
QPushButton#primary {{ background: {C['accent']}; border: none; font-weight: 600; color: white; }}
QPushButton#primary:hover {{ background: #9d74ff; }}
QPushButton#nav {{ background: transparent; border: none; border-radius: 12px; padding: 10px 6px; font-size: 20px; }}
QPushButton#nav:hover {{ background: {C['card2']}; }}
QPushButton#nav:checked {{ background: {C['card2']}; border-left: 3px solid {C['accent']}; }}
QPushButton#ghost {{ background: transparent; border: none; color: {C['muted']}; padding: 4px 8px; }}
QPushButton#ghost:hover {{ color: {C['text']}; }}
QPushButton#chip {{ border-radius: 14px; padding: 6px 12px; }}
QTextBrowser {{ background: {C['card']}; border: 1px solid {C['line']}; border-radius: 12px; padding: 8px; }}
QLineEdit, QComboBox, QTableWidget, QPlainTextEdit {{ background: {C['card2']}; border: 1px solid {C['line']}; border-radius: 10px;
  padding: 6px 10px; selection-background-color: {C['accent']}; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {C['accent']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url({ARROW}); width: 12px; height: 12px; margin-right: 8px; }}
QComboBox QAbstractItemView {{ background: {C['card2']}; border: 1px solid {C['line']}; selection-background-color: {C['accent']}; }}
QHeaderView::section {{ background: {C['card']}; border: none; padding: 6px; color: {C['muted']}; }}
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ border: none; padding: 0; margin: 0 0 8px 0; }}
QListWidget::item:selected {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: {C['line']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QProgressBar {{ background: {C['card2']}; border: none; border-radius: 2px; }}
QProgressBar::chunk {{ background: {C['accent']}; border-radius: 2px; }}
"""

STATUS = {"pegado": ("✓ Pegado", C["ok"]), "copiado": ("📋 Solo copiado", C["warn"]),
          "comando": ("✨ Comando", C["accent2"]), "atajo": ("⚡ Atajo", C["accent2"]), "error": ("✕ Error", C["bad"]),
          "": ("✓ Pegado", C["ok"])}


class Relay(QObject):
    """Corre una función lenta en otro hilo y entrega (ok, resultado) por señal en el hilo de la ventana."""
    done = Signal(object)

    @staticmethod
    def run(fn, relay):
        def work():
            try:
                relay.done.emit((True, fn()))
            except Exception as e:
                print("Tarea en segundo plano falló:", e)
                relay.done.emit((False, str(e)))
        threading.Thread(target=work, daemon=True).start()


def soft(hex_color, alpha=0.16):
    """Color con transparencia en el formato de Qt (rgba), para fondos de etiquetas."""
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"


class FlowLayout(QLayout):
    """Acomoda los widgets uno al lado del otro y salta de línea cuando no entran (como etiquetas)."""

    def __init__(self, spacing=6):
        super().__init__()
        self.items, self.sp = [], spacing

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, i):
        return self.items[i] if 0 <= i < len(self.items) else None

    def takeAt(self, i):
        return self.items.pop(i) if 0 <= i < len(self.items) else None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._place(QRect(0, 0, width, 0), dry=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._place(rect)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for it in self.items:
            size = size.expandedTo(it.minimumSize())
        return size

    def _place(self, rect, dry=False):
        x, y, line = rect.x(), rect.y(), 0
        for it in self.items:
            w, h = it.sizeHint().width(), it.sizeHint().height()
            if x + w > rect.right() and line:
                x, y, line = rect.x(), y + line + self.sp, 0
            if not dry:
                it.setGeometry(QRect(QPoint(x, y), it.sizeHint()))
            x += w + self.sp
            line = max(line, h)
        return y + line - rect.y()


def native_round(w, border=None):
    """Esquinas redondeadas, sombra y modo oscuro de Windows 11 (DWM). Sin transparencias de Qt,
    que en pantalla dejan restos de lo que se dibujó antes."""
    import ctypes
    hwnd = int(w.winId())
    dwm = ctypes.windll.dwmapi
    for attr, val in ((20, 1), (33, 2)):  # DWMWA_USE_IMMERSIVE_DARK_MODE, DWMWA_WINDOW_CORNER_PREFERENCE=ROUND
        v = ctypes.c_int(val)
        dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), 4)
    if border:  # DWMWA_BORDER_COLOR, formato 0x00BBGGRR
        h = border.lstrip("#")
        v = ctypes.c_int(int(h[4:6] + h[2:4] + h[0:2], 16))
        dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(v), 4)


def paper():
    """Contenedor que SÍ pinta su fondo (un QWidget común ignora el fondo del estilo y deja restos)."""
    w = QWidget()
    w.setObjectName("col")
    w.setAttribute(Qt.WA_StyledBackground, True)
    return w


class Column(QScrollArea):
    """Lista vertical que se desplaza: cada elemento ocupa todo el ancho y su alto natural."""

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = paper()
        self.box = QVBoxLayout(inner)
        self.box.setContentsMargins(0, 0, 6, 0)
        self.box.setSpacing(8)
        self.box.addStretch(1)
        self.setWidget(inner)

    def clear(self):
        while self.box.count() > 1:
            w = self.box.takeAt(0).widget()
            if w:
                w.hide()  # fuera de inmediato: deleteLater solo no alcanza y quedaban "fantasmas"
                w.setParent(None)
                w.deleteLater()

    def add(self, widget):
        widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)  # nunca más bajo que su alto natural
        self.box.insertWidget(self.box.count() - 1, widget)

    def count(self):
        return self.box.count() - 1


def label(text, name=None, wrap=False):
    l = QLabel(text)
    if name:
        l.setObjectName(name)
    l.setWordWrap(wrap)
    return l


def card():
    f = QFrame()
    f.setObjectName("card")
    return f


class Switch(QAbstractButton):
    """Interruptor tipo celular."""

    def __init__(self, checked=False, on_change=None):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(42, 24)
        if on_change:
            self.toggled.connect(on_change)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["accent"] if self.isChecked() else C["line"]))
        p.drawRoundedRect(QRectF(0, 0, 42, 24), 12, 12)
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(21 if self.isChecked() else 3, 3, 18, 18))
        p.end()


def setting_row(title, desc, widget):
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 6, 0, 6)
    v = QVBoxLayout()
    v.setSpacing(0)
    v.addWidget(label(title))
    if desc:
        d = label(desc, "muted", wrap=True)
        v.addWidget(d)
    h.addLayout(v, 1)
    h.addWidget(widget, 0, Qt.AlignVCenter)
    return row


class HistoryRow(QFrame):
    def __init__(self, row, ctx, on_delete, on_retry=None):
        super().__init__()
        self.setObjectName("card")
        rid, ts, seconds, text, app, status = row
        g = QGridLayout(self)
        g.setContentsMargins(14, 10, 10, 10)
        g.setHorizontalSpacing(10)
        when = datetime.fromisoformat(ts)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(label(when.strftime("%H:%M"), "muted"))
        st, color = STATUS.get(status or "", STATUS[""])
        chip = QLabel(st)
        chip.setStyleSheet(f"color:{color}; background:{soft(color)}; border-radius:8px; padding:1px 8px; font-size:12px;")
        top.addWidget(chip)
        if app:
            a = QLabel(app.split(" — ")[0].replace(".exe", ""))
            a.setStyleSheet(f"color:{C['muted']}; background:{C['card2']}; border-radius:8px; padding:1px 8px; font-size:12px;")
            top.addWidget(a)
        top.addStretch(1)
        g.addLayout(top, 0, 0, Qt.AlignTop)
        g.setRowStretch(1, 1)  # si los botones son más altos, el espacio va al texto, no a las etiquetas
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setStyleSheet("font-size:14px;")
        g.addWidget(body, 1, 0, Qt.AlignTop)
        btns = QVBoxLayout()
        cp = QPushButton("Copiar")
        cp.setCursor(Qt.PointingHandCursor)
        cp.clicked.connect(lambda: (ctx.copy_text(text), cp.setText("¡Copiado!"), QTimer.singleShot(1200, lambda: cp.setText("Copiar"))))
        rm = QPushButton("🗑")
        rm.setObjectName("ghost")
        rm.setToolTip("Borrar del historial")
        rm.clicked.connect(lambda: on_delete(rid))
        btns.addWidget(cp)
        if status == "error" and on_retry and ctx.can_retry(rid):
            rt = QPushButton("↻ Reintentar")
            rt.setObjectName("primary")
            rt.setToolTip("Vuelve a transcribir ese audio y te lo deja copiado")
            rt.clicked.connect(lambda: (rt.setText("…"), rt.setEnabled(False), on_retry(rid)))
            btns.addWidget(rt)
        btns.addWidget(rm, 0, Qt.AlignRight)
        btns.addStretch(1)
        g.addLayout(btns, 0, 1, 2, 1)


class Panel(QWidget):
    PAGES = (("🕘", "Historial"), ("📝", "Apuntes"), ("✨", "Personal"), ("🗒", "Notas rápidas"), ("⚙️", "Ajustes"))
    SETTINGS = 4

    def __init__(self, ctx):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.ctx, self.drag = ctx, None
        self.setStyleSheet(QSS)
        self.resize(740, 600)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        root = QFrame()
        root.setObjectName("root")
        outer.addWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(10, 12, 16, 14)
        # barra lateral
        side = QVBoxLayout()
        side.setSpacing(6)
        logo = QLabel("◉")
        logo.setStyleSheet(f"font-size:26px; color:{C['accent2']}; padding:6px 0 10px 0;")
        logo.setAlignment(Qt.AlignCenter)
        side.addWidget(logo)
        self.nav = []
        for i, (icon, name) in enumerate(self.PAGES):
            b = QPushButton(icon)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setToolTip(name)
            b.setFixedSize(52, 48)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _, i=i: self.go(i))
            side.addWidget(b)
            self.nav.append(b)
        side.addStretch(1)
        lay.addLayout(side)
        # contenido
        main = QVBoxLayout()
        main.setSpacing(10)
        head = QHBoxLayout()
        self.title = label("Historial", "h1")
        head.addWidget(self.title)
        self.pill = QLabel()
        head.addWidget(self.pill)
        head.addStretch(1)
        close = QPushButton("✕")
        close.setObjectName("ghost")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.hide)
        head.addWidget(close)
        main.addLayout(head)
        self.quick = QHBoxLayout()
        self.quick.setSpacing(6)
        main.addLayout(self.quick)
        self.stack = QStackedWidget()
        for build in (self._history_page, self._notes_page, self._personal_page, self._quick_page, self._settings_page):
            self.stack.addWidget(build())
        main.addWidget(self.stack, 1)
        lay.addLayout(main, 1)
        self.clock = QTimer(self)
        self.clock.timeout.connect(self.refresh_status)
        self.relay, self.pending = Relay(), None
        self.relay.done.connect(self._bg_done)
        self.go(0)

    # ── general ──
    def go(self, i):
        for j, b in enumerate(self.nav):
            b.setChecked(i == j)
        self.stack.setCurrentIndex(i)
        self.title.setText(self.PAGES[i][1])
        (self.load_history, self.load_notes, self.load_personal, self.load_quick, lambda: None)[i]()

    def toggle_near(self, anchor):
        if self.isVisible():
            self.hide()
            return
        self.refresh()
        scr = (QApplication.screenAt(anchor) or QApplication.primaryScreen()).availableGeometry()
        x = min(max(anchor.x() - self.width() + 40, scr.left() + 8), scr.right() - self.width() - 8)
        y = anchor.y() - self.height() - 10
        if y < scr.top() + 8:
            y = min(anchor.y() + 90, scr.bottom() - self.height() - 8)
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def refresh(self):
        self.build_quick()
        self.refresh_status()
        self.go(self.stack.currentIndex())
        self.clock.start(1000)

    def showEvent(self, e):
        native_round(self, C["line"])
        super().showEvent(e)

    def hideEvent(self, e):
        self.clock.stop()
        super().hideEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()
        super().keyPressEvent(e)

    def mousePressEvent(self, e):
        if e.position().y() < 60:
            self.drag = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e):
        if self.drag is not None:
            self.move(e.globalPosition().toPoint() - self.drag)

    def mouseReleaseEvent(self, _):
        self.drag = None

    def refresh_status(self):
        cls = self.ctx.class_elapsed()
        if cls is not None:
            text, color = f"● Grabando clase · {cls}", C["accent"]
        elif self.ctx.is_active():
            text, color = f"● Activo · {self.ctx.hotkey_label()}", C["ok"]
        else:
            text, color = "⏸ En pausa", C["muted"]
        self.pill.setText(text)
        self.pill.setStyleSheet(f"color:{color}; background:{soft(color)}; border-radius:10px; padding:3px 10px; font-weight:600;")

    def build_quick(self):
        while self.quick.count():
            w = self.quick.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for key in self.ctx.get("quick_buttons"):
            text, fn = self.ctx.quick_actions().get(key, (None, None))
            if not text:
                continue
            b = QPushButton(text)
            b.setObjectName("chip")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _, fn=fn: (fn(), QTimer.singleShot(300, self.refresh)))
            self.quick.addWidget(b)
        self.quick.addStretch(1)

    # ── historial ──
    def _history_page(self):
        w = paper()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        stats = QHBoxLayout()
        self.stats = []
        for _ in range(4):
            c = card()
            cv = QVBoxLayout(c)
            cv.setContentsMargins(14, 10, 14, 10)
            big, small = label("0"), label("", "muted")
            big.setStyleSheet("font-size:20px; font-weight:700;")
            cv.addWidget(big)
            cv.addWidget(small)
            stats.addWidget(c)
            self.stats.append((big, small))
        v.addLayout(stats)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Buscar en lo que dictaste…")
        self.search.textChanged.connect(lambda _: self.load_history())
        bar.addWidget(self.search, 1)
        self.filter = QComboBox()
        for k, t in (("", "Todo"), ("pegado", "Pegado"), ("copiado", "Solo copiado"), ("comando", "Comandos"),
                     ("error", "Errores")):
            self.filter.addItem(t, k)
        self.filter.currentIndexChanged.connect(lambda _: self.load_history())
        bar.addWidget(self.filter)
        clear = QPushButton("Borrar todo")
        clear.setObjectName("ghost")
        clear.clicked.connect(self.clear_history)
        bar.addWidget(clear)
        v.addLayout(bar)
        self.hist_list = Column()
        v.addWidget(self.hist_list, 1)
        return w

    def load_history(self):
        st = self.ctx.hist.stats()
        for (big, small), (val, cap) in zip(self.stats, st):
            big.setText(val)
            small.setText(cap)
        self.hist_list.clear()
        self.hist_rows = 0
        rows = self.ctx.hist.rows(self.search.text().strip(), self.filter.currentData() or "")
        last_day = None
        for row in rows:
            day = row[1][:10]
            if day != last_day:
                last_day = day
                d = datetime.fromisoformat(row[1]).date()
                today = datetime.now().date()
                name = "Hoy" if d == today else "Ayer" if d == today - timedelta(days=1) else d.strftime("%d/%m/%Y")
                self.hist_list.add(label(name, "h2"))
            self.hist_list.add(HistoryRow(row, self.ctx, self.delete_row, self.retry_row))
            self.hist_rows += 1
        if not rows:
            self.hist_list.add(label("Todavía no hay dictados acá. Mantené "
                                     f"{self.ctx.hotkey_label()} y hablá." if not self.search.text() and
                                     not self.filter.currentData() else "No hay dictados que coincidan.", "muted", wrap=True))

    def retry_row(self, rid):
        Relay.run(lambda: self.ctx.retry(rid), self.relay)
        self.pending = "retry"

    def _bg_done(self, result):
        ok, value = result
        kind, self.pending = self.pending, None
        if kind == "retry":
            self.load_history()
            if not ok:
                QMessageBox.warning(self, "FlowLite", f"No pude transcribirlo de nuevo: {value}")
        elif kind == "ask":
            self.answer.setMarkdown(value if ok else f"No pude responder: {value}")
            self.ask_btn.setEnabled(True)
        elif kind == "guide":
            self.guide_btn.setEnabled(True)
            self.guide_btn.setText("📚 Resumen para el parcial")
            if ok:
                os.startfile(value)
                self.load_notes()
            else:
                QMessageBox.warning(self, "FlowLite", f"No pude armar el resumen: {value}")

    def delete_row(self, rid):
        self.ctx.hist.delete(rid)
        self.load_history()

    def clear_history(self):
        if QMessageBox.question(self, "FlowLite", "¿Borrar todo el historial de dictados?") == QMessageBox.Yes:
            self.ctx.hist.clear()
            self.load_history()

    # ── apuntes ──
    def _notes_page(self):
        w = paper()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        hero = card()
        hv = QHBoxLayout(hero)
        hv.setContentsMargins(16, 14, 16, 14)
        txt = QVBoxLayout()
        self.notes_title = label("Apuntes de clases y reuniones", "h2")
        self.notes_sub = label("", "muted", wrap=True)
        txt.addWidget(self.notes_title)
        txt.addWidget(self.notes_sub)
        hv.addLayout(txt, 1)
        self.notes_btn = QPushButton()
        self.notes_btn.setObjectName("primary")
        self.notes_btn.setCursor(Qt.PointingHandCursor)
        self.notes_btn.clicked.connect(lambda: (self.ctx.notes_toggle(), QTimer.singleShot(400, self.load_notes)))
        hv.addWidget(self.notes_btn)
        v.addWidget(hero)
        ask = QHBoxLayout()
        self.ask = QLineEdit()
        self.ask.setPlaceholderText("💬  Preguntale a tus clases: «¿cómo se calcula el punto de equilibrio?»")
        self.ask.returnPressed.connect(self.ask_classes)
        self.ask_btn = QPushButton("Preguntar")
        self.ask_btn.setObjectName("primary")
        self.ask_btn.clicked.connect(self.ask_classes)
        ask.addWidget(self.ask, 1)
        ask.addWidget(self.ask_btn)
        v.addLayout(ask)
        self.answer = QTextBrowser()
        self.answer.setOpenExternalLinks(True)
        self.answer.setMaximumHeight(170)
        self.answer.hide()
        v.addWidget(self.answer)
        head = QHBoxLayout()
        head.addWidget(label("Tus clases", "h2"))
        head.addStretch(1)
        for text, fn in (("📂", lambda: self.ctx.open_notes_dir()), ("🔁 Rehacer de una carpeta…", lambda: self.ctx.redo_pick())):
            b = QPushButton(text)
            b.setObjectName("ghost")
            b.clicked.connect(fn)
            head.addWidget(b)
        v.addLayout(head)
        self.subject_row = QHBoxLayout()
        self.subject_row.setSpacing(6)
        v.addLayout(self.subject_row)
        self.subject = None
        self.guide_btn = QPushButton("📚 Resumen para el parcial")
        self.guide_btn.setObjectName("primary")
        self.guide_btn.setToolTip("Une los apuntes de todas las clases de esta materia en uno solo para estudiar")
        self.guide_btn.clicked.connect(self.make_guide)
        self.guide_open = QPushButton("Abrir el último")
        self.guide_open.clicked.connect(lambda: os.startfile(self.ctx.guide_path(self.subject_name())))
        grow = QHBoxLayout()
        grow.addWidget(self.guide_btn)
        grow.addWidget(self.guide_open)
        grow.addStretch(1)
        self.guide_box = QWidget()
        self.guide_box.setLayout(grow)
        v.addWidget(self.guide_box)
        self.notes_list = Column()
        v.addWidget(self.notes_list, 1)
        return w

    def load_notes(self):
        running = self.ctx.class_elapsed()
        if running is not None:
            self.notes_btn.setText("⏹ Terminar y armar apuntes")
            self.notes_sub.setText(f"Grabando ahora ({running}). Abrí la ventana de la clase para marcar, capturar o escribir notas.")
        else:
            self.notes_btn.setText("▶ Tomar apuntes")
            self.notes_sub.setText(f"Graba el audio de la PC o el micrófono y arma apuntes tipo cuaderno con "
                                   f"{'Gemini' if self.ctx.gemini_on() else 'Groq'}.")
        self.notes_list.clear()
        subs = self.ctx.subjects()
        while self.subject_row.count():
            w = self.subject_row.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        if self.subject not in subs:
            self.subject = None
        for key, info in [(None, {"name": "Todas", "folders": []})] + sorted(subs.items(), key=lambda x: x[1]["name"]):
            n = len(info["folders"])
            b = QPushButton(info["name"] + (f"  {n}" if key else ""))
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setChecked(key == self.subject)
            b.setStyleSheet(f"QPushButton:checked{{background:{C['accent']};color:white;border:none;}}")
            b.clicked.connect(lambda _, key=key: (setattr(self, "subject", key), self.load_notes()))
            self.subject_row.addWidget(b)
        self.subject_row.addStretch(1)
        self.guide_box.setVisible(self.subject is not None)
        if self.subject is not None:
            self.guide_open.setVisible(bool(self.ctx.guide_path(self.subject_name())))
        allowed = set(subs[self.subject]["folders"]) if self.subject else None
        for folder, name, has_html in self.ctx.class_folders():
            if allowed is not None and folder not in allowed:
                continue
            c = card()
            h = QHBoxLayout(c)
            h.setContentsMargins(14, 8, 10, 8)
            info = QVBoxLayout()
            date, _, title = name.partition(" - ")
            info.addWidget(label(title or name))
            info.addWidget(label(date.replace(".", ":") + ("" if has_html else " · sin apuntes armados"), "muted"))
            h.addLayout(info, 1)
            if has_html:
                o = QPushButton("Abrir")
                o.setObjectName("primary")
                o.clicked.connect(lambda _, f=folder: os.startfile(os.path.join(f, "Apuntes.html")))
                h.addWidget(o)
            r = QPushButton("Rehacer")
            r.clicked.connect(lambda _, f=folder: self.ctx.redo(f))
            h.addWidget(r)
            fo = QPushButton("📂")
            fo.setObjectName("ghost")
            fo.clicked.connect(lambda _, f=folder: os.startfile(f))
            h.addWidget(fo)
            self.notes_list.add(c)
        if not self.notes_list.count():
            self.notes_list.add(label("Todavía no grabaste clases.", "muted"))

    def subject_name(self):
        return self.ctx.subjects().get(self.subject, {}).get("name", "Materia")

    def visible_folders(self):
        subs = self.ctx.subjects()
        return subs[self.subject]["folders"] if self.subject in subs else [f for f, _, _ in self.ctx.class_folders()]

    def ask_classes(self):
        q = self.ask.text().strip()
        if not q or self.pending:
            return
        self.answer.show()
        self.answer.setMarkdown("✨ Buscando en tus clases…")
        self.ask_btn.setEnabled(False)
        self.pending = "ask"
        folders = self.visible_folders()
        Relay.run(lambda: self.ctx.ask_classes(q, folders), self.relay)

    def make_guide(self):
        if self.pending or self.subject is None:
            return
        self.pending = "guide"
        self.guide_btn.setEnabled(False)
        self.guide_btn.setText("⏳ Uniendo tus clases… (1-2 min)")
        folders, name = self.visible_folders(), self.subject_name()
        Relay.run(lambda: self.ctx.study_guide(folders, name), self.relay)

    # ── personal: vocabulario y atajos de voz ──
    def _personal_page(self):
        w = paper()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(label("Vocabulario", "h2"))
        v.addWidget(label("Nombres, marcas y palabras técnicas que FlowLite tiene que escribir bien "
                          "(también ayuda en los apuntes: autores, fórmulas, siglas).", "muted", wrap=True))
        add = QHBoxLayout()
        self.word = QLineEdit()
        self.word.setPlaceholderText("Ej.: Horngren, prorrateo, CMgU")
        self.word.returnPressed.connect(self.add_word)
        add.addWidget(self.word, 1)
        b = QPushButton("Agregar")
        b.setObjectName("primary")
        b.clicked.connect(self.add_word)
        add.addWidget(b)
        v.addLayout(add)
        box = QScrollArea()
        box.setWidgetResizable(True)
        box.setFrameShape(QFrame.NoFrame)
        box.setMaximumHeight(130)
        holder = paper()
        self.words = FlowLayout()
        holder.setLayout(self.words)
        box.setWidget(holder)
        v.addWidget(box)
        v.addWidget(label("Atajos de voz", "h2"))
        v.addWidget(label("Decís lo de la izquierda y se escribe lo de la derecha (tu mail, tu firma, un link).",
                          "muted", wrap=True))
        self.snip = QTableWidget(0, 2)
        self.snip.setHorizontalHeaderLabels(["Lo que decís", "Lo que se escribe"])
        self.snip.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.snip.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.snip.verticalHeader().hide()
        self.snip.itemChanged.connect(lambda _: self.save_snippets())
        v.addWidget(self.snip, 1)
        row = QHBoxLayout()
        a = QPushButton("+ Agregar atajo")
        a.clicked.connect(lambda: (self.snip.insertRow(self.snip.rowCount()),
                                   self.snip.editItem(self._cell(self.snip.rowCount() - 1, 0))))
        rm = QPushButton("Quitar el seleccionado")
        rm.setObjectName("ghost")
        rm.clicked.connect(lambda: (self.snip.removeRow(self.snip.currentRow()), self.save_snippets())
                           if self.snip.currentRow() >= 0 else None)
        row.addWidget(a)
        row.addWidget(rm)
        row.addStretch(1)
        v.addLayout(row)
        return w

    def _cell(self, r, c):
        it = self.snip.item(r, c)
        if it is None:
            it = QTableWidgetItem("")
            self.snip.setItem(r, c, it)
        return it

    def load_personal(self):
        while self.words.count():
            w = self.words.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for wd in self.ctx.vocab():
            chip = QPushButton(f"{wd}  ✕")
            chip.setObjectName("chip")
            chip.setCursor(Qt.PointingHandCursor)
            chip.setToolTip("Tocá para quitarla")
            chip.clicked.connect(lambda _, wd=wd: (self.ctx.unlearn(wd), self.load_personal()))
            self.words.addWidget(chip)
        self.snip.blockSignals(True)
        self.snip.setRowCount(0)
        for cue, text in self.ctx.snippets().items():
            r = self.snip.rowCount()
            self.snip.insertRow(r)
            self.snip.setItem(r, 0, QTableWidgetItem(cue))
            self.snip.setItem(r, 1, QTableWidgetItem(text))
        self.snip.blockSignals(False)

    def add_word(self):
        wd = self.word.text().strip()
        if wd:
            self.ctx.learn([wd])
            self.word.clear()
            self.load_personal()

    def save_snippets(self):
        data = {}
        for r in range(self.snip.rowCount()):
            cue, text = (self.snip.item(r, c).text().strip() if self.snip.item(r, c) else "" for c in (0, 1))
            if cue and text:
                data[cue] = text
        self.ctx.save_snippets(data)

    # ── notas rápidas (como el scratchpad de Wispr Flow) ──
    def _quick_page(self):
        w = paper()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(label("Un lugar para anotar al toque: hacé clic acá y dictá con tu tecla, o escribí. "
                          "Se guarda solo.", "muted", wrap=True))
        self.quick_text = QPlainTextEdit()
        self.quick_text.setPlaceholderText("Ideas, pendientes, cosas para preguntarle al profe…")
        self.quick_text.setStyleSheet("font-size:14px;")
        self.quick_save = QTimer(self)
        self.quick_save.setSingleShot(True)
        self.quick_save.timeout.connect(self.save_quick)
        self.quick_text.textChanged.connect(lambda: self.quick_save.start(700))
        v.addWidget(self.quick_text, 1)
        row = QHBoxLayout()
        cp = QPushButton("Copiar todo")
        cp.clicked.connect(lambda: self.ctx.copy_text(self.quick_text.toPlainText()))
        self.quick_info = label("", "muted")
        row.addWidget(cp)
        row.addStretch(1)
        row.addWidget(self.quick_info)
        v.addLayout(row)
        return w

    def load_quick(self):
        path = self.ctx.quick_notes_path
        text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        if text != self.quick_text.toPlainText():
            self.quick_text.blockSignals(True)
            self.quick_text.setPlainText(text)
            self.quick_text.blockSignals(False)
        self.quick_text.setFocus()

    def save_quick(self):
        with open(self.ctx.quick_notes_path, "w", encoding="utf-8") as f:
            f.write(self.quick_text.toPlainText())
        self.quick_info.setText("Guardado ✓")
        QTimer.singleShot(1500, lambda: self.quick_info.setText(""))

    # ── ajustes ──
    def rebuild_settings(self):
        """Vuelve a armar Ajustes (p. ej. después de cambiar la clave de Gemini) y se queda ahí."""
        old = self.stack.widget(self.SETTINGS)
        self.stack.insertWidget(self.SETTINGS, self._settings_page())
        self.stack.removeWidget(old)
        old.deleteLater()
        self.go(self.SETTINGS)

    def pick_notes_dir(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Elegí la carpeta de apuntes", self.ctx.notes_dir())
        if d:
            self.change_notes_dir(os.path.normpath(d))

    def use_drive(self, drive):
        if not drive:
            os.startfile("https://www.google.com/drive/download/")
            return
        self.change_notes_dir(drive)

    def change_notes_dir(self, path):
        copy = QMessageBox.question(self, "FlowLite", f"Los apuntes nuevos van a ir a:\n{path}\n\n"
                                    "¿Copio ahí también las clases que ya tenés? (las de la carpeta vieja no se borran)")
        self.ctx.set_notes_dir(path, copy == QMessageBox.Yes)
        self.rebuild_settings()

    def _settings_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        w = paper()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 8, 0)
        ctx = self.ctx

        def section(title):
            v.addWidget(label(title, "h2"))
            c = card()
            cv = QVBoxLayout(c)
            cv.setContentsMargins(14, 6, 14, 6)
            v.addWidget(c)
            return cv

        s = section("Dictado")
        hk = QComboBox()
        for key, (lab, _) in ctx.hotkeys().items():
            hk.addItem(lab, key)
        hk.setCurrentIndex(max(hk.findData(ctx.get("hotkey")), 0))
        hk.currentIndexChanged.connect(lambda _: (ctx.set_hotkey(hk.currentData()), self.refresh_status()))
        s.addWidget(setting_row("Tecla para dictar", "Mantener = dictar · 2 toques = sin sostener · 3 toques = pausa · "
                                "+ Shift = modo comando", hk))
        lang = QComboBox()
        for key, lab in (("es", "Español"), ("auto", "Detectar idioma"), ("en", "English"), ("pt", "Português")):
            lang.addItem(lab, key)
        lang.setCurrentIndex(max(lang.findData(ctx.get("language")), 0))
        lang.currentIndexChanged.connect(lambda _: ctx.set("language", lang.currentData()))
        s.addWidget(setting_row("Idioma", "En qué idioma hablás.", lang))
        s.addWidget(setting_row("Pulir con IA", "Puntuación, muletillas, autocorrecciones y formato según la app.",
                                Switch(ctx.get("polish"), lambda on: ctx.set("polish", on))))
        s.addWidget(setting_row("Sonidos", "Un tono corto al empezar y al terminar de grabar.",
                                Switch(ctx.get("sounds"), lambda on: ctx.set("sounds", on))))

        s = section("Bolita")
        s.addWidget(setting_row("Mostrar la bolita", "Si la ocultás, el panel se abre desde el ícono al lado del reloj.",
                                Switch(ctx.get("orb_visible"), lambda on: ctx.set("orb_visible", on))))
        size = QComboBox()
        for key, lab in (("small", "Chica"), ("normal", "Normal"), ("large", "Grande")):
            size.addItem(lab, key)
        size.setCurrentIndex(max(size.findData(ctx.get("orb_size")), 0))
        size.currentIndexChanged.connect(lambda _: ctx.set("orb_size", size.currentData()))
        s.addWidget(setting_row("Tamaño", None, size))

        s = section("Botones rápidos")
        s.addWidget(label("Elegí qué botones aparecen arriba del panel y en el clic derecho de la bolita.", "muted", wrap=True))
        chosen = list(ctx.get("quick_buttons"))
        grid = QGridLayout()
        for i, (key, (text, _)) in enumerate(ctx.quick_actions().items()):
            sw = Switch(key in chosen)

            def change(on, key=key):
                cur = [k for k in ctx.get("quick_buttons") if k != key] + ([key] if on else [])
                order = list(ctx.quick_actions())
                ctx.set("quick_buttons", sorted(cur, key=order.index))
                self.build_quick()
            sw.toggled.connect(change)
            cell = QHBoxLayout()
            cell.addWidget(sw)
            cell.addWidget(label(text))
            cell.addStretch(1)
            grid.addLayout(cell, i // 2, i % 2)
        s.addLayout(grid)

        s = section("Apuntes de clase")
        s.addWidget(setting_row("Ofrecer apuntes al entrar a una clase o llamada",
                                "Meet, Zoom, Teams, Webex, aulas virtuales y llamadas de WhatsApp, Discord o Telegram.",
                                Switch(ctx.get("detect_meetings"), lambda on: ctx.set("detect_meetings", on))))
        gem = QPushButton("Cambiar…")
        gem.clicked.connect(lambda: (ctx.ask_gemini(), self.rebuild_settings()))
        s.addWidget(setting_row(f"Motor de apuntes: {'Gemini ✓' if ctx.gemini_on() else 'Groq'}",
                                "Con Gemini salen mejores y lee las capturas de las diapositivas.", gem))

        folder = QPushButton("Cambiar…")
        folder.clicked.connect(self.pick_notes_dir)
        self.dir_row = setting_row("Carpeta de apuntes", ctx.notes_dir(), folder)
        s.addWidget(self.dir_row)
        drive = ctx.drive_dir()
        gd = QPushButton("Usar Google Drive" if drive else "¿Cómo sincronizo?")
        gd.clicked.connect(lambda: self.use_drive(drive))
        s.addWidget(setting_row("Ver los apuntes en el celular",
                                "Guardalos en Google Drive: aparecen en la app FlowLite del celular y en la app de Drive (PDF)."
                                if drive else "Instalá «Google Drive para escritorio» (gratis) y volvé a abrir FlowLite.", gd))

        s = section("General")
        s.addWidget(setting_row("Iniciar con Windows", None, Switch(ctx.autostart_on(), lambda on: ctx.set_autostart(on))))
        groq = QPushButton("Cambiar…")
        groq.clicked.connect(ctx.ask_groq)
        s.addWidget(setting_row("Clave de Groq", "La que se usa para transcribir.", groq))
        log = QPushButton("Abrir")
        log.clicked.connect(ctx.open_log)
        s.addWidget(setting_row("Registro de errores", f"FlowLite {ctx.version} · flowlite.log", log))
        v.addStretch(1)
        scroll.setWidget(w)
        return scroll


class MeetingToast(QWidget):
    """Tarjeta que entra desde abajo a la derecha cuando detecta una clase o llamada."""
    PLATFORMS = (("whatsapp", "una llamada de WhatsApp", "📞"), ("discord", "una llamada de Discord", "🎧"),
                 ("telegram", "una llamada de Telegram", "📞"), ("skype", "una llamada de Skype", "📞"),
                 ("slack", "una reunión de Slack", "💬"), ("meet", "Google Meet", "🎥"), ("zoom", "Zoom", "📹"),
                 ("teams", "Microsoft Teams", "👥"), ("webex", "Webex", "📞"), ("jitsi", "Jitsi", "📞"),
                 ("bigbluebutton", "un aula virtual", "🎓"))
    QUESTIONS = {"clase": "¿Tomo apuntes de esta clase?", "reunion": "¿Tomo notas de esta reunión?",
                 "llamada": "¿Tomo notas de esta llamada?", "charla": "¿Tomo apuntes de esta charla?"}

    def __init__(self, title, name, on_start, on_options, on_never, seconds=45, kind="clase", icon=None,
                 heading=None, question=None, body=None, go_text="▶ Empezar ahora", options_text="Opciones…",
                 never_text="No volver a preguntar"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet(QSS)
        low = title.lower()
        plat, found_icon = next(((p, i) for k, p, i in self.PLATFORMS if k in low), ("una clase o reunión", "🎓"))
        icon = icon or found_icon
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        root = QFrame()
        root.setObjectName("toast")
        root.setStyleSheet(f"#toast{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #221a35,stop:1 {C['bg']});}}")
        outer.addWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(18, 14, 14, 12)
        top = QHBoxLayout()
        ic = QLabel(icon)
        ic.setStyleSheet(f"font-size:26px; background:{C['card2']}; border-radius:14px; padding:6px 10px;")
        top.addWidget(ic)
        txt = QVBoxLayout()
        txt.setSpacing(0)
        txt.addWidget(label(heading or f"Estás en {plat}", "muted"))
        txt.addWidget(label(question or self.QUESTIONS.get(kind, self.QUESTIONS["clase"]), "h2"))
        top.addLayout(txt, 1)
        x = QPushButton("✕")
        x.setObjectName("ghost")
        x.clicked.connect(self.dismiss)
        top.addWidget(x, 0, Qt.AlignTop)
        v.addLayout(top)
        if name:
            v.addWidget(label(f"«{name}»", wrap=True))
        v.addWidget(label(body or "Transcribo en vivo, podés marcar ⭐, ❓ y capturar la pantalla, y al final te armo "
                          "notas completas, listas para estudiar o para no olvidarte de nada.", "muted", wrap=True))
        row = QHBoxLayout()
        go = QPushButton(go_text)
        go.setObjectName("primary")
        go.setCursor(Qt.PointingHandCursor)
        go.clicked.connect(lambda: (self.dismiss(), on_start()))
        opt = QPushButton(options_text)
        opt.clicked.connect(lambda: (self.dismiss(), on_options()))
        later = QPushButton("Ahora no")
        later.setObjectName("ghost")
        later.clicked.connect(self.dismiss)
        row.addWidget(go)
        row.addWidget(opt)
        row.addStretch(1)
        row.addWidget(later)
        v.addLayout(row)
        if never_text:
            never = QPushButton(never_text)
            never.setObjectName("ghost")
            never.setStyleSheet("font-size:12px;")
            never.clicked.connect(lambda: (self.dismiss(), on_never()))
            v.addWidget(never, 0, Qt.AlignRight)
        self.bar = QProgressBar()
        self.bar.setFixedHeight(3)
        self.bar.setTextVisible(False)
        self.bar.setRange(0, seconds * 10)
        self.bar.setValue(seconds * 10)
        v.addWidget(self.bar)
        self.left = seconds * 10
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.setFixedWidth(420)
        self.adjustSize()

    def popup(self):
        scr = QApplication.primaryScreen().availableGeometry()
        end = QPoint(scr.right() - self.width() - 16, scr.bottom() - self.height() - 16)
        self.move(end.x(), scr.bottom())
        self.setWindowOpacity(0.0)
        self.show()
        native_round(self, C["accent"])
        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(420)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.setStartValue(QPoint(end.x(), end.y() + 60))
        self.anim.setEndValue(end)
        self.fade = QPropertyAnimation(self, b"windowOpacity")
        self.fade.setDuration(300)
        self.fade.setStartValue(0.0)
        self.fade.setEndValue(1.0)
        self.anim.start()
        self.fade.start()
        self.timer.start(100)

    def enterEvent(self, e):
        self.timer.stop()  # si la estás mirando, no se va sola
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.timer.start(100)
        super().leaveEvent(e)

    def _tick(self):
        self.left -= 1
        self.bar.setValue(self.left)
        if self.left <= 0:
            self.dismiss()

    def dismiss(self):
        self.timer.stop()
        self.fade = QPropertyAnimation(self, b"windowOpacity")
        self.fade.setDuration(200)
        self.fade.setStartValue(self.windowOpacity())
        self.fade.setEndValue(0.0)
        self.fade.finished.connect(self.close)
        self.fade.start()
