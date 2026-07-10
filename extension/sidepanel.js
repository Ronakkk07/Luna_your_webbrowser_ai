// Luna side panel — login, settings, and conversation display.
// "Always listen" drives the headless offscreen Vosk listener (works with the
// panel closed). The mic button is a manual one-shot via Web Speech (panel open).
// Speaking, commands, actions and greeting all run in the background worker.

const DEFAULT_BASE_URL = "http://127.0.0.1:8000";
const WAKE_WORDS = ["luna", "hey luna", "ok luna", "okay luna"];
const $ = (id) => document.getElementById(id);

const els = {
  orb: $("orb"),
  settingsToggle: $("settingsToggle"),
  settings: $("settings"),
  baseUrl: $("baseUrl"),
  userName: $("userName"),
  voiceSelect: $("voiceSelect"),
  voiceRate: $("voiceRate"),
  voicePitch: $("voicePitch"),
  rateVal: $("rateVal"),
  pitchVal: $("pitchVal"),
  testVoice: $("testVoice"),
  saveSettings: $("saveSettings"),
  loginPanel: $("loginPanel"),
  username: $("username"),
  password: $("password"),
  loginBtn: $("loginBtn"),
  loginStatus: $("loginStatus"),
  assistantPanel: $("assistantPanel"),
  micBtn: $("micBtn"),
  status: $("status"),
  wakeToggle: $("wakeToggle"),
  stopBtn: $("stopBtn"),
  log: $("log"),
  logoutBtn: $("logoutBtn"),
};

let baseUrl = DEFAULT_BASE_URL;

// --------------------------- background bus ---------------------------
function toBg(cmd, extra = {}) {
  return chrome.runtime.sendMessage({ target: "bg", cmd, ...extra });
}

// --------------------------- UI helpers ---------------------------
function setStatus(text) { els.status.textContent = text; }
function showLoggedIn(loggedIn) {
  els.loginPanel.classList.toggle("hidden", loggedIn);
  els.assistantPanel.classList.toggle("hidden", !loggedIn);
}
function addBubble(text, who) {
  const div = document.createElement("div");
  div.className = `bubble ${who}`;
  div.textContent = text;
  els.log.appendChild(div);
  els.log.scrollTop = els.log.scrollHeight;
}

// --------------------------- settings / voices ---------------------------
function loadVoices() {
  try {
    chrome.tts.getVoices((voices) => {
      els.voiceSelect.innerHTML = "";
      (voices || [])
        .sort((a, b) => (a.lang || "").localeCompare(b.lang || ""))
        .forEach((v) => {
          const opt = document.createElement("option");
          opt.value = v.voiceName;
          opt.textContent = `${v.voiceName} (${v.lang || "?"})`;
          els.voiceSelect.appendChild(opt);
        });
      chrome.storage.local.get("voiceName", ({ voiceName }) => {
        if (voiceName) els.voiceSelect.value = voiceName;
      });
    });
  } catch (_) {}
}

async function loadSettings() {
  const cfg = await chrome.storage.local.get(["baseUrl", "voiceRate", "voicePitch", "displayName"]);
  baseUrl = cfg.baseUrl || DEFAULT_BASE_URL;
  els.baseUrl.value = baseUrl;
  els.userName.value = cfg.displayName || "";
  els.voiceRate.value = typeof cfg.voiceRate === "number" ? cfg.voiceRate : 1.0;
  els.voicePitch.value = typeof cfg.voicePitch === "number" ? cfg.voicePitch : 0.9;
  els.rateVal.textContent = els.voiceRate.value;
  els.pitchVal.textContent = els.voicePitch.value;
  loadVoices();
}

// --------------------------- microphone permission ---------------------------
async function ensureMicPermission() {
  try {
    const status = await navigator.permissions.query({ name: "microphone" });
    if (status.state === "granted") return true;
  } catch (_) {}
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((t) => t.stop());
    return true;
  } catch (_) {
    chrome.tabs.create({ url: chrome.runtime.getURL("permission.html") });
    setStatus("Grant microphone access in the new tab, then come back.");
    return false;
  }
}

// --------------------------- manual one-shot (Web Speech) ---------------------------
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

function stripWakeWord(text) {
  const t = text.trim().toLowerCase();
  for (const w of WAKE_WORDS) {
    if (t.startsWith(w)) {
      return text.trim().slice(w.length).replace(/^[\s,.:!?]+/, "").trim();
    }
  }
  return null;
}

// Tap to start, tap again to stop — so you can speak a full sentence (with
// pauses) and it won't cut you off mid-thought.
let dictation = null;
let dictationText = "";
function toggleMic() {
  if (!Recognition) { setStatus("Manual mic needs Chrome/Edge; use Always listen instead."); return; }
  if (dictation) { try { dictation.stop(); } catch (_) {} return; } // second tap → finish

  dictation = new Recognition();
  dictation.lang = "en-US";
  dictation.continuous = true;       // keep going through pauses
  dictation.interimResults = true;
  dictationText = "";

  els.micBtn.classList.add("recording");
  els.orb.classList.add("listening");
  setStatus("Listening… tap the mic again when you're done.");

  dictation.onresult = (event) => {
    let finalText = "";
    for (let i = 0; i < event.results.length; i++) {
      if (event.results[i].isFinal) finalText += event.results[i][0].transcript + " ";
    }
    if (finalText.trim()) dictationText = finalText.trim();
  };
  dictation.onerror = () => {};
  dictation.onend = () => {
    els.micBtn.classList.remove("recording");
    els.orb.classList.remove("listening");
    const stripped = stripWakeWord(dictationText);
    const text = (stripped !== null ? stripped : dictationText).trim();
    dictation = null;
    if (text) toBg("runCommand", { text, fromVoice: true });
    else setStatus("I didn't catch that. Try again.");
  };
  try { dictation.start(); } catch (_) { dictation = null; }
}

