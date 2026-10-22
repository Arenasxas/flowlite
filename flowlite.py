"""FlowLite: dictado estilo Wispr Flow + apuntes de clases y reuniones.

Mantené Ctrl izq + Alt izq (o la tecla elegida en el panel), hablá, soltá: el texto se transcribe con
Whisper en Groq, un LLM lo pule y se pega en la app activa. Dos toques = grabación fija; tres = pausa.
vocabulary.json crece con las correcciones. Tocá la bolita para abrir el panel.
Ctrl+Alt+Shift = modo comando: decí qué hacer con el texto seleccionado ("pasalo a formal").
Apuntes de clase: graba el audio de la PC (Meet, Zoom, Teams) y/o el micrófono, transcribe
en vivo y al terminar arma apuntes de estudio con resumen, conceptos, tareas y preguntas.
"""
import ctypes
import difflib
import html
import json
import math
import os
import queue
import re
import subprocess
import sys
import shutil
import sqlite3
import threading
import time
import unicodedata
import warnings
import winreg
from ctypes import wintypes
from datetime import datetime, timedelta

import keyboard
import numpy as np
import pyperclip
import pystray
import requests
from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRadialGradient
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget)
import sounddevice as sd
import uiautomation as auto
from PIL import Image, ImageDraw
from types import SimpleNamespace
from panel import QSS, MeetingToast, Panel, Relay

VERSION = "2.2"
FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
if sys.stdout is None:
    sys.stdout = sys.stderr = open(os.path.join(HERE, "flowlite.log"), "a", encoding="utf-8", buffering=1)
warnings.simplefilter("ignore")  # soundcard avisa "data discontinuity" seguido; no sirve en el log


CONFIG = {
    "language": "es",
    "dictionary": {},
    "prompt": "Hola, ¿cómo estás? Bien, gracias. ¿Me podés ayudar con esto? Sí, claro: mañana a las diez.",
    "groq_stt_model": "whisper-large-v3-turbo",
    "groq_llm_model": "openai/gpt-oss-20b",
    "learn_window": 60,
    "notes_llm_model": "openai/gpt-oss-120b",
    "gemini_model": "gemini-3.8-flash",
    "notes_dir": os.path.join(HERE, "Apuntes"),  # no en Documentos: Defender (acceso controlado) bloquea programas sin firma
    "notes_chunk_seconds": 60,
    "notes_section_minutes": 8,
}
cfg_path = os.path.join(HERE, "config.json")
if os.path.exists(cfg_path):
    with open(cfg_path, encoding="utf-8") as f:
        CONFIG.update(json.load(f))

env_path = os.path.join(HERE, ".env")
if os.path.exists(env_path):
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            if "=" not in line or line.startswith("#"):
                continue
            k, v = line.strip().split("=", 1)
            os.environ.setdefault(k, v.strip().strip('"'))
GROQ_KEY = os.environ.get("GROQ_API_KEY")
GROQ = "https://api.groq.com/openai/v1"


def resource(*parts):
    """Archivo que viene con el programa (en el .exe está en _internal; en desarrollo, en la carpeta del proyecto)."""
    for base in (getattr(sys, "_MEIPASS", ""), HERE, os.path.dirname(HERE)):
        path = os.path.join(base, *parts)
        if base and os.path.exists(path):
            return path
    raise FileNotFoundError(os.path.join(*parts))


PROMPTS = json.load(open(resource("shared", "prompts.json"), encoding="utf-8"))
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")  # opcional: si está, los apuntes de clase los arma Gemini
GEMINI = "https://generativelanguage.googleapis.com/v1beta/models"


def save_env(name, value):
    """Guarda o reemplaza NOMBRE=valor en el .env, sin tocar las otras líneas."""
    lines = open(env_path, encoding="utf-8").read().splitlines() if os.path.exists(env_path) else []
    lines = [l for l in lines if not l.startswith(name + "=")] + ([f"{name}={value}"] if value else [])
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


_http = threading.local()


def http():
    """Una conexión por hilo que se reutiliza: evita el saludo TLS en cada dictado (más rápido)."""
    if not hasattr(_http, "s"):
        _http.s = requests.Session()
    return _http.s

VOCAB_PATH = os.path.join(HERE, "vocabulary.json")
# No viene en el .zip: así, al actualizar descomprimiendo encima, no se pierden las palabras aprendidas
VOCAB = json.load(open(VOCAB_PATH, encoding="utf-8-sig")) if os.path.exists(VOCAB_PATH) else ["FlowLite", "WhatsApp", "Groq"]


def learn(words):
    """Suma palabras nuevas al vocabulario (las que ya estaban, sin importar mayúsculas, se ignoran)."""
    known = {w.lower() for w in VOCAB}
    new = [w for w in dict.fromkeys(words) if w.lower() not in known]
    if new:
        VOCAB.extend(new)
        with open(VOCAB_PATH, "w", encoding="utf-8") as f:
            json.dump(VOCAB, f, ensure_ascii=False, indent=1)
    return new


CORR_PATH = os.path.join(HERE, "corrections.json")
CORRECTIONS = json.load(open(CORR_PATH, encoding="utf-8")) if os.path.exists(CORR_PATH) else {}

SNIPPETS_PATH = os.path.join(HERE, "snippets.json")
def read_field(ctrl):
    """Texto completo del campo enfocado (ValuePattern o TextPattern), o None."""
    for get in (lambda: ctrl.GetValuePattern().Value,
                lambda: ctrl.GetTextPattern().DocumentRange.GetText(-1)):
        try:
            text = get()
            if text:
                return text
        except Exception:
            pass
    return None


def edits_to_learn(dictated, before, after):
    """Compara el campo antes y después de que lo edites a mano: devuelve (dije, corregí) por palabra."""
    tok = lambda s: re.findall(r"\w+", s)
    said, a, b = set(tok(dictated)), tok(before), tok(after)
    pairs = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op != "replace" or i2 - i1 != j2 - j1:
            continue
        for old, new in zip(a[i1:i2], b[j1:j2]):
            plain = lambda w: unicodedata.normalize("NFD", w.lower()).encode("ascii", "ignore")
            if plain(old) == plain(new) and new.islower():
                continue  # solo cambió una tilde o mayúscula común: no vale la pena aprenderlo
            if old in said and old != new and difflib.SequenceMatcher(None, old.lower(), new.lower()).ratio() >= 0.5:
                pairs.append((old, new))
    return pairs


def watch_edits(dictated, notify):
    """Durante learn_window segundos mira si corregís a mano lo dictado, y aprende la corrección."""
    with auto.UIAutomationInitializerInThread():
        time.sleep(0.6)
        ctrl = auto.GetFocusedControl()
        before = read_field(ctrl) if ctrl else None
        if not before or dictated not in before:
            return
        rid, after, end = ctrl.GetRuntimeId(), before, time.time() + CONFIG["learn_window"]
        while time.time() < end:
            time.sleep(1.5)
            focused = auto.GetFocusedControl()
            if not focused or focused.GetRuntimeId() != rid:
                break
            after = read_field(ctrl) or after
        pairs = edits_to_learn(dictated, before, after)
        if pairs:
            for old, new in pairs:
                CORRECTIONS[old.lower()] = new
            with open(CORR_PATH, "w", encoding="utf-8") as f:
                json.dump(CORRECTIONS, f, ensure_ascii=False, indent=1)
            learn([new for _, new in pairs])
            notify("Aprendí: " + ", ".join(f"{o} → {n}" for o, n in pairs))


def whisper_prompt():
    # primero las palabras de IA y tecnología: si no entra todo, se corta el principio y queda el vocabulario propio
    return (", ".join(PROMPTS["tech_vocab"] + VOCAB[-40:]) + ". " + CONFIG["prompt"])[-800:]


TECH_FIXES = [(re.compile(rf"(?<!\w)(?:{p})(?!\w)", re.I), r) for p, r in PROMPTS["tech_fixes"]]


def fix_tech(text):
    """Errores típicos de Whisper con nombres de IA y tecnología ("Cloud Code" → "Claude Code"). Lista en prompts.json."""
    for rx, rep in TECH_FIXES:
        text = rx.sub(rep, text)
    return text


def prompt_echo(text):
    """Whisper con casi silencio a veces devuelve la lista de la ayuda: 3+ palabras y todas de esa lista."""
    words = plain_words(text).split()
    known = set(plain_words(" ".join(PROMPTS["tech_vocab"] + VOCAB)).split())
    return len(words) >= 3 and set(words) <= known


def stt_language():
    lang = CONFIG["language"]
    return {} if lang in ("", "auto") else {"language": lang}


def groq_post(path, timeout=30, tries=1, **kw):
    """POST a Groq. Con tries > 1, si Groq dice que se pasó el límite (429) espera lo que pide y reintenta."""
    for i in range(tries):
        r = http().post(f"{GROQ}{path}", timeout=timeout, headers={"Authorization": f"Bearer {GROQ_KEY}"}, **kw)
        if r.status_code == 429 and i < tries - 1:
            try:
                wait = float(r.headers.get("retry-after", 10))
            except ValueError:
                wait = 10
            print(f"Groq: límite alcanzado en {path}, espero {wait:.0f}s")
            time.sleep(min(wait, 90) + 1)
            continue
        r.raise_for_status()
        return r.json()


def wav_bytes(audio):
    import io
    import wave
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(SR), w.writeframes(pcm)
    return buf.getvalue()


def groq_transcribe(audio):
    data = {"model": CONFIG["groq_stt_model"], "prompt": whisper_prompt(), "response_format": "json", **stt_language()}
    r = groq_post("/audio/transcriptions", files={"file": ("audio.wav", wav_bytes(audio), "audio/wav")}, data=data)
    text = r["text"].strip()
    return "" if prompt_echo(text) else fix_tech(text)


POLISH = PROMPTS["polish"]


def groq_chat(system, user, model=None, timeout=30, tries=1, max_tokens=None):
    body = {"model": model or CONFIG["groq_llm_model"], "temperature": 0.2, "reasoning_effort": "low",
            "include_reasoning": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if max_tokens:
        body["max_completion_tokens"] = max_tokens
    r = groq_post("/chat/completions", timeout=timeout, tries=tries, json=body)
    return r["choices"][0]["message"]["content"].strip()


def gemini_chat(system, user, max_tokens=8000, tries=4, images=(), continuations=2):
    """Gemini (Google AI Studio). Ventana enorme: entra la transcripción entera de una clase de horas,
    y también puede mirar imágenes (capturas de diapositivas o del pizarrón). images: [(texto, bytes_jpg)].
    Si la respuesta se corta por largo (MAX_TOKENS), le pide que siga desde ahí hasta `continuations` veces."""
    import base64
    parts = [{"text": user}]
    for label, data in images:
        parts += [{"text": label}, {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(data).decode()}}]
    contents = [{"role": "user", "parts": parts}]
    model, out = CONFIG["gemini_model"], ""
    for _ in range(continuations + 1):
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens}}
        for i in range(tries):
            r = http().post(f"{GEMINI}/{model}:generateContent", timeout=300, json=body,
                            headers={"x-goog-api-key": GEMINI_KEY})
            if r.status_code == 404 and model != "gemini-flash-latest":
                print(f"Gemini: {model} ya no existe, uso gemini-flash-latest")
                model = "gemini-flash-latest"  # Google retira modelos viejos: el alias apunta siempre al Flash actual
                continue
            if r.status_code in (429, 500, 503) and i < tries - 1:
                print(f"Gemini ocupado ({r.status_code}), reintento")
                time.sleep(20 * (i + 1))
                continue
            if not r.ok:
                raise RuntimeError(f"Gemini {r.status_code}: {r.text[:300]}")
            break
        cand = r.json()["candidates"][0]
        piece = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
        out += piece
        if cand.get("finishReason") != "MAX_TOKENS" or not piece:
            break
        print("Gemini se cortó por largo: le pido que siga")
        contents = contents[:1] + [{"role": "model", "parts": [{"text": out}]},
                                   {"role": "user", "parts": [{"text": "Seguí exactamente desde donde te cortaste, "
                                                                       "sin repetir nada y con el mismo formato."}]}]
    return out.strip()


def groq_polish(text, app=""):
    vocab = VOCAB + [w for w in PROMPTS["tech_vocab"] if w.lower() not in {v.lower() for v in VOCAB}]
    return fix_tech(groq_chat(POLISH.format(vocab=", ".join(vocab), app=app or "desconocida"), text))


COMMAND = PROMPTS["command"]


def groq_command(instruction, selected, app=""):
    user = f"Instrucción: {instruction}\nApp: {app or 'desconocida'}\nTexto seleccionado:\n{selected or '(nada)'}"
    return groq_chat(COMMAND, user, model=CONFIG["notes_llm_model"], timeout=45)


SR = 16000
FILLERS = re.compile(r"\b(eh+|em+|este\.\.\.|mmm+|ehm+)\b[,.]?\s*", re.IGNORECASE)


class Recorder:
    def __init__(self):
        self.frames = []
        self.stream = None
        self.level = 0.0

    def _on_audio(self, data, *_):
        self.frames.append(data.copy())
        self.level = float(np.sqrt(np.mean(data ** 2)))

    def cancel(self):
        self.stop()
        self.level = 0.0

    def start(self):
        self.frames = []
        self.stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", callback=self._on_audio)
        self.stream.start()

    def stop(self):
        self.stream.stop()
        self.stream.close()
        return np.concatenate(self.frames).flatten() if self.frames else np.zeros(0, np.float32)


