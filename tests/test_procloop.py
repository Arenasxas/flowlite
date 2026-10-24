"""Captura por programa (procloop): mide el volumen de «solo la música», «todo menos la música» y «todo».
Necesita un reproductor sonando (ej.: Spotify). No graba ni guarda audio. Uso: python tests/test_procloop.py"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ctypes
import numpy as np
import procloop

ctypes.windll.ole32.CoInitializeEx(None, 0)
app = procloop.music_app()
print("reproductor:", app)
assert procloop.music_app([(10, 1, "explorer.exe"), (20, 10, "spotify.exe"), (21, 20, "spotify.exe")]) == (20, "Spotify")
assert procloop.music_app([(10, 1, "msedge.exe")]) is None


def measure(pid, exclude, sec=4):
    cap = procloop.ProcessLoopback(pid, exclude)
    got, end = [], time.time() + sec
    while time.time() < end:
        got.append(cap.read())
    cap.close()
    a = np.concatenate(got)
    return len(a) / procloop.RATE, float(np.sqrt(np.mean(a ** 2))) if a.size else 0.0


if app:
    pid = app[0]
    for label, excl in (("solo la música", False), ("todo menos la música", True)):
        dur, rms = measure(pid, excl)
        print(f"{label}: {dur:.1f} s de audio, volumen {rms:.4f}")
    import soundcard as sc
    with sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True).recorder(samplerate=16000, channels=1) as r:
        a = r.record(numframes=16000 * 4).reshape(-1)
    print(f"todo junto (como antes): volumen {float(np.sqrt(np.mean(a ** 2))):.4f}")
print("PROCLOOP OK")
