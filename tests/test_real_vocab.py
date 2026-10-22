"""Vocabulario de IA y tecnología con Groq real: cuántos términos salen bien sin y con la lista incorporada.
Uso: python tests/test_real_vocab.py <carpeta con .env> <carpeta con f0.wav… y frases.txt>"""
import os, re, sys, wave
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import flowlite as fl

env = dict(l.strip().split("=", 1) for l in open(os.path.join(sys.argv[1], ".env"), encoding="utf-8") if "=" in l)
fl.GROQ_KEY = env["GROQ_API_KEY"]
d = sys.argv[2]
frases = open(os.path.join(d, "frases.txt"), encoding="utf-8").read().splitlines()
TERMS = ["MCP", "Claude Code", "skill", "API", "Gemini", "n8n", "ChatGPT", "deploy", "Vercel", "RAG", "Supabase", "tokens",
         "prompt", "LLM", "Copilot", "Cursor", "DeepSeek", "Claude", "Grok"]


def load(name):
    with wave.open(os.path.join(d, name)) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32767
        rate = w.getframerate()
    return np.interp(np.arange(0, len(a), rate / fl.SR), np.arange(len(a)), a).astype(np.float32)  # a 16 kHz


def run(label):
    hits = total = 0
    for i, f in enumerate(frases):
        raw = fl.groq_transcribe(load(f"f{i}.wav"))
        out = fl.clean(fl.groq_polish(raw, "Notion"))
        want = [t for t in TERMS if re.search(rf"\b{re.escape(t)}\b", f)]
        got = [t for t in want if re.search(rf"\b{re.escape(t)}\b", out)]
        hits += len(got); total += len(want)
        print(f"  [{label}] {out}\n      falta: {sorted(set(want) - set(got)) or '—'}")
    print(f"{label}: {hits}/{total} términos bien")
    return hits, total


tech, tech_w = fl.PROMPTS["tech_vocab"], fl.PROMPTS["tech_fixes"]
fl.PROMPTS["tech_vocab"], fl.PROMPTS["tech_fixes"] = [], []
fixes, fl.TECH_FIXES = fl.TECH_FIXES, []
antes = run("sin lista")
fl.PROMPTS["tech_vocab"], fl.PROMPTS["tech_fixes"] = tech, tech_w
fl.TECH_FIXES = fixes
despues = run("con lista")
assert despues[0] > antes[0], "la lista no mejoró"
print("eco de la ayuda descartado:", fl.prompt_echo("ChatGPT, OpenAI, Claude, Gemini."), "· frase real no:", fl.prompt_echo("Abrí Claude y pedile el resumen"))
print("VOCAB OK")