def clean(text):
    text = FILLERS.sub("", text).strip()
    for wrong, right in {**CORRECTIONS, **CONFIG["dictionary"]}.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", right, text, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", text)


def plain_words(s):
    s = unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"\w+", s))


def snippet_for(text):
    """Atajos de voz: si dijiste exactamente el disparador (p. ej. "mi mail"), devuelve el texto largo."""
    try:
        snippets = json.load(open(SNIPPETS_PATH, encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    said = plain_words(text)
    for cue, expansion in snippets.items():
        if said and plain_words(cue) == said:
            return expansion
    return None


EDITABLE = {"EditControl", "DocumentControl", "ComboBoxControl"}


def focus_is_editable():
    """¿El foco está en algo donde se puede escribir? (UI Automation)."""
    try:
        ctrl = auto.GetFocusedControl()
        if ctrl is None:
            return False
        if ctrl.ControlTypeName in EDITABLE:
            return True
        return not ctrl.GetValuePattern().IsReadOnly
    except Exception:
        return False


def paste(text):
    """Pega con Ctrl+V. Si había dónde escribir, devuelve el portapapeles como estaba; si no, deja el texto copiado."""
    editable = focus_is_editable()
    old = pyperclip.paste()
    pyperclip.copy(text)
    time.sleep(0.05)
    keyboard.send("ctrl+v")
    time.sleep(0.3)
    if editable:
        pyperclip.copy(old)
    return editable


def copy_selection():
    """Copia lo seleccionado en la app activa (Ctrl+C) sin perder el portapapeles. Devuelve (seleccion, portapapeles_viejo)."""
    old = pyperclip.paste()
    pyperclip.copy("")
    keyboard.send("ctrl+c")
    sel = ""
    for _ in range(10):
        time.sleep(0.05)
        sel = pyperclip.paste()
        if sel:
            break
    return sel, old


user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def window_title(h):
    n = user32.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, buf, n + 1)
    return buf.value


def foreground_app():
    """'whatsapp.exe — Título de la ventana' de la app activa, para adaptar el formato del dictado."""
    try:
        h = user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        hp = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        buf, size = ctypes.create_unicode_buffer(260), wintypes.DWORD(260)
        kernel32.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(size))
        kernel32.CloseHandle(hp)
        return f"{os.path.basename(buf.value)} — {window_title(h)[:80]}"
    except Exception:
        return ""


def visible_window_titles():
    titles = []

    def cb(h, _):
        if user32.IsWindowVisible(h):
            t = window_title(h)
            if t:
                titles.append(t)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return titles


MEETING_RX = re.compile(
    r"^\s*Meet\s*[-–:]\s|meet\.google\.com/[a-z]|Zoom Meeting|Reunión (de )?Zoom|"
    r"(Reunión|Meeting|Llamada|Call)\b.*\|\s*Microsoft Teams|Webex|Jitsi Meet|BigBlueButton", re.I)


def detect_meeting():
    for t in visible_window_titles():
        if MEETING_RX.search(t):
            return t
    return None


def meeting_name(title):
    """'Meet - Costos y Precios - Google Chrome' → 'Costos y Precios'."""
    t = re.sub(r"\s*[-–][^-–]*(Google Chrome|Microsoft\W*Edge|Firefox|Brave|Opera)\s*$", "", title or "")
    t = re.sub(r"\s+(y \d+ páginas? más|and \d+ more pages?)\s*$", "", t)  # Edge con varias pestañas
    t = re.sub(r"^\s*Meet\s*[-–:]\s*|\s*\|\s*Microsoft Teams\s*$", "", t)
    if re.fullmatch(r"[a-z]{3}-[a-z]{4}-[a-z]{3}", t.strip()):  # código de Meet, no dice nada
        return ""
    return t.strip()[:60]


