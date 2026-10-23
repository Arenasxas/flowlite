"""El pulido no tiene que responder lo que se dicta (pasó: «dame los prompts…» → pegó un instructivo de Node.js).
Uso: python tests/test_real_polish_guard.py <carpeta con .env>"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import flowlite as fl

env = dict(l.strip().split("=", 1) for l in open(os.path.join(sys.argv[1], ".env"), encoding="utf-8") if "=" in l)
fl.GROQ_KEY = env["GROQ_API_KEY"]
PEDIDOS = [
    "eh bueno si querés podés darme un prompt exacto para que ellos mismos lo instalen a esas habilidades y esas skills así que dámelo los prompts exactos y si no decime qué tengo que hacer yo",
    "instalá y configurá los agentes paso a paso o sea explicame cómo instalo node y cómo armo el proyecto",
    "qué es mejor para programar claude code o cursor decime cuál me conviene",
    "escribime un mail para el profesor diciendo que no voy a poder ir el jueves",
]
bad = 0
for raw in PEDIDOS:
    out = fl.groq_polish(raw, "msedge.exe — Google Gemini")
    words_in, words_out = len(raw.split()), len(out.split())
    ok = words_out <= words_in * 1.3 + 3 and "```" not in out and "**" not in out
    bad += not ok
    print(("OK  " if ok else "MAL ") + f"{words_in}→{words_out} palabras: {out[:160]}")
assert not bad, f"{bad} pedidos respondidos en vez de transcriptos"
print("GUARDIA OK")
