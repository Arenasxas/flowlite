// Configuración de FlowLite en el celular. El ID de cliente de Google es público por diseño (no es una clave):
// se crea en Google Cloud siguiendo docs/GUIA.md y se pega acá.
window.FLOWLITE_CONFIG = {
  version: "2.2.3",
  groq: "https://api.groq.com/openai/v1",
  gemini: "https://generativelanguage.googleapis.com/v1beta/models",
  drive: "https://www.googleapis.com",
  googleClientId: "",
  androidApk: "https://github.com/Arenasxas/flowlite/releases/latest",
  iphoneGuide: "https://github.com/Arenasxas/flowlite/blob/main/docs/iphone-atajo.md",
};
// ?mock=1: pruebas automáticas contra el servidor simulado (tests/mock_server.mjs), sin claves reales.
if (new URLSearchParams(location.search).get("mock") === "1") {
  Object.assign(window.FLOWLITE_CONFIG, {
    groq: location.origin + "/mock/groq", gemini: location.origin + "/mock/gemini",
    drive: location.origin + "/mock/drive", mock: true,
  });
}