class History:
    """Dictados: cuándo, cuánto audio, el texto, en qué app y si se pegó, solo se copió o falló."""

    def __init__(self):
        self.lock = threading.Lock()  # lo usan el hilo del dictado y el panel a la vez
        self.db = sqlite3.connect(os.path.join(HERE, "history.db"), check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS t (ts TEXT, seconds REAL, text TEXT)")
        for col in ("app", "status"):  # versiones viejas no tenían estas columnas
            try:
                self.db.execute(f"ALTER TABLE t ADD COLUMN {col} TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass

    def add(self, seconds, text, app="", status="pegado"):
        with self.lock:
            cur = self.db.execute("INSERT INTO t (ts, seconds, text, app, status) VALUES (?,?,?,?,?)",
                                  (datetime.now().isoformat(" ", "seconds"), seconds, text, app, status))
            self.db.commit()
            return cur.lastrowid

    def update(self, rowid, text, status):
        with self.lock:
            self.db.execute("UPDATE t SET text = ?, status = ? WHERE rowid = ?", (text, status, rowid))
            self.db.commit()

    def rows(self, query="", status="", limit=300):
        sql, args = "SELECT rowid, ts, seconds, text, app, status FROM t WHERE 1=1", []
        if query:
            sql += " AND text LIKE ?"
            args.append(f"%{query}%")
        if status:
            sql += " AND status = ?"
            args.append(status)
        with self.lock:
            return self.db.execute(sql + " ORDER BY ts DESC LIMIT ?", (*args, limit)).fetchall()

    def stats(self):
        """[(valor, explicación)] para las tarjetas del panel."""
        today = datetime.now().strftime("%Y-%m-%d")
        with self.lock:
            rows = self.db.execute("SELECT ts, seconds, text, status FROM t WHERE status != 'error'").fetchall()
        words = lambda rs: sum(len(t.split()) for _, _, t, _ in rs)
        tod = [r for r in rows if r[0].startswith(today)]
        talk = sum(r[1] or 0 for r in rows if r[3] != "comando") / 60  # minutos hablando
        ppm = words([r for r in rows if r[3] != "comando"]) / talk if talk > 0.2 else 0
        days = {r[0][:10] for r in rows}
        streak, d = 0, datetime.now().date()
        while d.isoformat() in days:  # días seguidos dictando, como la racha de Wispr Flow
            streak += 1
            d -= timedelta(days=1)
        saved = max(0, words(rows) / 40 - talk)  # tipear ~40 palabras por minuto
        return [(f"{words(tod):,}".replace(",", "."), f"palabras hoy · {len(tod)} dictados"),
                (f"{ppm:.0f} ppm" if ppm else "—", "velocidad hablando"),
                (f"{streak} día{'s' if streak != 1 else ''}", "racha dictando"),
                (f"{saved / 60:.1f} h" if saved >= 60 else f"{saved:.0f} min", "ahorrados vs. tipear")]

    def delete(self, rowid):
        with self.lock:
            self.db.execute("DELETE FROM t WHERE rowid = ?", (rowid,))
            self.db.commit()

    def clear(self):
        with self.lock:
            self.db.execute("DELETE FROM t")
            self.db.commit()


STATE_PATH = os.path.join(HERE, "state.json")


def load_state():
    try:
        return json.load(open(STATE_PATH, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(**kw):
    state = load_state()
    state.update(kw)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f)


SETTINGS = {"hotkey": "ctrl_alt", "language": "es", "polish": True, "sounds": False, "orb_visible": True,
            "orb_size": "normal", "quick_buttons": ["notes", "copy", "pause", "folder"], "detect_meetings": True}


def setting(key):
    return load_state().get(key, SETTINGS[key])


HOTKEYS = {  # nombre → (texto, teclas que hay que mantener juntas, como las nombra la librería keyboard)
    "ctrl_alt": ("Ctrl izq + Alt izq", [{"ctrl", "left ctrl"}, {"alt", "left alt"}]),
    "ctrl_win": ("Ctrl izq + Windows", [{"ctrl", "left ctrl"}, {"left windows", "windows"}]),
    "right_ctrl": ("Ctrl derecho (solo)", [{"right ctrl"}]),
    "f9": ("F9", [{"f9"}]),
    "f8": ("F8", [{"f8"}]),
}


def beep(freq):
    import winsound
    threading.Thread(target=winsound.Beep, args=(freq, 70), daemon=True).start()


def unlearn(word):
    if word in VOCAB:
        VOCAB.remove(word)
        with open(VOCAB_PATH, "w", encoding="utf-8") as f:
            json.dump(VOCAB, f, ensure_ascii=False, indent=1)


def load_snippets():
    try:
        return json.load(open(SNIPPETS_PATH, encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def save_snippets(data):
    with open(SNIPPETS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


class Orb(QWidget):
    """Esfera flotante estilo modo voz de ChatGPT: degradé con 'nubes' que giran adentro, halo suave
    y tamaño que sigue tu voz. Ventana transparente sin bordes; se arrastra y recuerda dónde quedó.
    Violeta = grabando una clase (podés seguir dictando igual)."""
    PALETTE = {"idle": ("#e1f5fe", "#4fc3f7", "#0277bd"), "rec": ("#ffebee", "#ef5350", "#b71c1c"),
               "busy": ("#fffde7", "#ffd54f", "#f57f17"), "paused": ("#eceff1", "#90a4ae", "#455a64"),
               "class": ("#f3e5f5", "#ba68c8", "#6a1b9a")}
    SPEED = {"idle": 0.03, "rec": 0.08, "busy": 0.14, "paused": 0.0, "class": 0.05}
    SIZE, R = 76, 21
    SCALES = {"small": 0.75, "normal": 1.0, "large": 1.3}
    clicked = Signal()
    menu_requested = Signal(QPoint)

    def __init__(self, level):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setCursor(Qt.SizeAllCursor)
        self.level, self.state, self.t, self.amp, self.drag = level, "idle", 0.0, 0.0, None
        self.in_class = False
        self.press_at = None
        self.set_scale(setting("orb_size"))
        try:
            self.move(*load_state()["orb"])
        except Exception:
            geo = QApplication.primaryScreen().availableGeometry()
            self.move(geo.right() - 130, geo.bottom() - 130)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.set("idle")
        self.show()

    def set(self, state):
        if state == "idle" and self.in_class:
            state = "class"
        self.state = state
        self.timer.start({"rec": 33, "busy": 33, "idle": 50, "class": 50, "paused": 500}[state])
        self.update()

    def set_scale(self, key):
        k = self.SCALES.get(key, 1.0)
        self.SIZE, self.R = int(76 * k), 21 * k
        self.resize(self.SIZE, self.SIZE)
        self.update()

    def set_class(self, on):
        self.in_class = on
        if self.state in ("idle", "class"):
            self.set("idle")

    def _tick(self):
        self.t += self.SPEED[self.state]
        target = min(self.level() * 20, 1.0) if self.state == "rec" else 0.3 if self.state == "busy" else 0.0
        self.amp += (target - self.amp) * 0.3
        self.update()

    def paintEvent(self, _):
        light, mid, dark = (QColor(c) for c in self.PALETTE[self.state])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        c = QPointF(self.SIZE / 2, self.SIZE / 2)
        r = self.R * (1 + 0.05 * math.sin(self.t * 2) + 0.28 * self.amp)

        def tint(col, alpha):
            col = QColor(col)
            col.setAlpha(alpha)
            return col

        g = min(r * 1.75, self.SIZE / 2)
        glow = QRadialGradient(c, g)
        glow.setColorAt(0.45, tint(mid, 110 + int(80 * self.amp)))
        glow.setColorAt(1.0, tint(mid, 0))
        p.setBrush(glow)
        p.drawEllipse(c, g, g)

        sphere = QPainterPath()
        sphere.addEllipse(c, r, r)
        p.setClipPath(sphere)
        base = QRadialGradient(QPointF(c.x() - r * 0.35, c.y() - r * 0.4), r * 1.7)
        base.setColorAt(0.0, light)
        base.setColorAt(0.45, mid)
        base.setColorAt(1.0, dark)
        p.fillPath(sphere, base)

        for k, ph, col, alpha in ((1.0, 0.0, light, 230), (1.4, 2.1, dark, 200), (0.7, 4.2, QColor("white"), 200)):
            pos = QPointF(c.x() + r * 0.6 * math.cos(self.t * k + ph), c.y() + r * 0.55 * math.sin(self.t * k * 1.3 + ph))
            cloud = QRadialGradient(pos, r * 0.7)
            cloud.setColorAt(0.0, tint(col, alpha))
            cloud.setColorAt(1.0, tint(col, 0))
            p.setBrush(cloud)
            p.drawEllipse(pos, r * 0.7, r * 0.7)
        shine = QRadialGradient(QPointF(c.x() - r * 0.4, c.y() - r * 0.45), r * 0.4)
        shine.setColorAt(0.0, QColor(255, 255, 255, 200))
        shine.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(shine)
        p.drawEllipse(QPointF(c.x() - r * 0.4, c.y() - r * 0.45), r * 0.4, r * 0.4)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.menu_requested.emit(e.globalPosition().toPoint())
            return
        self.drag = e.globalPosition().toPoint() - self.pos()
        self.press_at = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self.drag is not None:
            self.move(e.globalPosition().toPoint() - self.drag)

    def mouseReleaseEvent(self, e):
        moved = self.press_at is not None and (e.globalPosition().toPoint() - self.press_at).manhattanLength() > 5
        if self.drag is not None and not moved:
            self.clicked.emit()  # tocarla sin arrastrar abre el panel
        elif moved:
            save_state(orb=[self.x(), self.y()])
        self.drag = self.press_at = None


class Bridge(QObject):
    """Los hilos de audio y de la bandeja no pueden tocar la ventana: le avisan por señales."""
    state = Signal(str)
    quit = Signal()
    meeting = Signal(str)          # se detectó Meet/Zoom/Teams: ofrecer apuntes
    call = Signal(str, str)        # una app de llamadas abrió el micrófono: (título, tipo de apunte sugerido)
    notes_start = Signal(str)      # abrir el diálogo para empezar una clase (texto = título sugerido)
    notes_stop = Signal()
    notes_show = Signal()
    notes_text = Signal(str)       # nuevo tramo de transcripción
    notes_status = Signal(str)
    notes_done = Signal(str)       # ruta de los apuntes (o "" si falló)
    history_changed = Signal()
    show_panel = Signal()


class TapKeys:
    """Ctrl izq + Alt izq: mantener = dictar; 2 toques = grabación fija (un toque más la corta y transcribe);
    3 toques = pausar / reactivar FlowLite."""
    TAP, GAP = 0.35, 0.45

    def __init__(self, start, stop, cancel, toggle_pause, is_active):
        self.start, self.stop, self.cancel = start, stop, cancel
        self.toggle_pause, self.is_active = toggle_pause, is_active
        self.taps, self.last_tap, self.down_at = 0, 0.0, None
        self.consumed = self.recording = self.latched = False
        self.timer = None

    def down(self, now):
        if self.down_at is not None:
            return
        self.down_at = now
        self.taps = self.taps + 1 if now - self.last_tap < self.GAP else 1
        self.last_tap, self.consumed = now, False
        if self.timer:
            self.timer.cancel()
            self.timer = None
        if self.taps == 1:
            if self.latched:
                self.latched = self.recording = False
                self.consumed = True
                self.stop()
                return
            if self.is_active():
                self.recording = True
                self.start()

    def up(self, now):
        if self.down_at is None:
            return
        held, self.down_at = now - self.down_at, None
        if self.consumed:
            return
        if held >= self.TAP and self.taps == 1:
            if self.recording:
                self.recording = False
                self.stop()
            return
        self.timer = threading.Timer(self.GAP, self._decide)
        self.timer.start()

    def abort(self):
        """Ctrl+Alt+otra tecla es un atajo de otra app: descartar lo que se esté grabando."""
        if self.timer:
            self.timer.cancel()
            self.timer = None
        if self.recording:
            self.recording = self.latched = False
            self.cancel()
        self.taps, self.consumed = 0, True

    def _decide(self):
        self.timer = None
        if self.taps == 2 and self.recording:
            self.latched = True
            return
        if self.recording:
            self.recording = False
            self.cancel()
        if self.taps >= 3:
            self.toggle_pause()


SHIFT = {"shift", "left shift", "right shift"}


# ───────────────────────────── Apuntes de clases y reuniones ─────────────────────────────

SECTION = PROMPTS["section"]

CONDENSE = PROMPTS["condense"]

NOTE_TYPES = {k: v["label"] for k, v in PROMPTS["types"].items()}


def final_prompt(kind="clase", intro=None):
    """Prompt de apuntes finales para un tipo (clase, reunión, llamada, charla): intro + sintaxis + estructura + reglas."""
    t = PROMPTS["types"].get(kind) or PROMPTS["types"]["clase"]
    return f"{intro or t['intro']}\n{PROMPTS['final_syntax']}\n\n{t['structure']}\n\n{PROMPTS['final_rules']}"


FINAL = final_prompt("clase")
REVIEW = PROMPTS["review"]

DETAIL = PROMPTS["detail"]
DEFAULT_VOCAB = {"flowlite", "whatsapp", "groq", "padel"}  # vienen con el programa: no ayudan en una clase

HALLUCINATIONS = re.compile(r"amara\.org|subt[ií]tulos (realizados|por|hechos)|suscr[ií]b[ae]te|"
                            r"gracias por (ver|mirar)|^\W*(m[uú]sica|aplausos)\W*$", re.I)
SILENCE_RMS = 0.003  # por debajo, el tramo se toma como silencio
SECTION_LIMIT = 15000  # caracteres por pedido al LLM: el plan gratis de Groq acepta ~8000 tokens por minuto


def notes_root():
    """Carpeta de apuntes; si no se puede escribir ahí (carpeta protegida, permisos), usa AppData."""
    try:
        os.makedirs(CONFIG["notes_dir"], exist_ok=True)
    except OSError as e:
        print("No pude usar", CONFIG["notes_dir"], e)
        CONFIG["notes_dir"] = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "FlowLite", "Apuntes")
        os.makedirs(CONFIG["notes_dir"], exist_ok=True)
    return CONFIG["notes_dir"]


def clock(sec):
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def remove_quiet(path):
    try:
        os.remove(path)
    except OSError as e:
        print("No pude borrar", path, e)


def google_drive_dir():
    """Carpeta de FlowLite dentro de Google Drive para escritorio, si está instalado (G:\\Mi unidad, My Drive…)."""
    for letter in "GHIJKLMNOPQRSTUVWXYZDEF":
        for mine in ("Mi unidad", "My Drive"):
            d = f"{letter}:\\{mine}"
            if os.path.isdir(d):
                return os.path.join(d, "FlowLite", "Apuntes")
    return None


def safe_name(s):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s).strip(" .")[:60] or "Clase"


def junk_text(text, avoid=frozenset()):
    """¿Es basura de Whisper? Repite solo palabras de la ayuda (eco) o la misma frase en bucle."""
    words = plain_words(text).split()
    if not words or set(words) <= (set(avoid) | DEFAULT_VOCAB):
        return True
    return len(words) >= 12 and len(set(words)) / len(words) < 0.3


def groq_transcribe_segments(audio, prompt, avoid=frozenset()):
    """Transcribe un tramo y devuelve [(segundo, texto)], sin silencios ni frases inventadas por Whisper."""
    data = {"model": CONFIG["groq_stt_model"], "prompt": prompt[-600:], "response_format": "verbose_json",
            "temperature": 0, **stt_language()}
    r = groq_post("/audio/transcriptions", timeout=120, tries=4,
                  files={"file": ("audio.wav", wav_bytes(audio), "audio/wav")}, data=data)
    segs = r.get("segments") or [{"start": 0, "text": r.get("text", ""), "no_speech_prob": 0}]
    out = []
    for s in segs:
        text = s.get("text", "").strip()
        if (not text or s.get("no_speech_prob", 0) > 0.6 or HALLUCINATIONS.search(text)
                or s.get("compression_ratio", 0) > 2.4 or s.get("avg_logprob", 0) < -1.0 or junk_text(text, avoid)):
            continue  # silencio, frase inventada, bucle repetido o eco de la ayuda que le pasamos
        if len(out) >= 2 and out[-1][1] == text == out[-2][1]:
            continue  # Whisper repitiendo la misma frase en bucle
        out.append((float(s.get("start", 0)), fix_tech(text)))
    return out


BOX_ICONS = {"importante": "⚠️", "ojo": "👀", "ejemplo": "✏️", "tip": "💡", "duda": "❓", "resumen": "⏱️"}


LATEX = {"times": "×", "div": "÷", "cdot": "·", "approx": "≈", "leq": "≤", "geq": "≥", "neq": "≠", "pm": "±",
         "sum": "Σ", "sqrt": "√", "alpha": "α", "beta": "β", "mu": "μ", "sigma": "σ", "Delta": "Δ", "%": "%", "rightarrow": "→"}


def clean_math(md):
    """Los modelos a veces escriben fórmulas en LaTeX (con signos $ y comandos con barra): las pasa a texto común."""
    md = re.sub(r"\\[()\[\]]", "", md)  # delimitadores \( \) \[ \]
    md = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1) ÷ (\2)", md)
    md = re.sub(r"\\(?:text|mathrm|textbf|mathbf)\{([^{}]*)\}", r"\1", md)
    md = re.sub(r"\\([A-Za-z]+|%)", lambda m: LATEX.get(m.group(1), m.group(0)), md)
    md = md.replace("\\$", "\x00").replace("($)", "(\x00)")  # pesos de verdad
    md = re.sub(r"\$(?!\d)", "", md)  # lo que queda sin número detrás eran delimitadores de LaTeX
    return md.replace("\x00", "$").replace("\\,", " ")


def md_inline(s):
    s = html.escape(s)
    s = re.sub(r"==(.+?)==", r"<mark>\1</mark>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return re.sub(r"\s*(?:→|⇒|-&gt;|=&gt;)\s*", ' <b class="ar">→</b> ', s)


def md_block(kind, title, inner):
    """Bloques ::: del cuaderno: fichas de fórmula, recuadros, flujos, mapa y tarjetas de autoevaluación."""
    lines = [l for l in inner if l.strip()]
    if kind == "formula":
        rows = []
        for l in lines[1:]:
            m = re.match(r"^\s*[-*]?\s*([^:]{2,20}):\s*(.+)", l)
            rows.append(f'<div class="f-row"><span>{md_inline(m.group(1))}</span>{md_inline(m.group(2))}</div>' if m
                        else f"<p>{md_inline(l.strip())}</p>")
        eq = md_inline(lines[0].strip()) if lines else ""
        return (f'<div class="formula"><div class="f-name">📐 {md_inline(title or "Fórmula")}</div>'
                f'<div class="f-eq">{eq}</div>{"".join(rows)}</div>')
    if kind == "flujo":
        out = []
        for l in lines:
            steps = [x.strip(" -*") for x in re.split(r"→|⇒|->", l) if x.strip(" -*")]
            out.append('<div class="flujo">' + ' <b class="ar">→</b> '.join(
                f'<span class="node">{md_inline(x)}</span>' for x in steps) + "</div>")
        return "".join(out)
    if kind == "mapa":
        return f'<div class="mapa">{md_to_html(chr(10).join(inner), node=True)}</div>'
    if kind == "pregunta":
        return (f'<details class="q"><summary>{md_inline(title or "Pregunta")}</summary>'
                f'<div class="a">{md_to_html(chr(10).join(inner))}</div></details>')
    icon = BOX_ICONS.get(kind, "📌")
    head = f'<div class="box-t">{icon} {md_inline(title)}</div>' if title else f'<div class="box-t">{icon}</div>'
    return f'<div class="box {html.escape(kind)}">{head}{md_to_html(chr(10).join(inner))}</div>'


def md_table(rows):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows
             if not re.match(r"^\s*\|?[\s:|-]+\|?\s*$", r)]
    if not cells:
        return ""
    head = "".join(f"<th>{md_inline(c)}</th>" for c in cells[0])
    body = "".join("<tr>" + "".join(f"<td>{md_inline(c)}</td>" for c in r) + "</tr>" for r in cells[1:])
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def md_to_html(md, node=False):
    """Markdown (títulos, listas, negrita, tablas) + la sintaxis del cuaderno (::: bloques, >> margen, ==resaltado==)."""
    out, lists = [], []
    lines = md.splitlines()

    def close_lists(depth=0):
        while len(lists) > depth:
            out.append(f"</{lists.pop()}>")

    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        b = re.match(r"^\s*:::\s*([A-Za-záéíóúñ]+)\s*(.*)$", line)
        if b:  # bloque ::: tipo título … :::
            close_lists()
            inner = []
            while i < len(lines) and not re.match(r"^\s*:::\s*$", lines[i]):
                if re.match(r"^#{1,3}\s", lines[i]):
                    i -= 1  # la IA se olvidó de cerrar el bloque: termina antes del próximo título
                    break
                inner.append(lines[i])
                i += 1
            i += 1
            out.append(md_block(b.group(1).lower(), b.group(2).strip(), inner))
            continue
        if line.lstrip().startswith("|"):
            close_lists()
            rows = [line]
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(md_table(rows))
            continue
        img = re.match(r"^\s*!\[(.*?)\]\(((?:\.\./[^/\\()]+/)?capturas/\d{5}\.jpg)\)", line)
        if img:
            close_lists()
            out.append(f'<figure><img src="{html.escape(img.group(2))}" alt="{html.escape(img.group(1))}" loading="lazy">'
                       f'<figcaption>📸 {md_inline(img.group(1))}</figcaption></figure>')
            continue
        mg = re.match(r"^\s*&?gt;&?gt;\s*(.*)|^\s*>>\s*(.*)", line)
        if mg:
            out.append(f'<aside class="margin">{md_inline(mg.group(1) or mg.group(2) or "")}</aside>')
            continue
        m = re.match(r"^(\s*)([-*•]|\d+[.)])\s+(.*)", line)
        if m:
            depth = len(m.group(1).replace("\t", "  ")) // 2 + 1
            tag = "ol" if m.group(2)[0].isdigit() else "ul"
            close_lists(depth)
            if len(lists) == depth and lists[-1] != tag:  # pasó de viñetas a números (o al revés)
                close_lists(depth - 1)
            while len(lists) < depth:
                lists.append(tag)
                out.append(f"<{tag}>")
            text = m.group(3)
            task = re.match(r"^\[( |x|X)\]\s*(.*)", text)
            if task:
                done = " checked" if task.group(1) != " " else ""
                out.append(f'<li class="task"><label><input type="checkbox"{done}> {md_inline(task.group(2))}</label></li>')
            elif node:
                out.append(f'<li><span class="node">{md_inline(text)}</span></li>')
            else:
                out.append(f"<li>{md_inline(text)}</li>")
            continue
        close_lists()
        h = re.match(r"^(#{1,4})\s+(.*)", line)
        q = re.match(r"^\s*>\s?(.*)", line)
        if h:
            n = len(h.group(1))
            out.append(f"<h{n}>{md_inline(h.group(2))}</h{n}>")
        elif re.match(r"^\s*(-{3,}|\*{3,})\s*$", line):
            out.append("<hr>")
        elif q:
            out.append(f'<div class="box ojo">{md_inline(q.group(1))}</div>')
        elif line.strip():
            out.append(f"<p>{md_inline(line.strip())}</p>")
    close_lists()
    return "\n".join(out)


PAGE_TEMPLATE = open(resource("shared", "page.html"), encoding="utf-8").read()


def page_html(title, body, transcript=""):
    """Página de apuntes (la misma plantilla que usa la app del celular: shared/page.html)."""
    return (PAGE_TEMPLATE.replace("%%TITLE%%", title).replace("%%VERSION%%", VERSION)
            .replace("%%TRANSCRIPT%%", transcript).replace("%%BODY%%", body))


def build_notes(folder, title, segments, marks, my_notes, sections=None, status=print, missing=0, prefs=None, doubts=()):
    """Arma Apuntes.md y Apuntes.html en la carpeta de la clase. Devuelve la ruta del HTML.
    segments: [(segundo, texto)]; sections: apuntes parciales ya hechos durante la clase (o None)."""
    duration = clock(segments[-1][0]) if segments else "00:00"
    if not segments:
        raise RuntimeError("No hay nada transcripto: ¿sonaba la clase en la PC o en el micrófono?")
    md = None
    prefs = prefs or {}
    kind = prefs.get("type", "clase")
    system = final_prompt(kind).format(title=title, date=os.path.basename(folder)[:16].replace(".", ":"), duration=duration,
                          detail=DETAIL.get(prefs.get("detail"), DETAIL["normal"]),
                          extra=f"Indicaciones del alumno para esta materia (seguilas): {prefs['extra']}\n"
                          if prefs.get("extra") else "")
    caps = captures(folder)
    if GEMINI_KEY:
        status("Gemini está escribiendo los apuntes…")
        user = "TRANSCRIPCIÓN COMPLETA:\n" + section_text(segments, marks, doubts)
        if my_notes.strip():
            user += "\n\nNOTAS DEL ALUMNO (con el minuto en que las escribió):\n" + my_notes.strip()
        if caps:
            user += f"\n\nTE PASO {len(caps)} CAPTURAS DE LA CLASE, cada una con su minuto y su ruta."
        images = [(f"Captura del minuto {clock(sec)} — ruta: {rel}", open(os.path.join(folder, rel), "rb").read())
                  for sec, rel in caps]
        big = 32000 if prefs.get("detail") == "detallado" else 16000
        try:
            md = gemini_chat(system, user, max_tokens=big, images=images)
        except Exception as e:
            print("Gemini falló, sigo con Groq:", e)
        if md and prefs.get("detail") != "resumido":
            md = review_notes(md, segments, marks, doubts, my_notes, big, status)
    if md is None:
        md = groq_notes(system, segments, marks, doubts, my_notes, sections, status)
    md = clean_math(md)
    if generic_title(title):  # como Wispr Flow: si no pusiste nombre, el título lo saca de la clase
        m = re.search(r"^#\s+(.+)$", md, re.M)
        if m and not generic_title(m.group(1)):
            title = m.group(1).strip()[:70]
    left = [(sec, rel) for sec, rel in caps if rel not in md]  # las que la IA no ubicó (o Groq, que no ve imágenes)
    if left:
        md += "\n\n## Capturas de la clase\n" + "\n".join(f"![Minuto {clock(sec)}]({rel})" for sec, rel in left)
    if missing:
        md += f"\n\n> ⚠️ Faltan {missing} tramo(s) de audio sin transcribir (quedaron como pendiente_*.wav en la carpeta)."
    with open(os.path.join(folder, "Apuntes.md"), "w", encoding="utf-8") as f:
        f.write(md)
    transcript = "\n".join(f"<p><span>{clock(t)}</span>{html.escape(x)}</p>" for t, x in segments)
    page = page_html(html.escape(title), md_to_html(md), transcript)
    path = os.path.join(folder, "Apuntes.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    make_pdf(path)
    base = os.path.basename(folder)
    if generic_title(base[19:]) and not generic_title(title):  # renombrar la carpeta con el título nuevo
        new = os.path.join(os.path.dirname(folder), f"{base[:19]}{safe_name(title)}")
        try:
            if not os.path.exists(new):
                os.rename(folder, new)
                path = os.path.join(new, "Apuntes.html")
        except OSError as e:
            print("No pude renombrar la carpeta:", e)
    return path


def review_notes(md, segments, marks, doubts, my_notes, max_tokens, status=print):
    """Segunda pasada (como la de Wispr Flow, pero sobre los apuntes): un "profesor exigente" compara con la
    transcripción, agrega lo que falta y desarrolla lo flojo. Si algo sale mal, quedan los apuntes de la primera pasada."""
    status("Revisando que no falte nada y desarrollando lo importante…")
    user = (f"TRANSCRIPCIÓN:\n{section_text(segments, marks, doubts)}\n\n"
            + (f"NOTAS DEL ALUMNO:\n{my_notes.strip()}\n\n" if my_notes.strip() else "")
            + f"APUNTES A REVISAR:\n{md}")
    try:
        better = gemini_chat(REVIEW, user, max_tokens=max_tokens)
    except Exception as e:
        print("La revisión falló, quedan los apuntes de la primera pasada:", e)
        return md
    if len(better) < 0.8 * len(md) or not better.lstrip().startswith("#"):
        print(f"La revisión salió más corta o rara ({len(better)} vs {len(md)} caracteres): la descarto")
        return md
    return better


def find_browsers():
    """Navegadores que pueden imprimir a PDF sin ventana: Chrome y Edge (si uno falla, se prueba el otro;
    por ejemplo Edge no responde mientras tiene una actualización pendiente)."""
    out = []
    for rel in (("Google", "Chrome", "Application", "chrome.exe"), ("Microsoft", "Edge", "Application", "msedge.exe")):
        for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""),
                     os.environ.get("LOCALAPPDATA", "")):
            path = os.path.join(base, *rel)
            if base and os.path.exists(path) and path not in out:
                out.append(path)
                break
    return out


def make_pdf(html_path):
    """Apuntes.pdf con Chrome o Edge sin ventana, con las tarjetas de autoevaluación abiertas.
    Sirve para leerlos en cualquier celular, desde la app de Google Drive."""
    import tempfile
    pdf = html_path[:-5] + ".pdf"
    tmp = html_path[:-5] + ".imprimir.html"
    try:
        page = open(html_path, encoding="utf-8").read().replace('<details class="q">', '<details class="q" open>')
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(page)
        url = "file:///" + tmp.replace("\\", "/")
        for browser in find_browsers():
            profile = tempfile.mkdtemp(prefix="flowlite-pdf-")  # perfil propio: no choca con el navegador abierto
            try:
                subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                                f"--user-data-dir={profile}", f"--print-to-pdf={pdf}", url],
                               timeout=90, capture_output=True, creationflags=0x08000000)
            except Exception as e:
                print("No pude imprimir con", os.path.basename(browser), e)
            finally:
                shutil.rmtree(profile, ignore_errors=True)
            if os.path.exists(pdf) and os.path.getsize(pdf) > 0:
                return pdf
        print("No pude armar el PDF (ni Chrome ni Edge respondieron)")
        return None
    finally:
        if os.path.exists(tmp):
            remove_quiet(tmp)