// --------------------------- login ---------------------------
async function login() {
  const username = els.username.value.trim();
  const password = els.password.value;
  if (!username || !password) { els.loginStatus.textContent = "Enter username and password."; return; }
  els.loginStatus.textContent = "Logging in…";
  try {
    const resp = await fetch(`${baseUrl}/api/token/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await resp.json();
    if (data.access && data.refresh) {
      // Don't derive the greeting name from the login username (that's the
      // assistant's account, not you). The name comes from ⚙ Settings → Your name.
      await chrome.storage.local.set({ jwtAccess: data.access, jwtRefresh: data.refresh });
      els.loginStatus.textContent = "";
      els.password.value = "";
      showLoggedIn(true);
      setStatus("Ready. Turn on Always listen, or tap the mic.");
      await ensureMicPermission();
      toBg("greet");
    } else {
      els.loginStatus.textContent = "Login failed. Check your credentials.";
    }
  } catch (_) {
    els.loginStatus.textContent = "Could not reach the server.";
  }
}

// --------------------------- events from background ---------------------------
chrome.runtime.onMessage.addListener((message) => {
  if (!message || message.target !== "panel") return;
  switch (message.evt) {
    case "log":
      addBubble(message.text, message.who === "user" ? "user" : "luna");
      break;
    case "status":
      setStatus(message.text);
      break;
    case "speaking":
      els.orb.classList.toggle("speaking", Boolean(message.on));
      break;
    case "listening":
      els.orb.classList.toggle("listening", Boolean(message.on));
      els.wakeToggle.checked = Boolean(message.on);
      break;
    case "micError":
      els.wakeToggle.checked = false;
      ensureMicPermission();
      break;
  }
});

// --------------------------- wiring ---------------------------
els.settingsToggle.onclick = () => els.settings.classList.toggle("hidden");
els.voiceRate.oninput = () => (els.rateVal.textContent = els.voiceRate.value);
els.voicePitch.oninput = () => (els.pitchVal.textContent = els.voicePitch.value);

async function persistVoice() {
  await chrome.storage.local.set({
    voiceName: els.voiceSelect.value || undefined,
    voiceRate: parseFloat(els.voiceRate.value),
    voicePitch: parseFloat(els.voicePitch.value),
  });
}

els.saveSettings.onclick = async () => {
  baseUrl = (els.baseUrl.value.trim() || DEFAULT_BASE_URL).replace(/\/$/, "");
  const name = els.userName.value.trim();
  await chrome.storage.local.set({ baseUrl, userSetName: Boolean(name) });
  if (name) await chrome.storage.local.set({ displayName: name });
  else await chrome.storage.local.remove("displayName");
  await persistVoice();
  els.settings.classList.add("hidden");
  setStatus("Settings saved.");
  if (name) toBg("greet"); // re-greet so you hear the corrected name immediately
};

els.testVoice.onclick = async () => {
  await persistVoice();
  toBg("speak", { text: "Hi, I'm Luna. How can I help you today?" });
};

els.loginBtn.onclick = login;
els.password.addEventListener("keydown", (e) => { if (e.key === "Enter") login(); });

els.micBtn.onclick = async () => {
  if (dictation) { toggleMic(); return; }        // second tap stops (no perm re-check)
  if (await ensureMicPermission()) toggleMic();
};

// Always listen -> headless offscreen Vosk daemon.
els.wakeToggle.onchange = async () => {
  if (els.wakeToggle.checked) {
    if (await ensureMicPermission()) {
      setStatus("Starting listener…");
      toBg("setListening", { on: true });
    } else {
      els.wakeToggle.checked = false;
    }
  } else {
    toBg("setListening", { on: false });
    setStatus("Always listen off.");
  }
};

els.stopBtn.onclick = () => toBg("stopSpeaking");

els.logoutBtn.onclick = async () => {
  toBg("setListening", { on: false });
  els.wakeToggle.checked = false;
  await chrome.storage.local.remove(["jwtAccess", "jwtRefresh", "displayName"]);
  showLoggedIn(false);
};

// --------------------------- init ---------------------------
(async function init() {
  await loadSettings();
  try {
    const state = await toBg("getState");
    const loggedIn = Boolean(state && state.loggedIn);
    showLoggedIn(loggedIn);
    if (loggedIn) {
      els.wakeToggle.checked = Boolean(state && state.listening);
      setStatus(
        state && state.listening
          ? 'Listening for "Luna" (offline)…'
          : "Ready. Turn on Always listen, or tap the mic."
      );
    }
  } catch (_) {}
})();
