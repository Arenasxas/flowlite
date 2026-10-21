// Grabación de clases y llamadas en el celular, en tramos de ~60 s que se transcriben mientras sigue la clase.
// Fuentes: micrófono (todos los celulares) o "audio del celular" (solo la app de Android: videos, clases grabadas).
// Límite del sistema: ni Android ni iPhone dejan grabar el audio de una llamada (Meet, Zoom, WhatsApp) en el mismo celular.
import { transcribeSegments } from "./ai.js";

const CHUNK_MS = (+new URLSearchParams(location.search).get("chunk") || 60) * 1000; // ?chunk=10 en pruebas
const SILENCE_RMS = 0.003;

function pickMime() {
  for (const t of ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/aac"]) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(t)) return t;
  }
  return "";
}

export class ClassRecorder {
  /** onSegments(segs) se llama con cada tramo transcripto; onStatus(texto); onSaved() para guardar avance. */
  constructor({ source = "mic", prompt = () => "", avoid = new Set(), onSegments, onStatus, fakeAudioUrl = null }) {
    Object.assign(this, { source, prompt, avoid, onSegments, onStatus, fakeAudioUrl });
    this.offset = 0;           // segundos de audio ya enviados
    this.chunkStart = 0;       // momento (ms) en que empezó el tramo actual, sin contar pausas
    this.pausedAt = null;
    this.pending = [];         // tramos que fallaron (sin internet): se reintentan al final
    this.queue = Promise.resolve();
    this.levels = [];
    this.stopped = false;
  }

  elapsed() {
    if (!this.chunkStart) return this.offset;
    const now = this.pausedAt || Date.now();
    return this.offset + (now - this.chunkStart) / 1000;
  }

