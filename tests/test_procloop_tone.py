"""Captura por programa con un tono propio casi inaudible (7 kHz, volumen 0,002) sonando desde otro proceso:
incluir ese proceso lo tiene que traer, excluirlo lo tiene que sacar. Uso: python tests/test_procloop_tone.py"""
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ctypes
import numpy as np
import procloop

PLAYER = ("import numpy as np, sounddevice as sd\n"
          "t = np.arange(48000 * 12) / 48000\n"
          "sd.play((0.002 * np.sin(2 * np.pi * 7000 * t)).astype('float32'), 48000, blocking=True)\n")
ctypes.windll.ole32.CoInitializeEx(None, 0)
player = subprocess.Popen([sys.executable, "-c", PLAYER])
time.sleep(2.5)


def tone(pid, exclude, sec=3):
    cap = procloop.ProcessLoopback(pid, exclude)
    got, end = [], time.time() + sec
    while time.time() < end:
        got.append(cap.read())
    cap.close()
    a = np.concatenate(got)
    spec = np.abs(np.fft.rfft(a * np.hanning(len(a))))
    f = np.fft.rfftfreq(len(a), 1 / procloop.RATE)
    peak = spec[(f > 6950) & (f < 7050)].max()
    floor = np.median(spec[(f > 6000) & (f < 7800)]) + 1e-9
    return peak / floor


try:
    inc = tone(player.pid, False)
    exc = tone(player.pid, True)
finally:
    player.kill()
print(f"tono con el programa incluido: {inc:.0f}× el ruido · excluido: {exc:.1f}×")
assert inc > 20 and exc < inc / 100, (inc, exc)
print("TONO OK")