def unfinished_classes(days=7):
    """Clases que se cortaron (se cerró FlowLite, se apagó la PC) y quedaron sin apuntes armados."""
    root, out, now = notes_root(), [], time.time()
    for name in sorted(os.listdir(root), reverse=True):
        f = os.path.join(root, name)
        tr = os.path.join(f, "transcripcion.txt")
        if name.startswith("_") or not os.path.exists(tr) or os.path.exists(os.path.join(f, "Apuntes.html")):
            continue
        if now - os.path.getmtime(tr) > days * 86400:
            continue
        segs = read_transcript(f)[0]
        if sum(len(x) for _, x in segs) >= 600:  # más que unos saludos
            out.append(f)
    return out


MIC_APPS = {"whatsapp": ("WhatsApp", "llamada"), "discord": ("Discord", "llamada"), "telegram": ("Telegram", "llamada"),
            "skype": ("Skype", "llamada"), "slack": ("Slack", "reunion"), "teams": ("Microsoft Teams", "reunion"),
            "zoom": ("Zoom", "clase"), "webex": ("Webex", "reunion")}


def mic_registry():
    """[(app, LastUsedTimeStop)] del registro de Windows: 0 = la app está usando el micrófono ahora."""
    base = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
    out = []

    def walk(path):
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            return
        with k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                if sub == "NonPackaged":
                    walk(path + "\\" + sub)
                    continue
                try:
                    with winreg.OpenKey(k, sub) as sk:
                        out.append((sub, winreg.QueryValueEx(sk, "LastUsedTimeStop")[0]))
                except OSError:
                    pass
    walk(base)
    return out


def apps_using_mic(read=mic_registry):
    """{"WhatsApp": "llamada", ...}: apps de llamadas que tienen el micrófono abierto ahora (detecta llamadas
    aunque no se vean en el título de la ventana). FlowLite y Wispr Flow no cuentan: son dictado."""
    found = {}
    for app, stop in read():
        low = app.lower()
        if stop != 0 or "flowlite" in low or "wispr" in low:
            continue
        for key, (label, kind) in MIC_APPS.items():
            if key in low:
                found[label] = kind
    return found


def generic_title(t):
    k = re.sub(r"\W|\d", "", plain_words(t or ""))
    return k in ("", "clase", "reunion", "llamada", "charla") or bool(re.fullmatch(r"llamadade\w+", k))


def captures(folder):
    """[(segundo, 'capturas/00123.jpg')] de las capturas de pantalla tomadas en la clase."""
    d = os.path.join(folder, "capturas")
    names = sorted(n for n in os.listdir(d) if re.fullmatch(r"\d{5}\.jpg", n)) if os.path.isdir(d) else []
    return [(int(n[:5]), f"capturas/{n}") for n in names][:40]


def groq_notes(system, segments, marks, doubts, my_notes, sections, status):
    """Groq gratis acepta ~8000 tokens por minuto: apuntes por tramos y después los finales."""
    if sections is None:
        sections = make_sections(segments, marks, status, doubts)
    if not sections:
        raise RuntimeError("No hay nada transcripto: ¿sonaba la clase en la PC o en el micrófono?")
    parts = list(sections)
    while sum(len(p) for p in parts) > SECTION_LIMIT and len(parts) > 1:
        status(f"Resumiendo {len(parts)} partes…")
        groups = [parts[i:i + 3] for i in range(0, len(parts), 3)]
        parts = [g[0] if len(g) == 1 else groq_chat(CONDENSE, "\n\n---\n\n".join(g), model=CONFIG["notes_llm_model"],
                                                    timeout=120, tries=5, max_tokens=2500) for g in groups]
    status("Escribiendo los apuntes finales…")
    user = "APUNTES PARCIALES:\n\n" + "\n\n---\n\n".join(parts)
    if my_notes.strip():
        user += "\n\nNOTAS DEL ALUMNO:\n" + my_notes.strip()
    if marks:
        user += "\n\nMOMENTOS MARCADOS COMO IMPORTANTES (⭐): " + ", ".join(clock(m) for m in marks)
    if doubts:
        user += "\n\nMOMENTOS QUE EL ALUMNO NO ENTENDIÓ (❓): " + ", ".join(clock(m) for m in doubts)
    return groq_chat(system, user, model=CONFIG["notes_llm_model"], timeout=180, tries=5, max_tokens=4000)


def section_text(segs, marks, doubts=()):
    lines = [(t, f"[{clock(t)}] {x}") for t, x in segs]
    if segs:
        lo, hi = segs[0][0], segs[-1][0] + 60
        lines += [(m, f"[{clock(m)}] ⭐ (el alumno marcó este momento como importante)") for m in marks if lo <= m < hi]
        lines += [(m, f"[{clock(m)}] ❓ (el alumno NO entendió lo que se dijo justo antes: explicalo mejor)")
                  for m in doubts if lo <= m < hi]
    return "\n".join(x for _, x in sorted(lines, key=lambda p: p[0]))


def make_sections(segments, marks, status=print, doubts=()):
    """Apuntes parciales cada notes_section_minutes de clase (o por tamaño, para no pasarse del límite de Groq)."""
    span, groups, cur = CONFIG["notes_section_minutes"] * 60, [], []
    for seg in segments:
        if cur and (seg[0] - cur[0][0] >= span or sum(len(x) for _, x in cur) > SECTION_LIMIT * 0.7):
            groups.append(cur)
            cur = []
        cur.append(seg)
    if cur:
        groups.append(cur)
    out = []
    for i, g in enumerate(groups, 1):
        status(f"Apuntes del tramo {i} de {len(groups)}…")
        out.append(groq_chat(SECTION, section_text(g, marks, doubts), model=CONFIG["notes_llm_model"],
                             timeout=120, tries=5, max_tokens=2000))
    return out


