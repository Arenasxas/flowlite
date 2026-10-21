"""Datos de ejemplo y un ctx falso para probar el panel sin tocar la instalación real."""
import os, tempfile, time
from types import SimpleNamespace
import flowlite as fl


def build():
    tmp = tempfile.mkdtemp()
    fl.HERE, fl.STATE_PATH = tmp, os.path.join(tmp, "state.json")
    fl.SNIPPETS_PATH, fl.VOCAB_PATH = os.path.join(tmp, "snippets.json"), os.path.join(tmp, "vocabulary.json")
    fl.CONFIG["notes_dir"] = os.path.join(tmp, "Apuntes")
    for name, html in (("2026-10-17 21.32 - Costos y Precios", True), ("2026-10-16 20.01 - Estadistica", False)):
        os.makedirs(os.path.join(fl.CONFIG["notes_dir"], name))
        if html:
            open(os.path.join(fl.CONFIG["notes_dir"], name, "Apuntes.html"), "w").close()
    h = fl.History()
    ids = []
    for text, app, st in (
            ("Mañana a las seis paso por tu casa. ¿Vos podés traer el apunte de costos?", "whatsapp.exe — WhatsApp", "pegado"),
            ("Estimada profesora: le escribo para consultarle si es posible entregar el TP el lunes. Agradezco su "
             "comprensión y quedo atento a su respuesta.", "outlook.exe — Correo", "comando"),
            ("Recordar repasar punto de equilibrio y margen de seguridad para el parcial.", "explorer.exe — Escritorio", "copiado"),
            ("No se pudo procesar (sin conexión)", "chrome.exe — Docs", "error")):
        ids.append(h.add(5.2, text, app, st))
    err_id = ids[-1]
    fl.save_snippets({"mi mail": "nico@ejemplo.com", "firma": "Saludos, Nicolás"})
    fl.VOCAB[:] = ["Horngren", "prorrateo", "CMgU", "Groq", "margen de seguridad", "Pareto"]
    calls = []
    folders = lambda: [(os.path.join(fl.CONFIG["notes_dir"], n), n,
                        os.path.exists(os.path.join(fl.CONFIG["notes_dir"], n, "Apuntes.html")))
                       for n in sorted(os.listdir(fl.CONFIG["notes_dir"]), reverse=True)]
    ctx = SimpleNamespace(
        hist=h, version=fl.VERSION, copy_text=lambda t: calls.append(("copy", t)), is_active=lambda: True,
        toggle_pause=lambda: calls.append("pause"), hotkeys=lambda: fl.HOTKEYS, hotkey_label=lambda: "Ctrl izq + Alt izq",
        set_hotkey=lambda k: fl.save_state(hotkey=k), get=fl.setting, set=lambda k, v: fl.save_state(**{k: v}),
        quick_actions=lambda: {"notes": ("📝 Tomar apuntes", lambda: None), "copy": ("📋 Copiar último", lambda: None),
                               "pause": ("⏸ Pausar", lambda: None), "folder": ("📂 Apuntes", lambda: None),
                               "word": ("➕ Palabra", lambda: None)},
        class_elapsed=lambda: None, notes_toggle=lambda: None, open_notes_dir=lambda: None, redo=lambda f: None,
        redo_pick=lambda: None, class_folders=folders, gemini_on=lambda: True, ask_gemini=lambda: None,
        ask_groq=lambda: None, autostart_on=lambda: True, set_autostart=lambda on: None, open_log=lambda: None,
        vocab=lambda: list(fl.VOCAB), learn=fl.learn, unlearn=fl.unlearn, snippets=fl.load_snippets,
        save_snippets=fl.save_snippets,
        can_retry=lambda rid: rid == err_id, retry=lambda rid: (time.sleep(0.3), h.update(rid, "Texto recuperado al reintentar.", "copiado")),
        subjects=lambda: {"costos y precios": {"name": "Costos y Precios", "folders": [folders()[0][0]]},
                          "estadistica": {"name": "Estadistica", "folders": [folders()[1][0]]}},
        ask_classes=lambda q, f: (time.sleep(0.3), "**Punto de equilibrio** = Costos fijos ÷ Contribución marginal unitaria\n\n"
                                  "- Ejemplo: 100.000 ÷ 200 = **500 unidades** [Costos y Precios — 2026-10-17]")[1],
        study_guide=lambda f, n: "", guide_path=lambda n: None, quick_notes_path=os.path.join(tmp, "notas.txt"),
        notes_dir=lambda: fl.CONFIG["notes_dir"], set_notes_dir=lambda p, c=False: fl.CONFIG.update(notes_dir=p),
        drive_dir=lambda: r"G:\Mi unidad\FlowLite\Apuntes")
    return ctx, h, calls
