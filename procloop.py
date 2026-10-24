"""Audio de la PC SIN un programa (ej.: Spotify): la captura por proceso de Windows (10 2004 o más nuevo).
Así la música que escuchás durante la clase no entra en la grabación.

ProcessLoopback(pid, exclude=True).read() devuelve bloques float32 mono a 16 kHz, como soundcard.
"""
import ctypes
import os
from ctypes import POINTER, Structure, byref, c_byte, c_int, c_long, c_longlong, c_uint32, c_uint64, c_ulong, c_ushort, \
    c_void_p, c_wchar_p, wintypes

import numpy as np
from comtypes import COMMETHOD, COMObject, GUID, HRESULT, IUnknown

# reproductores de música: lo que suena ahí no es la clase
MUSIC_APPS = ("spotify.exe", "applemusic.exe", "itunes.exe", "deezer.exe", "tidal.exe", "amazon music.exe",
              "foobar2000.exe", "vlc.exe", "aimp.exe", "musicbee.exe", "winamp.exe", "wmplayer.exe",
              "microsoft.media.player.exe", "youtube music.exe")


class WAVEFORMATEX(Structure):
    _fields_ = [("wFormatTag", c_ushort), ("nChannels", c_ushort), ("nSamplesPerSec", c_ulong),
                ("nAvgBytesPerSec", c_ulong), ("nBlockAlign", c_ushort), ("wBitsPerSample", c_ushort), ("cbSize", c_ushort)]


class IAudioCaptureClient(IUnknown):
    _iid_ = GUID("{C8ADBD64-E71E-48A0-A4DE-185C395CD317}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetBuffer", (["out"], POINTER(POINTER(c_byte)), "data"), (["out"], POINTER(c_uint32), "frames"),
                  (["out"], POINTER(c_uint32), "flags"), (["out"], POINTER(c_uint64), "pos"), (["out"], POINTER(c_uint64), "qpc")),
        COMMETHOD([], HRESULT, "ReleaseBuffer", (["in"], c_uint32, "frames")),
        COMMETHOD([], HRESULT, "GetNextPacketSize", (["out"], POINTER(c_uint32), "frames")),
    ]


class IAudioClient(IUnknown):
    _iid_ = GUID("{1CB9AD4C-DBFA-4C32-B178-C2F568A703B2}")
    _methods_ = [
        COMMETHOD([], HRESULT, "Initialize", (["in"], c_int, "mode"), (["in"], c_ulong, "flags"), (["in"], c_longlong, "buf"),
                  (["in"], c_longlong, "period"), (["in"], POINTER(WAVEFORMATEX), "fmt"), (["in"], POINTER(GUID), "session")),
        COMMETHOD([], HRESULT, "GetBufferSize", (["out"], POINTER(c_uint32), "n")),
        COMMETHOD([], HRESULT, "GetStreamLatency", (["out"], POINTER(c_longlong), "l")),
        COMMETHOD([], HRESULT, "GetCurrentPadding", (["out"], POINTER(c_uint32), "n")),
        COMMETHOD([], HRESULT, "IsFormatSupported", (["in"], c_int, "mode"), (["in"], POINTER(WAVEFORMATEX), "fmt"),
                  (["out"], POINTER(POINTER(WAVEFORMATEX)), "closest")),
        COMMETHOD([], HRESULT, "GetMixFormat", (["out"], POINTER(POINTER(WAVEFORMATEX)), "fmt")),
        COMMETHOD([], HRESULT, "GetDevicePeriod", (["out"], POINTER(c_longlong), "d"), (["out"], POINTER(c_longlong), "m")),
        COMMETHOD([], HRESULT, "Start"),
        COMMETHOD([], HRESULT, "Stop"),
        COMMETHOD([], HRESULT, "Reset"),
        COMMETHOD([], HRESULT, "SetEventHandle", (["in"], c_void_p, "h")),
        COMMETHOD([], HRESULT, "GetService", (["in"], POINTER(GUID), "riid"), (["out"], POINTER(c_void_p), "ppv")),
    ]


class IActivateAudioInterfaceAsyncOperation(IUnknown):
    _iid_ = GUID("{72A22D78-CDE4-431D-B8CC-843A71199B6D}")
    _methods_ = [COMMETHOD([], HRESULT, "GetActivateResult", (["out"], POINTER(c_long), "hr"),
                           (["out"], POINTER(POINTER(IUnknown)), "iface"))]


class IActivateAudioInterfaceCompletionHandler(IUnknown):
    _iid_ = GUID("{41D949AB-9862-444A-80F6-C261334DA5EB}")
    _methods_ = [COMMETHOD([], HRESULT, "ActivateCompleted", (["in"], POINTER(IActivateAudioInterfaceAsyncOperation), "op"))]


class IAgileObject(IUnknown):  # sin métodos: le dice a COM que el aviso se puede llamar desde cualquier hilo
    _iid_ = GUID("{94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90}")
    _methods_ = []


class _Done(COMObject):
    _com_interfaces_ = [IActivateAudioInterfaceCompletionHandler, IAgileObject]

    def __init__(self):
        super().__init__()
        self.event = kernel32.CreateEventW(None, True, False, None)

    def ActivateCompleted(self, op):
        kernel32.SetEvent(self.event)
        return 0


