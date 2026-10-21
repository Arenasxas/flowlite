import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import flowlite as fl

h = fl.md_to_html("![Diapo](../2026-10-17 23.53 - Costos/capturas/00120.jpg)\n"
                  "![x](../../a/capturas/00001.jpg)\n![y](capturas/00002.jpg)")
assert 'src="../2026-10-17 23.53 - Costos/capturas/00120.jpg"' in h, h
assert "../../a" not in h.split("<p>")[0], h  # no se puede salir más de una carpeta
assert 'src="capturas/00002.jpg"' in h, h
print("RUTAS OK")
