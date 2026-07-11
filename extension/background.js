// Luna background service worker — the central controller.
//
// Owns: auth + backend calls, action execution, speaking (chrome.tts), and the
// daily startup greeting. These all run headless (no page needed). Microphone
// LISTENING lives in the side panel (sidepanel.js), because Chrome's Web Speech
// API can't run reliably without a visible page/offscreen context.

const DEFAULT_BASE_URL = "http://127.0.0.1:8000";

// ------------------------------------------------------------------ storage
async function store(get) {
  return chrome.storage.local.get(get);
}
async function getBaseUrl() {
  const { baseUrl } = await store("baseUrl");
  return (baseUrl || DEFAULT_BASE_URL).replace(/\/$/, "");
}
async function getTokens() {
  const { jwtAccess, jwtRefresh } = await store(["jwtAccess", "jwtRefresh"]);
  return { access: jwtAccess || null, refresh: jwtRefresh || null };
}

// ------------------------------------------------------------------ panel bus
function toPanel(evt) {
  chrome.runtime.sendMessage({ target: "panel", ...evt }).catch(() => {});
}
function log(who, text) {
  if (text) toPanel({ evt: "log", who, text });
}
function status(text) {
  toPanel({ evt: "status", text });
}

// ------------------------------------------------------------------ offscreen listener
async function ensureOffscreen() {
  if (await chrome.offscreen.hasDocument()) return;
  await chrome.offscreen.createDocument({
    url: "offscreen.html",
    reasons: ["USER_MEDIA"],
    justification: "On-device voice-command listening (Vosk) with the panel closed.",
  });
}
async function toOffscreen(cmd) {
  await ensureOffscreen();
  chrome.runtime.sendMessage({ target: "off", cmd }).catch(() => {});
}
async function startListening() {
  await chrome.storage.local.set({ listening: true });
  await toOffscreen("startContinuous");
}
async function stopListening() {
  await chrome.storage.local.set({ listening: false });
  chrome.runtime.sendMessage({ target: "off", cmd: "stopContinuous" }).catch(() => {});
}

// ------------------------------------------------------------------ speaking
// A FRIDAY-ish default: prefer a British female voice, otherwise any en-GB.
const VOICE_PREFERENCES = [
  "sonia", "libby", "hazel", "aria", "emma", "google uk english female",
  "en-gb", "female",
];

async function pickDefaultVoiceName() {
  return new Promise((resolve) => {
    try {
      chrome.tts.getVoices((voices) => {
        if (!voices || !voices.length) return resolve(null);
        const score = (v) => {
          const name = (v.voiceName || "").toLowerCase();
          const lang = (v.lang || "").toLowerCase();
          let s = 0;
          VOICE_PREFERENCES.forEach((pref, i) => {
            if (name.includes(pref) || lang.includes(pref)) s += VOICE_PREFERENCES.length - i;
          });
          if (lang.startsWith("en-gb")) s += 3;
          if (lang.startsWith("en")) s += 1;
          if (v.remote) s += 2; // network "natural" voices sound better
          return s;
        };
        const best = [...voices].sort((a, b) => score(b) - score(a))[0];
        resolve(best ? best.voiceName : null);
      });
    } catch (_) {
      resolve(null);
    }
  });
}

async function getVoiceSettings() {
  const cfg = await store(["voiceName", "voiceRate", "voicePitch"]);
  let voiceName = cfg.voiceName;
  if (!voiceName) {
    voiceName = await pickDefaultVoiceName();
    if (voiceName) await chrome.storage.local.set({ voiceName });
  }
  return {
    voiceName: voiceName || undefined,
    rate: typeof cfg.voiceRate === "number" ? cfg.voiceRate : 1.0,
    pitch: typeof cfg.voicePitch === "number" ? cfg.voicePitch : 0.9,
  };
}

async function speak(text, { interrupt = true } = {}) {
  if (!text) return;
  if (interrupt) chrome.tts.stop();
  const v = await getVoiceSettings();
  toPanel({ evt: "speaking", on: true });
  chrome.tts.speak(text, {
    voiceName: v.voiceName,
    rate: v.rate,
    pitch: v.pitch,
    enqueue: false,
    onEvent: (e) => {
      if (["end", "interrupted", "cancelled", "error"].includes(e.type)) {
        toPanel({ evt: "speaking", on: false });
      }
    },
  });
}

function stopSpeaking() {
  chrome.tts.stop();
  toPanel({ evt: "speaking", on: false });
}

