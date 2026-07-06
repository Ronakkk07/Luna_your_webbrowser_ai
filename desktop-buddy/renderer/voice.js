// Offline wake-word + command listening via Vosk (WebAssembly), running right in
// the Electron renderer. Unlike the browser extension, Electron's renderer allows
// the stock Vosk build (blob worker + WASM), so no patching is needed here.

window.LunaVoice = (function () {
  let model = null;
  let recognizer = null;
  let audioContext = null;
  let node = null;
  let source = null;
  let stream = null;
  let running = false;

  async function start(onText, onStatus) {
    if (running) return;
    running = true;
    const status = (s) => onStatus && onStatus(s);

    if (typeof Vosk === "undefined") {
      running = false;
      return status("vosk-not-loaded");
    }

    try {
      status("loading-model");
      model = await Vosk.createModel("../models/model.tar.gz");

      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          channelCount: 1,
          sampleRate: 16000,
        },
      });

      audioContext = new AudioContext({ sampleRate: 16000 });
      recognizer = new model.KaldiRecognizer(audioContext.sampleRate);
      recognizer.on("result", (message) => {
        const text = message && message.result && message.result.text;
        if (text) onText(text);
      });

      node = audioContext.createScriptProcessor(4096, 1, 1);
      node.onaudioprocess = (event) => {
        try {
          recognizer.acceptWaveform(event.inputBuffer);
        } catch (_) { /* ignore transient buffer errors */ }
      };
      source = audioContext.createMediaStreamSource(stream);
      source.connect(node);
      node.connect(audioContext.destination); // required for onaudioprocess to fire

      status("listening");
    } catch (err) {
      running = false;
      console.error("Vosk voice failed:", err);
      status("error: " + (err && err.message ? err.message : err));
    }
  }

  function stop() {
    running = false;
    try { node && node.disconnect(); } catch (_) {}
    try { source && source.disconnect(); } catch (_) {}
    try { audioContext && audioContext.close(); } catch (_) {}
    try { stream && stream.getTracks().forEach((t) => t.stop()); } catch (_) {}
    node = source = audioContext = stream = recognizer = null;
  }

  return { start, stop };
})();
