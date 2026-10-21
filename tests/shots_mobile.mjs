// Capturas de la app del celular con Chrome sin ventana (tamaño de celular, densidad 2x), esperando a que cargue.
// Uso: node tests/shots_mobile.mjs <carpeta salida> [url base]   (con tests/mock_server.mjs corriendo)
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const OUT = process.argv[2];
const BASE = process.argv[3] || "http://localhost:8765/?mock=1&seed=1";
const CHROME = ["C:/Program Files/Google/Chrome/Application/chrome.exe", "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"];
const SHOTS = [["1_grabar", "&tab=grabar"], ["2_clases", "&tab=clases"], ["3_visor", "&tab=clases&open=1"],
  ["4_repasar", "&tab=repasar&show=1"], ["5_dictar", "&tab=dictar"], ["6_ajustes", "&tab=ajustes"]];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const profile = mkdtempSync(join(tmpdir(), "fl-shots-"));
const port = 9333;
const chrome = spawn(CHROME[0], ["--headless=new", "--disable-gpu", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "about:blank"], { stdio: "ignore" });
let ws, id = 0;
const pending = new Map();
const send = (method, params = {}) => new Promise((ok) => { const n = ++id; pending.set(n, ok); ws.send(JSON.stringify({ id: n, method, params })); });

try {
  let target;
  for (let i = 0; i < 40 && !target; i++) {
    await sleep(250);
    try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page"); } catch { /* arrancando */ }
  }
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } };
  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  await send("Page.enable");
  for (const [name, q] of SHOTS) {
    // cada captura con datos limpios: borrar lo guardado en el sitio
    await send("Storage.clearDataForOrigin", { origin: new URL(BASE).origin, storageTypes: "all" });
    await send("Page.navigate", { url: BASE + q });
    await sleep(3500);
    const { data } = await send("Page.captureScreenshot", { format: "png" });
    writeFileSync(join(OUT, name + ".png"), Buffer.from(data, "base64"));
    console.log("captura", name);
  }
} finally {
  if (ws) ws.close();
  chrome.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* lo libera después */ }
}