// ------------------------------------------------------------------ auth fetch
async function authFetch(path, options = {}) {
  const baseUrl = await getBaseUrl();
  let { access, refresh } = await getTokens();
  options.headers = {
    "ngrok-skip-browser-warning": "true", // skip ngrok free interstitial
    ...(options.headers || {}),
    Authorization: "Bearer " + access,
  };

  let resp = await fetch(`${baseUrl}${path}`, options);
  if (resp.status !== 401) return resp;

  if (!refresh) return resp;
  const refreshResp = await fetch(`${baseUrl}/api/token/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "true" },
    body: JSON.stringify({ refresh }),
  });
  const data = await refreshResp.json().catch(() => ({}));
  if (!data.access) return resp;

  await chrome.storage.local.set({ jwtAccess: data.access });
  options.headers.Authorization = "Bearer " + data.access;
  return fetch(`${baseUrl}${path}`, options);
}

// ------------------------------------------------------------------ commands
const STOP_PHRASES = [
  "stop", "stop it", "stop talking", "shut up", "be quiet", "quiet",
  "that's enough", "thats enough", "enough", "stop please", "please stop", "cancel",
];
function isStopPhrase(text) {
  return STOP_PHRASES.includes((text || "").toLowerCase().replace(/[.!?]+$/, "").trim());
}

// Wake-word audio (from the offscreen listener) → Whisper transcript → command.
const WAKE_PREFIXES = ["hey luna", "ok luna", "okay luna", "luna"];
function stripWakeFront(text) {
  const t = (text || "").trim();
  const low = t.toLowerCase();
  for (const w of WAKE_PREFIXES) {
    if (low.startsWith(w)) return t.slice(w.length).replace(/^[\s,.:!?]+/, "").trim();
  }
  return t;
}

async function transcribeAndRun(base64Wav) {
  const { access } = await getTokens();
  if (!access) { status("Please log in first."); return; }
  status("Transcribing…");
  try {
    const bytes = Uint8Array.from(atob(base64Wav), (c) => c.charCodeAt(0));
    const form = new FormData();
    form.append("audio_file", new Blob([bytes], { type: "audio/wav" }), "command.wav");
    const resp = await authFetch("/api/assistant/transcribe/", { method: "POST", body: form });
    if (resp.status === 401) { status("Session expired. Please log in again."); return; }
    const data = await resp.json();
    const text = stripWakeFront(data.transcript || "");
    if (!text) { status('Say "Luna" then your command.'); speak("Yes?"); return; }
    await runCommand(text, { fromVoice: true });
  } catch (err) {
    console.error("transcribe failed:", err);
    status("I couldn't transcribe that.");
  }
}

async function runCommand(text, { fromVoice = false } = {}) {
  const clean = (text || "").trim();
  if (!clean) return;

  // Barge-in: a fresh voice command cuts off whatever Luna is saying.
  if (fromVoice) stopSpeaking();

  // "Luna, stop it" — just go quiet. Don't call the brain or say anything new.
  if (isStopPhrase(clean)) {
    stopSpeaking();
    status("Okay — stopped.");
    return;
  }

  const { access } = await getTokens();
  if (!access) {
    status("Please log in first.");
    return;
  }

  log("user", clean);
  status("Thinking…");

  let data;
  try {
    const resp = await authFetch("/api/assistant/command/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: clean }),
    });
    if (resp.status === 401) {
      status("Session expired. Please log in again.");
      return;
    }
    data = await resp.json();
  } catch (_) {
    log("luna", "I couldn't reach the server.");
    speak("I couldn't reach the server.");
    status("Ready.");
    return;
  }

  const speech = data.speak || "";
  if (speech) log("luna", speech);

  let extra = "";
  if (Array.isArray(data.actions) && data.actions.length) {
    extra = await executeActions(data.actions);
    if (extra) log("luna", extra);
  }

  speak([speech, extra].filter(Boolean).join(". "));
  status("Ready.");
}

// ------------------------------------------------------------------ greeting
const DAILY_QUESTIONS = [
  "What's the plan for today?",
  "What are we working on first?",
  "Anything you'd like me to remind you about today?",
  "What's the most important thing on your list today?",
  "How can I help you get started?",
  "What would you like to tackle this morning?",
  "Any meetings or tasks I should keep track of?",
  "What's one thing you want to finish today?",
  "Shall I catch you up on the news?",
  "Where should we begin today?",
  "What's on your mind?",
  "Ready when you are — what's first?",
  "Anything I can line up for you today?",
  "What are your top priorities today?",
];

function partOfDay(hour) {
  if (hour < 12) return "morning";
  if (hour < 17) return "afternoon";
  if (hour < 21) return "evening";
  return "night";
}

async function greet() {
  const { access, refresh } = await getTokens();
  if (!access && !refresh) return; // not logged in, stay quiet
  const { displayName } = await store("displayName");
  const now = new Date();
  const name = displayName ? ` ${displayName}` : "";
  const dayIndex = Math.floor(now / 86400000) % DAILY_QUESTIONS.length;
  const greeting = `Hi${name}, good ${partOfDay(now.getHours())}. ${DAILY_QUESTIONS[dayIndex]}`;
  log("luna", greeting);
  speak(greeting);
}

// ------------------------------------------------------------------ actions
async function actOpenTab(a) {
  await chrome.tabs.create({ url: a.url });
  return null;
}
async function actSearchWeb(a) {
  try {
    await chrome.search.query({ text: a.query, disposition: "NEW_TAB" });
  } catch (_) {
    if (a.url) await chrome.tabs.create({ url: a.url });
  }
  return null;
}

// Open YouTube and make it actually PLAY: on a /watch page press play; on a
// search page click the first result (which SPA-navigates to a watch page, then
// the same script keeps polling and presses play there).
async function actYoutubePlay(a) {
  const tab = await chrome.tabs.create({ url: a.url });

  const ensurePlay = () => {
    let tries = 0;
    let clickedResult = false;
    const timer = setInterval(() => {
      tries++;
      const video = document.querySelector("video");
      if (video && video.readyState > 0) {
        if (video.paused) {
          const p = video.play();
          if (p && p.catch) {
            p.catch(() => {
              const btn = document.querySelector(".ytp-large-play-button, .ytp-play-button");
              if (btn) btn.click();
            });
          }
        }
        if (!video.paused) { clearInterval(timer); return; }
      } else if (!clickedResult) {
        const link = document.querySelector(
          "ytd-video-renderer a#video-title, a#video-title-link, a#video-title, ytd-video-renderer a#thumbnail"
        );
        if (link) { clickedResult = true; link.click(); }
      }
      if (tries > 60) clearInterval(timer); // give up after ~15s
    }, 250);
  };

  const listener = (tabId, info) => {
    if (tabId === tab.id && info.status === "complete") {
      chrome.tabs.onUpdated.removeListener(listener);
      chrome.scripting
        .executeScript({ target: { tabId: tab.id }, func: ensurePlay })
        .catch(() => {});
    }
  };
  chrome.tabs.onUpdated.addListener(listener);
  return null;
}

function tabMatches(tab, hint) {
  const n = (hint || "").toLowerCase();
  return (
    (tab.title || "").toLowerCase().includes(n) ||
    (tab.url || "").toLowerCase().includes(n)
  );
}
async function actSwitchTab(a) {
  const tabs = await chrome.tabs.query({});
  const match = tabs.find((t) => tabMatches(t, a.hint));
  if (!match) return `I couldn't find a tab matching "${a.hint}".`;
  await chrome.tabs.update(match.id, { active: true });
  await chrome.windows.update(match.windowId, { focused: true });
  return null;
}
async function actCloseTab(a) {
  if (a.hint) {
    const tabs = await chrome.tabs.query({});
    const match = tabs.find((t) => tabMatches(t, a.hint));
    if (!match) return `I couldn't find a tab matching "${a.hint}".`;
    await chrome.tabs.remove(match.id);
    return null;
  }
  const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (active) await chrome.tabs.remove(active.id);
  return null;
}
async function actListTabs() {
  const tabs = await chrome.tabs.query({ currentWindow: true });
  if (!tabs.length) return "You don't have any tabs open.";
  const titles = tabs.map((t) => t.title || t.url).slice(0, 12);
  return `You have ${tabs.length} tabs open: ${titles.join(", ")}.`;
}
async function actSummarizePage() {
  const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!active || !active.id) return "I couldn't find an active tab to read.";
  let extracted;
  try {
    const [{ result } = {}] = await chrome.scripting.executeScript({
      target: { tabId: active.id },
      func: () => ({ title: document.title, text: (document.body && document.body.innerText) || "" }),
    });
    extracted = result;
  } catch (_) {
    return "I can't read this page (it may be a protected browser page).";
  }
  if (!extracted || !extracted.text.trim()) return "There's no readable text on this page.";
  try {
    const resp = await authFetch("/api/assistant/summarize-page/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: extracted.title, text: extracted.text }),
    });
    if (resp.status === 401) return "Your session expired. Please log in again.";
    const data = await resp.json();
    return data.speak || "I couldn't summarize this page.";
  } catch (_) {
    return "I couldn't reach the server to summarize this page.";
  }
}