def read_transcript(folder):
    """Lee transcripcion.txt: devuelve (segmentos, marcas ⭐, dudas ❓), sin la basura que haya metido Whisper."""
    segs, marks, doubts = [], [], []
    avoid = set(plain_words(os.path.basename(folder)[19:]).split())
    path = os.path.join(folder, "transcripcion.txt")
    if not os.path.exists(path):
        return segs, marks, doubts
    for line in open(path, encoding="utf-8"):
        m = re.match(r"^\[(?:(\d+):)?(\d+):(\d+)\]\s?(.*)", line.strip())
        if not m:
            continue
        sec = int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        if m.group(4).startswith("⭐"):
            marks.append(sec)
        elif m.group(4).startswith("❓"):
            doubts.append(sec)
        elif m.group(4).startswith("📸"):
            continue
        elif m.group(4) and not junk_text(m.group(4), avoid):
            segs.append((sec, m.group(4)))
    return segs, marks, doubts


_SOUNDCARD = {}


def soundcard():
    """Importa soundcard en un hilo que queda vivo: así COM multihilo no se apaga entre una clase y otra,
    y no choca con el COM de un solo hilo que usa Qt en el hilo principal."""
    if "mod" not in _SOUNDCARD:
        ready = threading.Event()

        def keeper():
            try:
                import soundcard as sc
                _SOUNDCARD["mod"] = sc
            except Exception as e:
                _SOUNDCARD["err"] = e
            ready.set()
            threading.Event().wait()

        threading.Thread(target=keeper, daemon=True).start()
        ready.wait(15)
        if "mod" not in _SOUNDCARD:
            raise RuntimeError(f"no se pudo cargar el audio de Windows: {_SOUNDCARD.pop('err', 'tardó demasiado')}")
    return _SOUNDCARD["mod"]