  async start() {
    if (this.source === "device") return this.startDevice();
    if (this.fakeAudioUrl) {
      // pruebas automáticas: un audio en lugar del micrófono
      const ctx = new AudioContext();
      const el = new Audio(this.fakeAudioUrl);
      el.crossOrigin = "anonymous";
      const src = ctx.createMediaElementSource(el);
      const dest = ctx.createMediaStreamDestination();
      src.connect(dest);
      await el.play();
      this.fakeEl = el;
      this.stream = dest.stream;
      this.ctx = ctx;
    } else {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: true } });
      this.ctx = new AudioContext();
    }
    const an = this.ctx.createAnalyser();
    an.fftSize = 2048;
    this.ctx.createMediaStreamSource(this.stream).connect(an);
    const buf = new Float32Array(an.fftSize);
    this.meter = setInterval(() => {
      an.getFloatTimeDomainData(buf);
      this.levels.push(Math.sqrt(buf.reduce((a, x) => a + x * x, 0) / buf.length));
    }, 250);
    this.mime = pickMime();
    this.newChunk();
    this.noData = setTimeout(() => {
      if (!this.gotData) this.onStatus("El celular no está entregando audio. En iPhone, abrí FlowLite en Safari (no desde el ícono) y probá de nuevo.");
    }, 12000);
    await this.wake();
    document.addEventListener("visibilitychange", this.onVisible = () => { if (document.visibilityState === "visible") this.wake(); });
  }

  newChunk() {
    this.chunkStart = Date.now();
    this.levels = [];
    const rec = new MediaRecorder(this.stream, this.mime ? { mimeType: this.mime } : {});
    const parts = [];
    rec.ondataavailable = (e) => { if (e.data && e.data.size) { parts.push(e.data); this.gotData = true; } };
    rec.onstop = () => {
      const dur = ((this.pausedAt || Date.now()) - this.chunkStart) / 1000;
      const start = this.offset;
      this.offset += dur;
      const levels = this.levels;
      const rms = levels.length ? levels.reduce((a, x) => a + x, 0) / levels.length : 1;
      const blob = new Blob(parts, { type: rec.mimeType || this.mime || "audio/webm" });
      if (!this.stopped) this.newChunk();
      this.enqueue(blob, start, rms);
    };
    rec.start(1000);
    this.rec = rec;
    this.timer = setTimeout(() => { if (rec.state !== "inactive") rec.stop(); }, CHUNK_MS);
  }

  enqueue(blob, start, rms = 1) {
    if (rms < SILENCE_RMS || blob.size < 2000) return; // silencio: no gasta cupo ni deja que Whisper invente
    this.queue = this.queue.then(async () => {
      try {
        const segs = await transcribeSegments(blob, start, this.prompt(), this.avoid);
        if (segs.length) this.onSegments(segs);
      } catch (e) {
        this.pending.push({ blob, start });
        this.onStatus(`Sin conexión en ${Math.floor(start / 60)}:${String(Math.floor(start % 60)).padStart(2, "0")}: lo reintento al final.`);
      }
    });
  }

  pause(on) {
    if (this.source === "device") return;
    if (on && this.rec.state === "recording") {
      this.rec.pause();
      this.pausedAt = Date.now();
      clearTimeout(this.timer); // en pausa el tramo no corre
    } else if (!on && this.rec.state === "paused") {
      this.chunkStart += Date.now() - this.pausedAt; // el tiempo en pausa no cuenta
      this.pausedAt = null;
      this.rec.resume();
      const rec = this.rec;
      this.timer = setTimeout(() => { if (rec.state !== "inactive") rec.stop(); },
        Math.max(1000, CHUNK_MS - (Date.now() - this.chunkStart)));
    }
  }

  /** Termina: corta el último tramo, espera las transcripciones y reintenta las que fallaron. */
  async stop() {
    this.stopped = true;
    clearTimeout(this.timer);
    clearTimeout(this.noData);
    clearInterval(this.meter);
    document.removeEventListener("visibilitychange", this.onVisible);
    if (this.source === "device") {
      window.FlowLiteAndroid.stopDeviceAudio();
      await new Promise((r) => setTimeout(r, 1500));
    } else if (this.rec && this.rec.state !== "inactive") {
      await new Promise((r) => { this.rec.addEventListener("stop", () => setTimeout(r, 50), { once: true }); this.rec.stop(); });
    }
    await this.queue;
    for (const p of this.pending.splice(0)) {
      try {
        const segs = await transcribeSegments(p.blob, p.start, this.prompt(), this.avoid);
        if (segs.length) this.onSegments(segs);
      } catch (e) { this.pending.push(p); }
    }
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    if (this.fakeEl) this.fakeEl.pause();
    if (this.ctx) this.ctx.close();
    if (this.lock) this.lock.release().catch(() => {});
    return this.pending.length; // tramos que no se pudieron transcribir
  }

  async wake() {
    try { if ("wakeLock" in navigator) this.lock = await navigator.wakeLock.request("screen"); } catch { /* sin permiso */ }
  }

  // ── Android: audio del celular (videos, YouTube, clases grabadas) ──
  startDevice() {
    const bridge = window.FlowLiteAndroid;
    if (!bridge || !bridge.isAvailable()) throw new Error("Grabar el audio del celular necesita la app FlowLite de Android.");
    window.flowliteOnDeviceChunk = (b64, start) => {
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const dur = Math.max(0, (bytes.length - 44) / 32000);
      this.offset = Math.max(this.offset, start + dur);
      this.chunkStart = Date.now();
      this.enqueue(new Blob([bytes], { type: "audio/wav" }), start);
    };
    window.flowliteOnDeviceStatus = (text) => this.onStatus(text);
    this.chunkStart = Date.now();
    bridge.startDeviceAudio();
    return this.wake();
  }
}

/** Dictado corto: mantener el botón, hablar, soltar. Devuelve el audio. */
export class QuickRecorder {
  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.parts = [];
    this.rec = new MediaRecorder(this.stream, pickMime() ? { mimeType: pickMime() } : {});
    this.rec.ondataavailable = (e) => e.data.size && this.parts.push(e.data);
    this.rec.start();
  }

  stop() {
    return new Promise((ok) => {
      this.rec.onstop = () => {
        this.stream.getTracks().forEach((t) => t.stop());
        ok(new Blob(this.parts, { type: this.rec.mimeType || "audio/webm" }));
      };
      this.rec.stop();
    });
  }
}