// --- page Q&A: read a tab's text and let the backend answer a question about it ---
async function readTabText(tabId) {
  const [{ result } = {}] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => ({ title: document.title, text: (document.body && document.body.innerText) || "" }),
  });
  return result || { title: "", text: "" };
}

async function answerFromPage(question, text, title) {
  try {
    const resp = await authFetch("/api/assistant/answer-page/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, text, title }),
    });
    if (resp.status === 401) return "Your session expired. Please log in again.";
    const data = await resp.json();
    return data.speak || "I couldn't find that on the page.";
  } catch (_) {
    return "I couldn't reach the server to read that page.";
  }
}

// "What does this page say / tell me the odds on this page" → read the active tab.
async function actReadPage(a) {
  const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!active || !active.id) return "I don't see a page to read.";
  let page;
  try {
    page = await readTabText(active.id);
  } catch (_) {
    return "I can't read this page (it may be a protected browser page).";
  }
  if (!page.text.trim()) return "There's no readable text on this page.";
  return answerFromPage(a.question, page.text, page.title);
}

// "Open polymarket and tell me the odds for X" → open, wait, read, answer.
async function actOpenAndAnswer(a) {
  const tab = await chrome.tabs.create({ url: a.url });
  await new Promise((resolve) => {
    let done = false;
    const finish = () => { if (!done) { done = true; chrome.tabs.onUpdated.removeListener(listener); resolve(); } };
    const listener = (id, info) => { if (id === tab.id && info.status === "complete") finish(); };
    chrome.tabs.onUpdated.addListener(listener);
    setTimeout(finish, 9000); // don't wait forever
  });
  await new Promise((r) => setTimeout(r, 2500)); // let SPA content render
  let page;
  try {
    page = await readTabText(tab.id);
  } catch (_) {
    return "I opened it, but couldn't read the page.";
  }
  if (!page.text.trim()) return "I opened it, but there was no readable text yet.";
  return answerFromPage(a.question, page.text, page.title);
}