class PROPVARIANT(Structure):  # solo el caso VT_BLOB
    _fields_ = [("vt", c_ushort), ("r1", c_ushort), ("r2", c_ushort), ("r3", c_ushort), ("cbSize", c_ulong), ("pBlobData", c_void_p)]


class ACTIVATION_PARAMS(Structure):
    _fields_ = [("ActivationType", c_int), ("TargetProcessId", wintypes.DWORD), ("ProcessLoopbackMode", c_int)]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateEventW.restype = c_void_p
kernel32.CreateEventW.argtypes = [c_void_p, wintypes.BOOL, wintypes.BOOL, c_wchar_p]
kernel32.SetEvent.argtypes = [c_void_p]
kernel32.WaitForSingleObject.argtypes = [c_void_p, wintypes.DWORD]
kernel32.CloseHandle.argtypes = [c_void_p]

RATE = 16000


class ProcessLoopback:
    """Graba lo que suena en la PC incluyendo solo un programa (y sus hijos) o todo menos ese programa."""

    def __init__(self, pid, exclude=True):
        params = ACTIVATION_PARAMS(1, pid, 1 if exclude else 0)  # PROCESS_LOOPBACK; EXCLUDE/INCLUDE_TARGET_PROCESS_TREE
        pv = PROPVARIANT(65, 0, 0, 0, ctypes.sizeof(params), ctypes.cast(byref(params), c_void_p))  # VT_BLOB
        done = _Done()
        op = POINTER(IActivateAudioInterfaceAsyncOperation)()
        fn = ctypes.WinDLL("Mmdevapi").ActivateAudioInterfaceAsync
        fn.restype = HRESULT
        fn.argtypes = [c_wchar_p, POINTER(GUID), POINTER(PROPVARIANT), POINTER(IActivateAudioInterfaceCompletionHandler),
                       POINTER(POINTER(IActivateAudioInterfaceAsyncOperation))]
        fn("VAD\\Process_Loopback", byref(IAudioClient._iid_), byref(pv),
           done.QueryInterface(IActivateAudioInterfaceCompletionHandler), byref(op))
        if kernel32.WaitForSingleObject(done.event, 5000) != 0:
            raise RuntimeError("Windows no respondió a la captura por programa")
        kernel32.CloseHandle(done.event)
        hr, unk = op.GetActivateResult()
        if hr < 0:
            raise OSError(hr, "la captura por programa no está disponible")
        self.client = unk.QueryInterface(IAudioClient)
        fmt = WAVEFORMATEX(1, 1, RATE, RATE * 2, 2, 16, 0)  # PCM 16 bits mono 16 kHz (Windows convierte)
        # LOOPBACK | EVENTCALLBACK | AUTOCONVERTPCM | SRC_DEFAULT_QUALITY
        self.client.Initialize(0, 0x00020000 | 0x00040000 | 0x80000000 | 0x08000000, 2_000_000, 0, byref(fmt), None)
        self.event = kernel32.CreateEventW(None, False, False, None)
        self.client.SetEventHandle(self.event)
        raw = self.client.GetService(byref(IAudioCaptureClient._iid_))
        self.capture = ctypes.cast(c_void_p(raw), POINTER(IAudioCaptureClient))
        self.client.Start()

    def read(self, timeout_ms=200):
        """Lo que llegó desde la última vez (float32 mono 16 kHz). Con silencio total, Windows no manda nada."""
        kernel32.WaitForSingleObject(self.event, timeout_ms)
        out = []
        while self.capture.GetNextPacketSize():
            data, frames, flags, _, _ = self.capture.GetBuffer()
            if frames:
                if flags & 0x2:  # AUDCLNT_BUFFERFLAGS_SILENT
                    out.append(np.zeros(frames, np.float32))
                else:
                    buf = ctypes.string_at(data, frames * 2)
                    out.append(np.frombuffer(buf, np.int16).astype(np.float32) / 32768)
            self.capture.ReleaseBuffer(frames)
        return np.concatenate(out) if out else np.zeros(0, np.float32)

    def close(self):
        try:
            self.client.Stop()
        finally:
            kernel32.CloseHandle(self.event)


def processes():
    """[(pid, pid del padre, nombre.exe)] de todo lo que corre."""
    class ENTRY(Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", c_void_p), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]
    kernel32.CreateToolhelp32Snapshot.restype = c_void_p
    snap = kernel32.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
    e, out = ENTRY(), []
    e.dwSize = ctypes.sizeof(ENTRY)
    ok = kernel32.Process32FirstW(c_void_p(snap), byref(e))
    while ok:
        out.append((e.th32ProcessID, e.th32ParentProcessID, e.szExeFile.lower()))
        ok = kernel32.Process32NextW(c_void_p(snap), byref(e))
    kernel32.CloseHandle(snap)
    return out


def music_app(procs=None):
    """(pid raíz, nombre) del primer reproductor de música abierto, o None. Raíz = el que no es hijo de otro igual."""
    procs = procs if procs is not None else processes()
    by_pid = {p: (pp, n) for p, pp, n in procs}
    for app in MUSIC_APPS:
        for pid, ppid, name in procs:
            if name == app and by_pid.get(ppid, (0, ""))[1] != app:
                return pid, os.path.splitext(name)[0].title().replace("Applemusic", "Apple Music")
    return None