class ClassNotes:
    """Graba una clase o reunión (audio de la PC y/o micrófono), la transcribe en tramos de ~1 minuto
    mientras sucede y va armando apuntes parciales; al terminar arma los apuntes finales."""
    SOURCES = {"pc": "Audio de la PC (Meet, Zoom, Teams, YouTube)",
               "mic": "Micrófono (clase presencial)",
               "both": "Ambos: audio de la PC + mi micrófono"}

    def __init__(self, title, source, on_text, on_status, on_done, prefs=None):
        self.title, self.source, self.prefs = title or "Clase", source, prefs or {}
        self.on_text, self.on_status, self.on_done = on_text, on_status, on_done
        stamp = datetime.now().strftime("%Y-%m-%d %H.%M")
        base = os.path.join(notes_root(), f"{stamp} - {safe_name(self.title)}")
        self.folder, n = base, 1
        while os.path.exists(self.folder):
            n += 1
            self.folder = f"{base} ({n})"
        os.makedirs(self.folder)
        with open(os.path.join(self.folder, "indicaciones.json"), "w", encoding="utf-8") as f:
            json.dump(self.prefs, f, ensure_ascii=False)
        self.keys = {"pc": ["pc"], "mic": ["mic"], "both": ["pc", "mic"]}[source]
        self.bufs = {k: [] for k in self.keys}
        self.lock = threading.Lock()
        self.stop_ev, self.pause_ev = threading.Event(), threading.Event()
        self.chunks = queue.Queue()
        self.offset = 0.0           # segundos de audio ya enviados a transcribir
        self.segments, self.marks, self.doubts, self.sections = [], [], [], []
        self.section_from = 0       # primer segmento que todavía no tiene apuntes parciales
        self.failed = 0
        self.my_notes = ""
        self.started = time.time()
        self.rec_threads = [threading.Thread(target=self._record, args=(k,), daemon=True) for k in self.keys]
        for t in self.rec_threads:
            t.start()
        threading.Thread(target=self._chunker, daemon=True).start()
        threading.Thread(target=self._transcriber, daemon=True).start()

    # ── grabación ──
    def _record(self, key):
        ctypes.windll.ole32.CoInitializeEx(None, 0)  # COM multihilo en este hilo (WASAPI lo necesita)
        try:
            sc = soundcard()
            if key == "pc":
                dev = sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)
            else:
                dev = sc.default_microphone()
            with dev.recorder(samplerate=SR, channels=1, blocksize=1600) as r:
                while not self.stop_ev.is_set():
                    data = r.record(numframes=1600).reshape(-1)
                    if not self.pause_ev.is_set():
                        with self.lock:
                            self.bufs[key].append(data.astype(np.float32))
        except Exception as e:
            print("Error grabando", key, e)
            with self.lock:
                self.bufs.pop(key, None)  # que la otra fuente siga sola
            self.on_status(f"No pude grabar {'el audio de la PC' if key == 'pc' else 'el micrófono'}: {e}")
        finally:
            ctypes.windll.ole32.CoUninitialize()

    def elapsed(self):
        with self.lock:
            buffered = max((sum(len(a) for a in b) for b in self.bufs.values()), default=0)
        return self.offset + buffered / SR

    def capture(self, pixmap):
        """Guarda una captura de pantalla (diapositiva, pizarrón) con el minuto de la clase."""
        sec = self.elapsed()
        os.makedirs(os.path.join(self.folder, "capturas"), exist_ok=True)
        rel = f"capturas/{int(sec):05d}.jpg"
        if pixmap.width() > 1600:
            pixmap = pixmap.scaledToWidth(1600, Qt.SmoothTransformation)
        pixmap.save(os.path.join(self.folder, rel), "JPG", 82)
        self._append(f"[{clock(sec)}] 📸 CAPTURA {rel}")
        return sec

    def mark(self, doubt=False):
        sec = self.elapsed()
        (self.doubts if doubt else self.marks).append(sec)
        self._append(f"[{clock(sec)}] {'❓ DUDA' if doubt else '⭐ MARCA'}")
        return sec

    def _take(self, final=False):
        """Saca del buffer un tramo de ~notes_chunk_seconds cortando en un silencio, mezclando PC + micrófono."""
        chunk = CONFIG["notes_chunk_seconds"] * SR
        with self.lock:
            if not self.bufs:
                return None
            arrays = {k: np.concatenate(b) if b else np.zeros(0, np.float32) for k, b in self.bufs.items()}
            n = max(len(a) for a in arrays.values()) if final else min(len(a) for a in arrays.values())
            if n == 0 or (not final and n < chunk):
                for k, a in arrays.items():
                    self.bufs[k] = [a] if len(a) else []
                return None
            if not final:
                n = self._quiet_cut(next(iter(arrays.values())), chunk)
            mix = np.zeros(n, np.float32)
            for k, a in arrays.items():
                part = a[:n]
                mix[:len(part)] += part
                self.bufs[k] = [a[n:]] if len(a) > n else []
        peak = float(np.max(np.abs(mix))) if len(mix) else 0
        return mix / peak * 0.9 if peak > 1 else mix

    @staticmethod
    def _quiet_cut(a, chunk):
        """Índice donde cortar: el momento más silencioso de los últimos 8 s del tramo, para no partir palabras."""
        win, lo = SR // 5, max(chunk - 8 * SR, 0)
        tail = a[lo:chunk]
        if len(tail) < win:
            return chunk
        frames = tail[:len(tail) // win * win].reshape(-1, win)
        return lo + int(np.argmin((frames ** 2).mean(axis=1))) * win + win // 2

    def _chunker(self):
        while not self.stop_ev.is_set():
            time.sleep(0.5)
            audio = self._take()
            if audio is not None:
                self.chunks.put((self.offset, audio))
                self.offset += len(audio) / SR
        for t in self.rec_threads:
            t.join(timeout=3)
        audio = self._take(final=True)
        if audio is not None and len(audio) > SR:
            self.chunks.put((self.offset, audio))
            self.offset += len(audio) / SR
        self.chunks.put(None)

    # ── transcripción y apuntes ──
    def _append(self, line):
        with open(os.path.join(self.folder, "transcripcion.txt"), "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _transcribe(self, start, audio):
        if float(np.sqrt(np.mean(audio ** 2))) < SILENCE_RMS:
            return []  # silencio: no gasta cupo de Groq ni deja que Whisper invente frases
        vocab = [w for w in VOCAB[-40:] if plain_words(w) not in DEFAULT_VOCAB]
        tail = " ".join(x for _, x in self.segments[-3:])
        prompt = f"{self.title}. {', '.join(vocab) + '. ' if vocab else ''}{tail}"
        avoid = set(plain_words(f"{self.title} {' '.join(vocab)}").split())  # si solo repite la ayuda, es eco
        return [(start + t, x) for t, x in groq_transcribe_segments(audio, prompt, avoid)]

    def _transcriber(self):
        pending = []  # (inicio, ruta wav) de tramos que fallaron por red o límite
        while True:
            item = self.chunks.get()
            if item is None:
                break
            start, audio = item
            wav = os.path.join(self.folder, f"pendiente_{int(start):05d}.wav")
            with open(wav, "wb") as f:
                f.write(wav_bytes(audio))  # si se corta la luz o internet, el audio queda para reintentar
            try:
                self._add(self._transcribe(start, audio))
                remove_quiet(wav)
            except Exception as e:
                print("Falló la transcripción del tramo", clock(start), e)
                pending.append((start, wav, audio))
                self.on_status(f"Sin conexión con Groq en {clock(start)}: lo reintento al final.")
            self._maybe_section()
        for start, wav, audio in pending:  # reintento al terminar
            try:
                self._add(self._transcribe(start, audio))
                remove_quiet(wav)
            except Exception as e:
                print("Sigue fallando", clock(start), e)
                self.failed += 1
        self._finish()

    def _add(self, segs):
        if not segs:
            return
        self.segments.extend(segs)
        self.segments.sort()
        for t, x in segs:
            self._append(f"[{clock(t)}] {x}")
        self.on_text("\n".join(f"[{clock(t)}] {x}" for t, x in segs))

    def _maybe_section(self, final=False):
        segs = self.segments[self.section_from:]
        if not segs:
            return
        long_enough = segs[-1][0] - segs[0][0] >= CONFIG["notes_section_minutes"] * 60
        too_big = sum(len(x) for _, x in segs) > SECTION_LIMIT * 0.7
        if GEMINI_KEY or not (final or long_enough or too_big):
            return  # con Gemini no hacen falta: lee la transcripción entera al final
        try:
            notes = groq_chat(SECTION, section_text(segs, self.marks, self.doubts), model=CONFIG["notes_llm_model"],
                              timeout=120, tries=5, max_tokens=2000)
        except Exception as e:
            print("Falló el apunte parcial", e)
            return  # se reintenta con el próximo tramo (o en build_notes si fue el último)
        self.sections.append(notes)
        self.section_from = len(self.segments)
        with open(os.path.join(self.folder, "parciales.md"), "a", encoding="utf-8") as f:
            f.write(f"\n\n<!-- hasta {clock(segs[-1][0])} -->\n{notes}")

    def _finish(self):
        try:
            if self.my_notes.strip():
                with open(os.path.join(self.folder, "mis_notas.txt"), "w", encoding="utf-8") as f:
                    f.write(self.my_notes)
            self.on_status("Armando los apuntes…")
            self._maybe_section(final=True)
            sections = self.sections if self.section_from >= len(self.segments) else None
            path = build_notes(self.folder, self.title, self.segments, self.marks, self.my_notes,
                               sections=sections, status=self.on_status, missing=self.failed,
                               prefs=self.prefs, doubts=self.doubts)
            self.on_done(path)
        except Exception as e:
            print("No pude armar los apuntes:", e)
            self.on_status(f"No pude armar los apuntes: {e}. La transcripción quedó en la carpeta; "
                           "probá después con «Rehacer apuntes de una clase…».")
            self.on_done("")

    # ── control ──
    def pause(self, on):
        (self.pause_ev.set if on else self.pause_ev.clear)()

    def stop(self, my_notes=""):
        self.my_notes = my_notes
        self.stop_ev.set()


RECAP = PROMPTS["recap"]

QUESTION = PROMPTS["question"]

ASK = PROMPTS["ask"]

GUIDE = final_prompt("clase", PROMPTS["guide_intro"])


def live_help(kind, segments, minutes=5):
    """«¿Qué me perdí?» o «sugerime preguntas» con lo último de la clase (rápido: Groq)."""
    if not segments:
        return "Todavía no hay transcripción: esperá un minuto."
    last = segments[-1][0]
    recent = [s for s in segments if s[0] >= last - minutes * 60]
    text = "\n".join(f"[{clock(t)}] {x}" for t, x in recent)[-9000:]
    return clean_math(groq_chat(RECAP if kind == "recap" else QUESTION, text, timeout=40, tries=2, max_tokens=700))


def class_notes_text(folder, limit=None):
    """Apuntes.md de una clase (o su transcripción si todavía no hay apuntes)."""
    for name in ("Apuntes.md", "transcripcion.txt"):
        f = os.path.join(folder, name)
        if os.path.exists(f):
            return open(f, encoding="utf-8").read()[:limit]
    return ""


def ask_classes(question, folders):
    """Pregunta sobre tus clases: Gemini lee todas; Groq solo las 3 que más se parecen a la pregunta."""
    q = set(plain_words(question).split())
    docs = []
    for f in folders:
        name = os.path.basename(f)
        body = class_notes_text(f)
        if body:
            score = len(q & set(plain_words(body[:20000]).split()))
            docs.append((score, f"### [{name[19:] or 'Clase'} — {name[:10]}]\n{body}"))
    if not docs:
        return "Todavía no hay clases con apuntes para responder."
    if GEMINI_KEY:
        try:
            return clean_math(gemini_chat(ASK, f"PREGUNTA: {question}\n\nAPUNTES:\n\n" +
                                          "\n\n".join(d for _, d in docs)[:600000], max_tokens=2000))
        except Exception as e:
            print("Gemini falló al responder, sigo con Groq:", e)
    best = [d[:4000] for _, d in sorted(docs, key=lambda x: -x[0])[:3]]
    return clean_math(groq_chat(ASK, f"PREGUNTA: {question}\n\nAPUNTES:\n\n" + "\n\n".join(best),
                                model=CONFIG["notes_llm_model"], timeout=60, tries=3, max_tokens=1500))


def study_guide(folders, subject, status=print):
    """Une los apuntes de todas las clases de una materia en un resumen para el parcial (HTML tipo cuaderno)."""
    folders = sorted(folders)
    parts = [f"## Clase del {os.path.basename(f)[:10]}\n" +
             class_notes_text(f).replace("](capturas/", f"](../{os.path.basename(f)}/capturas/")  # el resumen vive en _Resúmenes
             for f in folders if class_notes_text(f)]
    if not parts:
        raise RuntimeError("Esa materia todavía no tiene clases con apuntes.")
    title = f"{subject} — resumen para el parcial"
    system = GUIDE.format(title=title, date=datetime.now().strftime("%Y-%m-%d"),
                          duration=f"{len(parts)} clases", detail=DETAIL["normal"], extra="")
    md = None
    if GEMINI_KEY:
        status("Gemini está uniendo tus clases…")
        try:
            md = gemini_chat(system, "APUNTES DE LAS CLASES (en orden):\n\n" + "\n\n---\n\n".join(parts), max_tokens=20000)
        except Exception as e:
            print("Gemini falló en el resumen, sigo con Groq:", e)
    if md is None:
        md = groq_notes(system, [], [], [], "", parts, status)
    md = clean_math(md)
    out_dir = os.path.join(notes_root(), "_Resúmenes")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{safe_name(subject)} - parcial {datetime.now():%Y-%m-%d}.html")
    with open(path[:-5] + ".md", "w", encoding="utf-8") as f:
        f.write(md)
    with open(path, "w", encoding="utf-8") as f:
        f.write(page_html(html.escape(title), md_to_html(md)))
    make_pdf(path)
    return path


def redo_notes(folder, status):
    """Rehace los apuntes de una clase ya grabada desde su transcripcion.txt (y transcribe los pendientes)."""
    segs, marks, doubts = read_transcript(folder)
    missing = 0
    for name in sorted(os.listdir(folder)):
        m = re.match(r"pendiente_(\d+)\.wav$", name)
        if not m:
            continue
        import wave
        status(f"Transcribiendo {name}…")
        with wave.open(os.path.join(folder, name)) as w:
            audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32767
        try:
            start = int(m.group(1))
            segs += [(start + t, x) for t, x in groq_transcribe_segments(audio, os.path.basename(folder))]
            os.remove(os.path.join(folder, name))
        except Exception as e:
            print("Pendiente sin transcribir", name, e)
            missing += 1
    segs.sort()
    notes_path = os.path.join(folder, "mis_notas.txt")
    my_notes = open(notes_path, encoding="utf-8").read() if os.path.exists(notes_path) else ""
    title = os.path.basename(folder)[19:] or "Clase"
    prefs_path = os.path.join(folder, "indicaciones.json")
    prefs = json.load(open(prefs_path, encoding="utf-8")) if os.path.exists(prefs_path) else {}
    return build_notes(folder, title, segs, marks, my_notes, status=status, missing=missing, prefs=prefs, doubts=doubts)


def subject_key(title):
    """'Costos y Precios — clase 8' → 'costos y precios': las preferencias valen para toda la materia."""
    t = re.split(r"\s[-–—:|]\s", title)[0]
    return re.sub(r"\b(clase|unidad|tema|parte)\b|\d+", " ", plain_words(t)).strip() or "general"


class StartDialog(QDialog):
    def __init__(self, suggested, kind="clase"):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.suggested_kind = kind
        self.setWindowTitle("FlowLite — tomar apuntes")
        self.title = QLineEdit(suggested)
        self.title.setPlaceholderText("Ej.: Costos y Precios — clase 8")
        self.source = QComboBox()
        for key, label in ClassNotes.SOURCES.items():
            self.source.addItem(label, key)
        self.source.setCurrentIndex(max(self.source.findData(load_state().get("notes_source", "pc")), 0))
        form = QFormLayout(self)
        form.addRow(QLabel("Graba la clase o llamada, la transcribe en vivo y al terminar te arma los apuntes.\n"
                           "Usá auriculares si elegís «Ambos», así el micrófono no repite el audio de la PC."))
        self.kind = QComboBox()
        for key, label in NOTE_TYPES.items():
            self.kind.addItem(label, key)
        self.detail = QComboBox()
        for key, label in (("resumido", "Resumido: para repasar rápido"), ("normal", "Normal: apuntes completos"),
                           ("detallado", "Muy detallado: como para estudiar sin haber ido")):
            self.detail.addItem(label, key)
        self.extra = QPlainTextEdit()
        self.extra.setPlaceholderText("Opcional, se recuerda para esta materia. Ej.: «Poné siempre la fórmula con un "
                                      "ejemplo numérico», «El prorrateo de la cátedra es por horas máquina», "
                                      "«Comparame los métodos en una tabla».")
        self.extra.setFixedHeight(70)
        form.addRow("Materia o tema:", self.title)
        form.addRow("Qué grabar:", self.source)
        form.addRow("Tipo:", self.kind)
        form.addRow("Detalle:", self.detail)
        form.addRow("Cómo querés\nlos apuntes:", self.extra)
        self.title.textChanged.connect(self.load_prefs)
        self.load_prefs()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Empezar a grabar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.resize(540, 0)

    def load_prefs(self):
        p = load_state().get("notes_prefs", {}).get(subject_key(self.title.text()), {})
        self.kind.setCurrentIndex(max(self.kind.findData(p.get("type", self.suggested_kind)), 0))
        self.detail.setCurrentIndex(max(self.detail.findData(p.get("detail", "normal")), 0))
        self.extra.setPlainText(p.get("extra", ""))

    def prefs(self):
        p = {"type": self.kind.currentData(), "detail": self.detail.currentData(), "extra": self.extra.toPlainText().strip()}
        all_prefs = load_state().get("notes_prefs", {})
        all_prefs[subject_key(self.title.text())] = p
        save_state(notes_prefs=all_prefs)
        return p


class ClassWindow(QWidget):
    """Ventana de la clase en curso: tus notas arriba, la transcripción en vivo abajo."""

    def __init__(self, notes, on_stop):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.notes, self.on_stop, self.paused, self.finished = notes, on_stop, False, False
        self.setWindowTitle(f"FlowLite — {notes.title}")
        self.header = QLabel()
        self.header.setStyleSheet("font-size:15px;font-weight:600;color:#ab47bc")
        self.status = QLabel("Escuchando… la transcripción aparece cada ~1 minuto.")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color:gray")
        self.mine = QPlainTextEdit()
        self.mine.setPlaceholderText("Tus notas (opcional): lo que escribas acá se suma a los apuntes con prioridad.")
        self.live = QPlainTextEdit()
        self.live.setReadOnly(True)
        self.live.setPlaceholderText("Transcripción en vivo…")
        split = QSplitter(Qt.Vertical)
        for label, w in (("Mis notas", self.mine), ("Transcripción en vivo", self.live)):
            box = QWidget()
            lay = QVBoxLayout(box)
            lay.setContentsMargins(0, 4, 0, 0)
            lay.addWidget(QLabel(f"<b>{label}</b>"))
            lay.addWidget(w)
            split.addWidget(box)
        self.mark_btn = QPushButton("⭐ Importante")
        self.mark_btn.clicked.connect(self.mark)
        self.cap_btn = QPushButton("📸 Captura")
        self.cap_btn.setToolTip("Guarda lo que se ve en la pantalla (diapositiva, pizarrón): va a los apuntes explicado.")
        self.cap_btn.clicked.connect(self.capture)
        self.line_times = []  # minuto en que empezaste a escribir cada línea de "Mis notas"
        self.doubt_btn = QPushButton("❓ No entendí")
        self.doubt_btn.setToolTip("Marca este momento: en los apuntes se explica mejor, en «Dudas para consultar».")
        self.doubt_btn.clicked.connect(self.doubt)
        self.help_btn = QPushButton("✨ Ayuda")
        self.help_btn.setToolTip("¿Qué me perdí? (últimos 5 minutos) o una pregunta para hacerle al profe")
        self.help_btn.clicked.connect(self.show_help_menu)
        self.helper = QLabel()
        self.helper.setWordWrap(True)
        self.helper.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.helper.setStyleSheet("background:rgba(139,92,246,0.14);border:1px solid #8b5cf6;border-radius:10px;padding:8px;")
        self.helper.hide()
        self.help_relay = Relay()
        self.help_relay.done.connect(self._help_done)
        self.pause_btn = QPushButton("⏸ Pausar")
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.stop_btn = QPushButton("⏹ Terminar y armar apuntes")
        self.stop_btn.setStyleSheet("font-weight:600")
        self.stop_btn.clicked.connect(self.stop)
        self.open_btn = QPushButton("Abrir apuntes")
        self.open_btn.hide()
        row = QHBoxLayout()
        for b in (self.mark_btn, self.doubt_btn, self.cap_btn, self.help_btn, self.pause_btn, self.stop_btn, self.open_btn):
            row.addWidget(b)
        lay = QVBoxLayout(self)
        lay.addWidget(self.header)
        lay.addWidget(self.status)
        lay.addWidget(self.helper)
        lay.addWidget(split, 1)
        lay.addLayout(row)
        self.resize(560, 640)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self._tick()
        self.show()

    def _tick(self):
        if self.notes.stop_ev.is_set():
            return
        state = "⏸ En pausa" if self.paused else "● Grabando"
        self.header.setText(f"{state} · {self.notes.title} · {clock(self.notes.elapsed())}")
        self.notes.my_notes = self.stamped_notes()

    def stamped_notes(self):
        """Tus notas con el minuto de cada línea, así la IA las pone al margen del tema justo."""
        lines = self.mine.toPlainText().splitlines()
        now = self.notes.elapsed()
        while len(self.line_times) < len(lines):
            self.line_times.append(None)
        out = []
        for i, line in enumerate(lines):
            if line.strip() and self.line_times[i] is None:
                self.line_times[i] = now
            if line.strip():
                out.append(f"[{clock(self.line_times[i])}] {line.strip()}")
        return "\n".join(out)

    def capture(self):
        self.hide()  # que la ventana de FlowLite no tape la diapositiva
        QTimer.singleShot(300, self._grab)

    def _grab(self):
        from PySide6.QtGui import QCursor
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        try:
            sec = self.notes.capture(screen.grabWindow(0))
            self.live.appendPlainText(f"[{clock(sec)}] 📸 captura guardada")
        except Exception as e:
            self.status.setText(f"No pude capturar la pantalla: {e}")
        self.show()

    def add_text(self, text):
        self.live.appendPlainText(text)

    def set_status(self, text):
        self.status.setText(text)

    def mark(self):
        sec = self.notes.mark()
        self.live.appendPlainText(f"[{clock(sec)}] ⭐ marcado")

    def show_help_menu(self):
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("⏪ ¿Qué me perdí? (últimos 5 min)", lambda: self.ask_help("recap"))
        m.addAction("💬 Sugerime una pregunta para el profe", lambda: self.ask_help("question"))
        m.exec(self.help_btn.mapToGlobal(self.help_btn.rect().topLeft()))

    def ask_help(self, kind):
        self.helper.setText("✨ Pensando…")
        self.helper.show()
        segs = list(self.notes.segments)
        Relay.run(lambda: live_help(kind, segs), self.help_relay)

    def _help_done(self, result):
        ok, text = result
        title = "Lo último de la clase" if "•" not in (text or "")[:3] else "Preguntas para el profe"
        body = md_to_html(text or "").replace("<p>", "").replace("</p>", "<br>").replace("<br>\n<ul>", "<ul>")
        body = body.replace("<ul>", "<ul style='margin:2px 0 0 -18px'>")
        self.helper.setText(f"<b>✨ {title}</b><br>{body}" if ok else f"No pude ayudarte ahora: {text}")

    def doubt(self):
        sec = self.notes.mark(doubt=True)
        self.live.appendPlainText(f"[{clock(sec)}] ❓ no entendí")

    def toggle_pause(self):
        self.paused = not self.paused
        self.notes.pause(self.paused)
        self.pause_btn.setText("▶ Reanudar" if self.paused else "⏸ Pausar")
        self._tick()

    def stop(self):
        if self.notes.stop_ev.is_set():
            return
        for b in (self.mark_btn, self.doubt_btn, self.cap_btn, self.help_btn, self.pause_btn, self.stop_btn):
            b.setEnabled(False)
        self.header.setText(f"⏳ Armando apuntes · {self.notes.title} · {clock(self.notes.elapsed())}")
        self.status.setText("Termino de transcribir y armo los apuntes. Puede tardar uno o dos minutos…")
        self.on_stop(self.stamped_notes())

    def done(self, path):
        self.finished = True
        if path:
            self.header.setText(f"✅ Apuntes listos · {self.notes.title}")
            self.status.setText(path)
            self.open_btn.clicked.connect(lambda: os.startfile(path))
            self.open_btn.show()

    def closeEvent(self, e):
        if self.finished:
            return e.accept()
        e.ignore()
        self.hide()  # sigue grabando; se vuelve a abrir desde la bandeja


def probe_audio():
    """FlowLite.exe --probar-audio: graba 3 s de la PC y del micrófono con el mismo camino que las clases."""
    run = ClassNotes("Prueba de audio", "both", lambda t: None, print, lambda p: None)
    time.sleep(3)
    with run.lock:
        for k, b in run.bufs.items():
            a = np.concatenate(b) if b else np.zeros(0, np.float32)
            print(f"probar-audio {k}: {len(a) / SR:.1f}s, volumen {float(np.sqrt(np.mean(a ** 2))) if len(a) else 0:.4f}")
    run.stop_ev.set()
    time.sleep(1)
    import shutil
    shutil.rmtree(run.folder, ignore_errors=True)


def key_ok(service, key):
    """True si la clave anda, False si el servicio la rechaza, None si no se pudo comprobar (sin internet)."""
    try:
        if service == "groq":
            r = requests.get(f"{GROQ}/models", headers={"Authorization": f"Bearer {key}"}, timeout=10)
        else:
            r = requests.get(GEMINI, headers={"x-goog-api-key": key}, timeout=10)
    except requests.RequestException:
        return None
    return False if r.status_code in (400, 401, 403) else True if r.ok else None


def ask_gemini_key():
    """Pide la clave de Gemini, la comprueba y la guarda. Devuelve True si quedó una clave válida."""
    global GEMINI_KEY
    msg = ("Con una clave de Gemini los apuntes de clase salen mejores y más rápidos\n"
           "(lee la clase entera de una vez). Sacala gratis en aistudio.google.com/apikey\n"
           "Dejalo vacío para usar solo Groq.")
    while True:
        key, ok = QInputDialog.getText(None, "FlowLite — Gemini para apuntes (opcional)", msg, text=GEMINI_KEY or "")
        if not ok:
            return bool(GEMINI_KEY)
        key = key.strip()
        if key and key_ok("gemini", key) is False:
            msg = "Esa clave no funciona en Gemini. Copiala de nuevo desde aistudio.google.com/apikey:"
            continue
        GEMINI_KEY = key or None
        save_env("GEMINI_API_KEY", key)
        if key:
            QMessageBox.information(None, "FlowLite", "Listo: los apuntes de clase los arma Gemini.")
        return bool(GEMINI_KEY)


def desktop_shortcut():
    """Acceso directo en el escritorio (lo crea PowerShell, que Windows deja escribir en el escritorio)."""
    if not FROZEN:
        return
    exe = sys.executable.replace("'", "''")
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\\FlowLite.lnk');"
          f"$s.TargetPath='{exe}';$s.WorkingDirectory='{HERE.replace(chr(39), chr(39) * 2)}';"
          "$s.Description='FlowLite: dictado y apuntes de clase';$s.Save()")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], timeout=20, creationflags=0x08000000)
    except Exception as e:
        print("No pude crear el acceso directo:", e)