const HANDLERS = {
  open_tab: actOpenTab,
  search_web: actSearchWeb,
  youtube_play: actYoutubePlay,
  switch_tab: actSwitchTab,
  close_tab: actCloseTab,
  list_tabs: actListTabs,
  summarize_page: actSummarizePage,
  read_page: actReadPage,
  open_and_answer: actOpenAndAnswer,
};

async function executeActions(actions) {
  const extra = [];
  for (const action of actions || []) {
    const handler = HANDLERS[action.type];
    if (!handler) continue;
    try {
      const spoken = await handler(action);
      if (spoken) extra.push(spoken);
    } catch (err) {
      console.error("Action failed:", action, err);
    }
  }
  return extra.join(" ");
}

// ------------------------------------------------------------------ lifecycle
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
});

// On browser start: resume headless listening if it was on, then greet.
chrome.runtime.onStartup.addListener(async () => {
  const { listening } = await store("listening");
  if (listening) await startListening();
  setTimeout(() => greet(), 1500);
});

// ------------------------------------------------------------------ messages
// Everything addressed to the worker carries target: "bg" (from the side panel
// and from the offscreen listener).
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.target !== "bg") return;

  (async () => {
    switch (message.cmd) {
      // ---- from the offscreen listener ----
      case "voiceCommand":
        await runCommand(message.text, { fromVoice: true });
        break;
      case "audioCommand":
        await transcribeAndRun(message.wav);
        break;
      case "wakeOnly":
        stopSpeaking();
        status("Yes? Say your command.");
        speak("Yes?");
        break;
      case "listenState":
        toPanel({ evt: "listening", on: message.listening });
        break;
      case "listenStatus":
        status(message.text);
        break;
      case "micError":
        status("Microphone is blocked — open the panel to enable it.");
        toPanel({ evt: "micError" });
        break;
      case "ready":
        break;

      // ---- from the side panel ----
      case "runCommand":
        await runCommand(message.text, { fromVoice: message.fromVoice });
        sendResponse({ ok: true });
        break;
      case "setListening":
        if (message.on) await startListening();
        else await stopListening();
        sendResponse({ ok: true });
        break;
      case "stopSpeaking":
        stopSpeaking();
        sendResponse({ ok: true });
        break;
      case "speak":
        speak(message.text);
        sendResponse({ ok: true });
        break;
      case "greet":
        await greet();
        sendResponse({ ok: true });
        break;
      case "getState": {
        const { access } = await getTokens();
        const { listening } = await store("listening");
        sendResponse({ loggedIn: Boolean(access), listening: Boolean(listening) });
        break;
      }
      default:
        if (sendResponse) sendResponse({ ok: false });
    }
  })();

  return true; // async sendResponse
});
