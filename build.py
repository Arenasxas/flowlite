"""Arma FlowLite.zip (lo que se reparte). Con --instalar además lo descomprime en C:\\FlowLite y lo abre.
Uso: .venv\\Scripts\\python build.py [--instalar]
No deja nada en el proyecto: compila en una carpeta temporal y solo queda el zip."""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

import PyInstaller.__main__
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ZIP = os.path.join(os.path.expanduser("~"), "Downloads", "FlowLite.zip")
INSTALL = r"C:\FlowLite"
work = tempfile.mkdtemp(prefix="flowlite-build-")
try:
    icon = os.path.join(work, "flowlite.ico")
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((16, 16, 240, 240), fill="#29b6f6")
    d.rounded_rectangle((96, 56, 160, 160), radius=32, fill="white")
    d.line((128, 160, 128, 200), fill="white", width=16)
    img.save(icon, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])

    PyInstaller.__main__.run([
        os.path.join(HERE, "flowlite.py"), "--name", "FlowLite", "--windowed", "--noconfirm", "--clean", "--log-level", "WARN",
        "--icon", icon, "--collect-data", "soundcard", "--collect-all", "uiautomation", "--hidden-import", "pystray._win32",
        "--exclude-module", "tkinter", "--add-data", os.path.join(HERE, "shared") + os.pathsep + "shared", "--distpath", os.path.join(work, "dist"), "--workpath", os.path.join(work, "build"),
        "--specpath", work,
    ])
    dist = os.path.join(work, "dist", "FlowLite")
    shutil.copy(os.path.join(HERE, "LEEME.txt"), dist)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, _, files in os.walk(dist):
            for f in files:
                path = os.path.join(root, f)
                z.write(path, os.path.join("FlowLite", os.path.relpath(path, dist)))
    print("Listo:", ZIP, f"({os.path.getsize(ZIP) / 1e6:.0f} MB)")

    if "--instalar" in sys.argv:
        subprocess.run(["taskkill", "/F", "/IM", "FlowLite.exe"], capture_output=True)
        time.sleep(1)
        with zipfile.ZipFile(ZIP) as z:  # como lo haría cualquiera: descomprimir encima (la clave y el historial quedan)
            for m in z.infolist():
                rel = m.filename.split("/", 1)[1] if "/" in m.filename else ""
                if rel and not m.is_dir():
                    target = os.path.join(INSTALL, rel)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with z.open(m) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out)
        subprocess.Popen([os.path.join(INSTALL, "FlowLite.exe")], cwd=INSTALL)
        print("Instalado y abierto en", INSTALL)
finally:
    shutil.rmtree(work, ignore_errors=True)