def main():
    global GROQ_KEY
    if "--probar-audio" in sys.argv:
        return probe_audio()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    # Una sola copia abierta: dos copias escucharían Ctrl+Alt a la vez y escribirían todo doble
    ctypes.windll.kernel32.CreateMutexW(None, False, "FlowLite-una-sola-copia")  # queda abierto hasta salir
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        QMessageBox.information(None, "FlowLite", "FlowLite ya está abierto: buscá la esfera en la pantalla "
                                                  "o el ícono al lado del reloj (quizás en la flechita ^).")
        return

    msg = ("Pegá tu clave de Groq (console.groq.com/keys → Create API Key; empieza con gsk_).\n"
           "Se guarda solo en esta PC, en el archivo .env junto al programa:")
    first = not GROQ_KEY
    while not GROQ_KEY or key_ok("groq", GROQ_KEY) is False:
        key, ok = QInputDialog.getText(None, "FlowLite — clave de Groq", msg)
        if not ok or not key.strip():
            GROQ_KEY = None
            break
        if key_ok("groq", key.strip()) is False:
            msg = ("Esa clave no funciona en Groq. Copiá de nuevo la que empieza con gsk_\n"
                   "desde console.groq.com/keys (no pegues contraseñas acá):")
            continue
        GROQ_KEY = key.strip()
        save_env("GROQ_API_KEY", GROQ_KEY)
    if first and GROQ_KEY:
        desktop_shortcut()
    if not GROQ_KEY:
        QMessageBox.warning(None, "FlowLite", "Sin clave de Groq FlowLite no puede transcribir.\n"
                                              "Abrilo de nuevo cuando la tengas.")
        return

    CONFIG["language"] = setting("language")
    if load_state().get("notes_dir"):  # carpeta elegida en Ajustes (p. ej. Google Drive para sincronizar con el celular)
        CONFIG["notes_dir"] = load_state()["notes_dir"]
    rec, hist = Recorder(), History()
    bridge = Bridge()
    orb = Orb(level=lambda: rec.level)
    bridge.state.connect(orb.set)
    set_state = bridge.state.emit
    jobs = queue.Queue()
    last = {"text": ""}
    active = threading.Event()
    active.set()
    mode = {"cmd": False, "app": ""}

    def start_rec():
        mode["cmd"], mode["app"] = keyboard.is_pressed("shift"), foreground_app()
        rec.start()
        set_state("rec")
        if setting("sounds"):
            beep(880)

    def stop_rec():
        jobs.put((rec.stop(), mode["cmd"], mode["app"]))
        if setting("sounds"):
            beep(620)

    def cancel_rec():
        rec.cancel()
        set_state("idle" if active.is_set() else "paused")

    def worker():
        with auto.UIAutomationInitializerInThread():
            work()

    def transcribe(audio):
        try:
            return groq_transcribe(audio), "groq"
        except Exception as e:
            print("Groq falló:", e)
            raise RuntimeError(f"sin conexión con Groq ({str(e)[:80]})")

    def work():
        while True:
            audio, cmd, app_name = jobs.get()
            seconds = len(audio) / SR
            if seconds < 0.3:
                set_state("idle")
                continue
            set_state("busy")
            t0 = time.time()
            status = "pegado"
            try:
                text, engine = transcribe(audio)
                if text and cmd and GROQ_KEY:
                    selected, old_clip = copy_selection()
                    text = groq_command(text, selected, app_name)
                    engine = status = "comando"
                    paste(text)
                    pyperclip.copy(old_clip)
                elif text:
                    expansion = snippet_for(text)
                    if expansion:
                        text, engine = expansion, "atajo"
                    elif engine == "groq" and len(text.split()) > 3 and setting("polish"):  # 1-3 palabras: Whisper ya puntúa
                        try:
                            text = groq_polish(text, app_name)
                            engine = "groq+llm"
                            text = snippet_for(text) or text
                        except Exception as e:
                            print("El LLM falló, pego la transcripción cruda:", e)
                    text = clean(text) if engine != "atajo" else text
                    if engine == "atajo":
                        status = "atajo"
                    if text and not paste(text + " "):
                        status = "copiado"
                        tray.notify("No había dónde pegar: el dictado quedó copiado, pegalo con Ctrl+V.", "FlowLite")
                if text:
                    hist.add(seconds, text, app_name, status)
                    bridge.history_changed.emit()
                    last["text"] = text
                    if engine not in ("comando", "atajo"):
                        threading.Thread(target=watch_edits, daemon=True,
                                         args=(text, lambda msg: tray.notify(msg, "FlowLite"))).start()
                print(f"[{engine} {seconds:.1f}s audio → {time.time() - t0:.1f}s] {text}")
            except Exception as e:
                print("Error procesando el dictado:", e)
                tray.notify(f"No pude procesar el dictado: {e}", "FlowLite")
                rid = hist.add(seconds, f"No se pudo procesar ({str(e)[:120]})", app_name, "error")
                try:  # se guarda el audio para el botón «Reintentar» del panel
                    os.makedirs(os.path.join(HERE, "pendientes"), exist_ok=True)
                    with open(os.path.join(HERE, "pendientes", f"{rid}.wav"), "wb") as f:
                        f.write(wav_bytes(audio))
                except OSError as err:
                    print("No pude guardar el audio para reintentar:", err)
                bridge.history_changed.emit()
            set_state("idle" if active.is_set() else "paused")

    def toggle_pause():
        active.clear() if active.is_set() else active.set()
        set_state("idle" if active.is_set() else "paused")
        tray.update_menu()

    taps = TapKeys(start_rec, stop_rec, cancel_rec, toggle_pause, active.is_set)
    hk = {}

    def set_hotkey(key):
        key = key if key in HOTKEYS else "ctrl_alt"
        save_state(hotkey=key)
        hk.update(key=key, sets=HOTKEYS[key][1], held=[False] * len(HOTKEYS[key][1]), combo=False)

    set_hotkey(setting("hotkey"))

    def on_key(e):
        name = (e.name or "").lower()
        idx = next((i for i, keys in enumerate(hk["sets"]) if name in keys), None)
        if idx is None:
            if name in SHIFT:
                if hk["combo"] and e.event_type == "down":
                    mode["cmd"] = True  # atajo + Shift = modo comando
                return
            if hk["combo"] and e.event_type == "down":
                print(HOTKEYS[hk["key"]][0], "+", name, "→ atajo de otra app, se descarta")
                taps.abort()
            return
        hk["held"][idx] = e.event_type == "down"
        both = all(hk["held"])
        if both and not hk["combo"]:
            hk["combo"] = True
            taps.down(time.time())
        elif not both and hk["combo"]:
            hk["combo"] = False
            taps.up(time.time())

    def toggle(icon, _):
        toggle_pause()

    def learn_correction(icon, _):
        """Copiás el texto ya corregido y FlowLite aprende las palabras nuevas con mayúscula (nombres, marcas)."""
        before = set(re.findall(r"\w+", last["text"]))
        candidates = [w for w in re.findall(r"\w+", pyperclip.paste())
                      if w not in before and any(c.isupper() for c in w) and len(w) > 1]
        new = learn(candidates)
        icon.notify(f"Aprendí: {', '.join(new)}" if new else "No encontré palabras nuevas.", "FlowLite")

    def ask_word():
        w, ok = QInputDialog.getText(None, "FlowLite", "Palabra o nombre a aprender (tal cual se escribe):")
        if ok and w.strip():
            new = learn([w.strip()])
            tray.notify(f"Aprendí: {w.strip()}" if new else "Ya la conocía.", "FlowLite")

    bridge.quit.connect(app.quit)

    def copy_last(icon, _):
        if last["text"]:
            pyperclip.copy(last["text"])
            icon.notify("Último dictado copiado: pegalo con Ctrl+V.", "FlowLite")

    # ── apuntes de clase ──
    notes = {"run": None, "win": None, "asked": set()}

    def notes_start(suggested, kind="clase"):
        if notes["run"]:
            notes_show()
            return
        if not GROQ_KEY:
            QMessageBox.warning(None, "FlowLite", "Los apuntes de clase necesitan la clave de Groq.")
            return
        dlg = StartDialog(suggested, kind)
        dlg.activateWindow()
        if dlg.exec() != QDialog.Accepted:
            return
        source = dlg.source.currentData()
        save_state(notes_source=source)
        start_class(dlg.title.text().strip(), source, dlg.prefs())

    def start_class(title, source, prefs):
        if notes["run"]:
            return notes_show()
        run = ClassNotes(title, source, bridge.notes_text.emit,
                         bridge.notes_status.emit, bridge.notes_done.emit, prefs=prefs)
        notes["run"] = run
        notes["win"] = ClassWindow(run, run.stop)
        orb.set_class(True)
        tray.update_menu()
        print("Apuntes: empecé a grabar", run.folder)

    def notes_show():
        if notes["win"]:
            notes["win"].show()
            notes["win"].raise_()
            notes["win"].activateWindow()

    def notes_stop():
        if notes["win"] and notes["run"] and not notes["run"].stop_ev.is_set():
            notes_show()
            notes["win"].stop()

    def notes_text(text):
        if notes["win"]:
            notes["win"].add_text(text)

    def notes_status(text):
        if notes["win"]:
            notes["win"].set_status(text)
        if not notes["win"] or not notes["win"].isVisible():
            tray.notify(text, "FlowLite")

    def notes_done(path):
        orb.set_class(False)
        if notes["win"]:
            notes["win"].done(path)
        notes["run"] = None
        tray.update_menu()
        if path:
            tray.notify("Apuntes listos. Los abro en el navegador.", "FlowLite")
            os.startfile(path)

    def notes_redo():
        folder = QFileDialog.getExistingDirectory(None, "Elegí la carpeta de la clase", notes_root())
        if not folder:
            return
        if not os.path.exists(os.path.join(folder, "transcripcion.txt")):
            QMessageBox.warning(None, "FlowLite", "Esa carpeta no tiene transcripcion.txt.")
            return
        tray.notify("Rehaciendo los apuntes… te aviso cuando estén.", "FlowLite")

        def run():
            try:
                path = redo_notes(folder, print)
                tray.notify("Apuntes rehechos. Los abro en el navegador.", "FlowLite")
                os.startfile(path)
            except Exception as e:
                print("No pude rehacer los apuntes:", e)
                tray.notify(f"No pude rehacer los apuntes: {e}", "FlowLite")
        threading.Thread(target=run, daemon=True).start()

    def on_meeting(title, kind=""):
        if notes["run"] or not GROQ_KEY:
            return
        name = meeting_name(title)
        kind = kind or ("reunion" if "teams" in title.lower() else "clase")

        def start_now():
            if not name:  # sin nombre de materia no sabemos qué preferencias usar: mejor preguntar
                return notes_start("", kind)
            prefs = load_state().get("notes_prefs", {}).get(subject_key(name), {"detail": "normal", "extra": ""})
            prefs.setdefault("type", kind)
            start_class(name, load_state().get("notes_source", "pc"), prefs)

        notes["toast"] = MeetingToast(title, "" if generic_title(name) else name, start_now, lambda: notes_start(name, kind),
                                      lambda: save_state(detect_meetings=False), kind=kind)
        notes["toast"].popup()

    def check_unfinished():
        pending = [f for f in unfinished_classes() if f not in notes.setdefault("offered", set())]
        if not pending or notes["run"]:
            return
        folder = pending[0]
        notes["offered"].add(folder)
        name = os.path.basename(folder)
        notes["toast"] = MeetingToast(
            "", name[19:], lambda: redo(folder), lambda: os.startfile(folder), lambda: None, seconds=60,
            icon="🧩", heading="Quedó una clase sin terminar", question="¿Armo los apuntes?",
            body=f"La grabación del {name[:10]} se cortó antes de terminar (se cerró FlowLite o se apagó la PC). "
                 "La transcripción está guardada.", go_text="📝 Armar apuntes", options_text="Ver carpeta", never_text="")
        notes["toast"].popup()

    for sig, fn in ((bridge.notes_start, notes_start), (bridge.notes_show, notes_show),
                    (bridge.notes_stop, notes_stop), (bridge.notes_text, notes_text),
                    (bridge.notes_status, notes_status), (bridge.notes_done, notes_done),
                    (bridge.meeting, on_meeting), (bridge.call, on_meeting)):
        sig.connect(fn)

    def toggle_notes(icon, _):
        if notes["run"]:
            bridge.notes_stop.emit()
        else:
            bridge.notes_start.emit(meeting_name(detect_meeting() or ""))

    def detect_on():
        return setting("detect_meetings")

    def meeting_watcher():
        while True:
            time.sleep(8)
            try:
                if notes["run"] or not detect_on():
                    continue
                title = detect_meeting()
                key = re.sub(r"\s+(y \d+ páginas? más|and \d+ more pages?).*$", "", title or "")
                if title and key not in notes["asked"]:  # una sola vez por reunión, aunque cambien las pestañas
                    notes["asked"].add(key)
                    bridge.meeting.emit(title)
                    continue
                for app, kind in apps_using_mic().items():  # llamadas de WhatsApp, Discord, Telegram… (por el micrófono)
                    if "mic:" + app not in notes["asked"]:
                        notes["asked"].add("mic:" + app)
                        bridge.call.emit(f"Llamada de {app}", kind)
                        break
            except Exception as e:
                print("Detector de reuniones:", e)

    def ask_gemini():
        ask_gemini_key()
        tray.update_menu()


    def open_notes_dir(icon=None, _=None):
        os.startfile(notes_root())

    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    STARTUP_LNK = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup\FlowLite.lnk")

    def autostart_on():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, "FlowLite")
            return True
        except OSError:
            return os.path.exists(STARTUP_LNK)

    def toggle_autostart(icon, _):
        if autostart_on():
            if os.path.exists(STARTUP_LNK):
                os.remove(STARTUP_LNK)
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                    winreg.DeleteValue(k, "FlowLite")
            except OSError:
                pass
        else:
            exe = (f'"{sys.executable}"' if FROZEN else
                   f'"{os.path.join(os.path.dirname(sys.executable), "pythonw.exe")}" "{os.path.abspath(__file__)}"')
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, "FlowLite", 0, winreg.REG_SZ, exe)
        icon.update_menu()

    def class_folders():
        root = notes_root()
        out = []
        for name in sorted(os.listdir(root), reverse=True)[:200]:
            f = os.path.join(root, name)
            if os.path.isdir(f) and not name.startswith("_"):
                out.append((f, name, os.path.exists(os.path.join(f, "Apuntes.html"))))
        return out

    def retry_path(rowid):
        return os.path.join(HERE, "pendientes", f"{rowid}.wav")

    def retry(rowid):
        """Vuelve a transcribir un dictado que falló y lo deja copiado."""
        import wave
        with wave.open(retry_path(rowid)) as w:
            audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32767
        text = groq_transcribe(audio)
        if text and len(text.split()) > 3 and setting("polish"):
            try:
                text = groq_polish(text)
            except Exception as e:
                print("El LLM falló al reintentar:", e)
        text = clean(text)
        if not text:
            raise RuntimeError("no se escuchó nada en ese audio")
        pyperclip.copy(text)
        hist.update(rowid, text, "copiado")
        remove_quiet(retry_path(rowid))
        last["text"] = text
        return text

    def subjects():
        """{materia: [carpetas]} para agrupar las clases como las carpetas de Wispr Flow."""
        out = {}
        for f, name, _ in class_folders():
            title = name[19:] or "Clase"
            out.setdefault(subject_key(title), {"name": re.split(r"\s[-–—:|]\s", title)[0].strip(), "folders": []})
            out[subject_key(title)]["folders"].append(f)
        return out

    def guide_path(subject):
        d = os.path.join(notes_root(), "_Resúmenes")
        if not os.path.isdir(d):
            return None
        hits = sorted(n for n in os.listdir(d) if n.startswith(safe_name(subject) + " - parcial") and n.endswith(".html"))
        return os.path.join(d, hits[-1]) if hits else None

    def redo(folder):
        tray.notify("Rehaciendo los apuntes… te aviso cuando estén.", "FlowLite")

        def run():
            try:
                path = redo_notes(folder, print)
                tray.notify("Apuntes rehechos. Los abro en el navegador.", "FlowLite")
                os.startfile(path)
            except Exception as e:
                print("No pude rehacer los apuntes:", e)
                tray.notify(f"No pude rehacer los apuntes: {e}", "FlowLite")
        threading.Thread(target=run, daemon=True).start()

    def ask_groq():
        global GROQ_KEY
        key, ok = QInputDialog.getText(None, "FlowLite — clave de Groq", "Pegá la clave nueva de Groq (empieza con gsk_):")
        if ok and key.strip():
            if key_ok("groq", key.strip()) is False:
                return QMessageBox.warning(None, "FlowLite", "Esa clave no funciona en Groq. No la guardé.")
            GROQ_KEY = key.strip()
            save_env("GROQ_API_KEY", GROQ_KEY)

    def set_notes_dir(path, copy_old=False):
        """Cambia la carpeta de apuntes; si se pide, copia ahí las clases que ya había (no borra las viejas)."""
        old = CONFIG["notes_dir"]
        os.makedirs(path, exist_ok=True)
        if copy_old and os.path.isdir(old) and os.path.normcase(old) != os.path.normcase(path):
            for name in os.listdir(old):
                src, dst = os.path.join(old, name), os.path.join(path, name)
                if os.path.isdir(src) and not os.path.exists(dst):
                    shutil.copytree(src, dst)
        CONFIG["notes_dir"] = path
        save_state(notes_dir=path)

    def set_setting(key, value):
        save_state(**{key: value})
        if key == "language":
            CONFIG["language"] = value
        elif key == "orb_visible":
            orb.setVisible(value)
        elif key == "orb_size":
            orb.set_scale(value)
        tray.update_menu()

    def set_autostart(on):
        if on != autostart_on():
            toggle_autostart(tray, None)

    def class_elapsed():
        return clock(notes["run"].elapsed()) if notes["run"] else None

    def quick_actions():
        return {"notes": ("⏹ Terminar clase" if notes["run"] else "📝 Tomar apuntes", lambda: toggle_notes(None, None)),
                "copy": ("📋 Copiar último", lambda: copy_last(tray, None)),
                "pause": ("▶ Reanudar" if not active.is_set() else "⏸ Pausar", toggle_pause),
                "folder": ("📂 Apuntes", open_notes_dir),
                "word": ("➕ Palabra", ask_word),
                "class": ("🎓 Ver clase", notes_show),
                "learn": ("🧠 Aprender corrección", lambda: learn_correction(tray, None))}

    ctx = SimpleNamespace(
        hist=hist, version=VERSION, copy_text=pyperclip.copy, is_active=active.is_set, toggle_pause=toggle_pause,
        hotkeys=lambda: HOTKEYS, hotkey_label=lambda: HOTKEYS[hk["key"]][0], set_hotkey=set_hotkey,
        get=setting, set=set_setting, quick_actions=quick_actions, class_elapsed=class_elapsed,
        notes_toggle=lambda: toggle_notes(None, None), open_notes_dir=open_notes_dir, redo=redo,
        redo_pick=notes_redo, class_folders=class_folders, gemini_on=lambda: bool(GEMINI_KEY), ask_gemini=ask_gemini,
        can_retry=lambda rid: os.path.exists(retry_path(rid)), retry=retry, subjects=subjects,
        ask_classes=ask_classes, study_guide=study_guide, guide_path=guide_path,
        quick_notes_path=os.path.join(HERE, "notas_rapidas.txt"),
        notes_dir=lambda: CONFIG["notes_dir"], set_notes_dir=set_notes_dir, drive_dir=google_drive_dir,
        ask_groq=ask_groq, autostart_on=autostart_on, set_autostart=set_autostart,
        open_log=lambda: os.startfile(os.path.join(HERE, "flowlite.log")) if os.path.exists(
            os.path.join(HERE, "flowlite.log")) else None,
        vocab=lambda: list(VOCAB), learn=learn, unlearn=unlearn, snippets=load_snippets, save_snippets=save_snippets)
    panel = Panel(ctx)

    def show_panel():
        panel.toggle_near(orb.mapToGlobal(QPoint(orb.width() // 2, 0)) if orb.isVisible()
                          else QApplication.primaryScreen().availableGeometry().bottomRight())

    def orb_menu(pos):
        from PySide6.QtWidgets import QMenu
        m = QMenu()
        m.setStyleSheet(QSS + "QMenu{background:#1e1b28;border:1px solid #302b40;border-radius:10px;padding:6px;}"
                              "QMenu::item{padding:7px 18px;border-radius:6px;} QMenu::item:selected{background:#312b42;}")
        m.addAction("🗂 Abrir panel", show_panel)
        m.addSeparator()
        for key in setting("quick_buttons"):
            text, fn = quick_actions().get(key, (None, None))
            if text:
                m.addAction(text, fn)
        m.addSeparator()
        m.addAction("⚙️ Ajustes", lambda: (show_panel() if not panel.isVisible() else None, panel.go(panel.SETTINGS)))
        m.exec(pos)

    QTimer.singleShot(8000, check_unfinished)
    orb.clicked.connect(show_panel)
    orb.menu_requested.connect(orb_menu)
    orb.setVisible(setting("orb_visible"))
    bridge.show_panel.connect(show_panel)
    bridge.history_changed.connect(lambda: panel.load_history() if panel.isVisible() and panel.stack.currentIndex() == 0
                                   else None)

    def quit_app(icon, _):
        if notes["run"] and not notes["run"].stop_ev.is_set():
            notes["run"].stop(notes["win"].stamped_notes() if notes["win"] else "")
            icon.notify("Estabas grabando: termino de transcribir y armo los apuntes antes de salir (hasta 2 minutos).",
                        "FlowLite")
            end = time.time() + 120
            while notes["run"] is not None and time.time() < end:  # notes_done lo pone en None al terminar
                time.sleep(0.5)
        keyboard.unhook_all()
        icon.stop()
        bridge.quit.emit()

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill="#29b6f6")
    draw.rounded_rectangle((24, 14, 40, 40), radius=8, fill="white")
    draw.line((32, 40, 32, 50), fill="white", width=4)
    tray = pystray.Icon("FlowLite", img, "FlowLite", pystray.Menu(
        pystray.MenuItem("Abrir panel", lambda icon, _: bridge.show_panel.emit(), default=True),
        pystray.MenuItem("Activo", toggle, checked=lambda _: active.is_set()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(lambda _: "⏹ Terminar clase y armar apuntes" if notes["run"] else "📝 Tomar apuntes de clase o reunión",
                         toggle_notes),
        pystray.MenuItem("Ver la clase en curso", lambda icon, _: bridge.notes_show.emit(),
                         visible=lambda _: notes["run"] is not None),
        pystray.MenuItem("Copiar último dictado", copy_last),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"FlowLite {VERSION}", None, enabled=False),
        pystray.MenuItem("Salir", quit_app),
    ))

    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=meeting_watcher, daemon=True).start()
    keyboard.hook(on_key)
    tray.run_detached()
    print(f"Listo. {HOTKEYS[hk['key']][0]}: mantener = dictar · 2 toques = grabación fija · 3 toques = pausa · "
          "+Shift = modo comando. Tocá la bolita para abrir el panel.")
    app.exec()


if __name__ == "__main__":
    main()
