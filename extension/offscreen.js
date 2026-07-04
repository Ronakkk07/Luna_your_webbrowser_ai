// Offscreen listener — headless, on-device speech recognition via Vosk (WASM).
// Runs with the side panel closed. Captures the mic, transcribes locally, and
// forwards only the text of "Luna …" commands to the background worker.
// The global `Vosk` comes from vendor/vosk.js.

const WAKE_WORDS = ["luna", "hey luna", "ok luna", "okay luna", "loona", "lunar"];
const MODEL_URL = chrome.runtime.getURL("models/model.tar.gz");

let model = null;
let recognizer = null;
let audioContext = null;
let sourceNode = null;
let procNode = null;
let micStream = null;
let running = false;
let starting = false;

function send(msg) {
  chrome.runtime.sendMessage({ target: "bg", ...msg }).catch(() => {});
}

function stripWakeWord(text) {
  const t = (text || "").trim().toLowerCase();
  for (const w of WAKE_WORDS) {
    if (t === w) return "";
    if (t.startsWith(w + " ")) {
      return text.trim().slice(w.length).replace(/^[\s,.:!?]+/, "").trim();
    }
  }
  return null; // no wake word present
}

function handleText(text) {
  const command = stripWakeWord(text);
  if (command === null) return;
  if (command === "") { send({ cmd: "wakeOnly" }); return; }
  send({ cmd: "voiceCommand", text: command });
}

async function start() {
  if (running || starting) return;
  starting = true;
  try {
    if (!model) {
      send({ cmd: "listenStatus", text: "Loading speech model…" });
      model = await Vosk.createModel(MODEL_URL);
    }

    micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        channelCount: 1,
        sampleRate: 16000,
      },
    });

    audioContext = new AudioContext({ sampleRate: 16000 });
    recognizer = new model.KaldiRecognizer(audioContext.sampleRate);
    recognizer.on("result", (m) => handleText(m.result && m.result.text));

    procNode = audioContext.createScriptProcessor(4096, 1, 1);
    procNode.onaudioprocess = (event) => {
      try {
        recognizer.acceptWaveform(event.inputBuffer);
      } catch (_) {
        /* ignore transient decode errors */
      }
    };
    sourceNode = audioContext.createMediaStreamSource(micStream);
    sourceNode.connect(procNode);
    // Connect to destination so onaudioprocess fires; we never write output,
    // so nothing is played back (no echo).
    procNode.connect(audioContext.destination);

    running = true;
    starting = false;
    send({ cmd: "listenState", listening: true });
    send({ cmd: "listenStatus", text: 'Listening (offline). Say "Luna …".' });
  } catch (err) {
    starting = false;
    running = false;
    send({ cmd: "micError", error: String((err && err.name) || err) });
  }
}

function stop() {
  running = false;
  try { if (procNode) procNode.disconnect(); } catch (_) {}
  try { if (sourceNode) sourceNode.disconnect(); } catch (_) {}
  try { if (audioContext) audioContext.close(); } catch (_) {}
  try { if (micStream) micStream.getTracks().forEach((t) => t.stop()); } catch (_) {}
  procNode = sourceNode = audioContext = micStream = recognizer = null;
  send({ cmd: "listenState", listening: false });
}

chrome.runtime.onMessage.addListener((message) => {
  if (!message || message.target !== "off") return;
  if (message.cmd === "startContinuous") start();
  else if (message.cmd === "stopContinuous") stop();
});

send({ cmd: "ready" });
