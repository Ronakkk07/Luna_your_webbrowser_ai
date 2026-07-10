// Offscreen listener — headless, panel-closed.
//
// Flow: Vosk (tiny, offline) watches only for the wake word "Luna". Once heard,
// we RECORD your whole command and stop only when you've actually gone quiet for
// a moment (voice-activity detection) — so it waits for you to finish your
// sentence instead of cutting off at the first pause. Then the recorded audio is
// sent to the background worker, which has Whisper transcribe it accurately.
// The global `Vosk` comes from vendor/vosk.js.

const WAKE_WORDS = ["luna", "hey luna", "ok luna", "okay luna", "loona"];
const WAKE_GRAMMAR = ["luna", "hey luna", "ok luna", "okay luna", "[unk]"];
const MODEL_URL = chrome.runtime.getURL("models/model.tar.gz");

const SILENCE_MS = 1400;      // stop recording after this much quiet (end of sentence)
const MIN_COMMAND_MS = 350;   // ignore blips shorter than this
const MAX_COMMAND_MS = 15000; // hard cap so it can't record forever
const PREROLL_MS = 1600;      // keep this much audio from just before the wake word
const VOICE_RMS = 0.012;      // energy above this counts as speech

let model = null;
let recognizer = null;
let audioContext = null;
let sourceNode = null;
let procNode = null;
let micStream = null;
let running = false;
let starting = false;
let sampleRate = 16000;

// idle rolling pre-roll buffer
let preroll = [];
let prerollSamples = 0;
// active command capture
let capturing = false;
let capChunks = [];
let capSamples = 0;
let lastVoiceMs = 0;

function send(msg) {
  chrome.runtime.sendMessage({ target: "bg", ...msg }).catch(() => {});
}

function isWake(text) {
  const t = (text || "").trim().toLowerCase();
  if (!t) return false;
  return WAKE_WORDS.some((w) => t === w || t.startsWith(w + " ") || t.includes(" " + w));
}

function rms(frame) {
  let sum = 0;
  for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
  return Math.sqrt(sum / frame.length);
}

function startCapture() {
  capturing = true;
  // seed with the rolling pre-roll so the words right after "Luna" aren't lost
  capChunks = preroll.slice();
  capSamples = prerollSamples;
  preroll = [];
  prerollSamples = 0;
  lastVoiceMs = performance.now();
  send({ cmd: "listenStatus", text: "Listening… (I'll wait until you finish)" });
}

function finalizeCapture() {
  capturing = false;
  const merged = new Float32Array(capSamples);
  let off = 0;
  for (const c of capChunks) { merged.set(c, off); off += c.length; }
  capChunks = [];
  capSamples = 0;

  const ms = (merged.length / sampleRate) * 1000;
  if (ms < MIN_COMMAND_MS) { send({ cmd: "wakeOnly" }); return; }
  send({ cmd: "audioCommand", wav: toBase64(encodeWAV(merged, sampleRate)) });
  send({ cmd: "listenStatus", text: "Heard you — transcribing…" });
}

function onFrame(input) {
  const energy = rms(input);
  const now = performance.now();

  if (capturing) {
    capChunks.push(new Float32Array(input));
    capSamples += input.length;
    if (energy > VOICE_RMS) lastVoiceMs = now;
    const capturedMs = (capSamples / sampleRate) * 1000;
    if ((now - lastVoiceMs > SILENCE_MS && capturedMs > MIN_COMMAND_MS) || capturedMs > MAX_COMMAND_MS) {
      finalizeCapture();
    }
  } else {
    // keep a short rolling window so pre-wake audio is available
    preroll.push(new Float32Array(input));
    prerollSamples += input.length;
    const maxPre = (PREROLL_MS / 1000) * sampleRate;
    while (prerollSamples > maxPre && preroll.length > 1) {
      prerollSamples -= preroll[0].length;
      preroll.shift();
    }
  }
}

// ---- WAV encoding ----
function encodeWAV(samples, rate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const w = (off, str) => { for (let i = 0; i < str.length; i++) view.setUint8(off + i, str.charCodeAt(i)); };
  w(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true);
  w(8, "WAVE"); w(12, "fmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  w(36, "data"); view.setUint32(40, samples.length * 2, true);
  let off = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    off += 2;
  }
  return buffer;
}
function toBase64(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
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
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1, sampleRate: 16000 },
    });
    audioContext = new AudioContext({ sampleRate: 16000 });
    sampleRate = audioContext.sampleRate;

    try {
      recognizer = new model.KaldiRecognizer(sampleRate, JSON.stringify(WAKE_GRAMMAR));
    } catch (_) {
      recognizer = new model.KaldiRecognizer(sampleRate);
    }
    // Detect the wake word from partial results too, so capture starts promptly.
    const maybeWake = (text) => { if (!capturing && isWake(text)) startCapture(); };
    recognizer.on("result", (m) => maybeWake(m.result && m.result.text));
    recognizer.on("partialresult", (m) => maybeWake(m.result && m.result.partial));

    procNode = audioContext.createScriptProcessor(4096, 1, 1);
    procNode.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0);
      onFrame(input);
      try { recognizer.acceptWaveform(event.inputBuffer); } catch (_) {}
    };
    sourceNode = audioContext.createMediaStreamSource(micStream);
    sourceNode.connect(procNode);
    procNode.connect(audioContext.destination);

    running = true;
    starting = false;
    send({ cmd: "listenState", listening: true });
    send({ cmd: "listenStatus", text: 'Listening. Say "Luna …".' });
  } catch (err) {
    starting = false;
    running = false;
    send({ cmd: "micError", error: String((err && err.name) || err) });
  }
}

function stop() {
  running = false;
  capturing = false;
  try { if (procNode) procNode.disconnect(); } catch (_) {}
  try { if (sourceNode) sourceNode.disconnect(); } catch (_) {}
  try { if (audioContext) audioContext.close(); } catch (_) {}
  try { if (micStream) micStream.getTracks().forEach((t) => t.stop()); } catch (_) {}
  procNode = sourceNode = audioContext = micStream = recognizer = null;
  preroll = []; prerollSamples = 0; capChunks = []; capSamples = 0;
  send({ cmd: "listenState", listening: false });
}

chrome.runtime.onMessage.addListener((message) => {
  if (!message || message.target !== "off") return;
  if (message.cmd === "startContinuous") start();
  else if (message.cmd === "stopContinuous") stop();
});

send({ cmd: "ready" });
