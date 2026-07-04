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
  options.headers = { ...(options.headers || {}), Authorization: "Bearer " + access };

  let resp = await fetch(`${baseUrl}${path}`, options);
  if (resp.status !== 401) return resp;

  if (!refresh) return resp;
  const refreshResp = await fetch(`${baseUrl}/api/token/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });
  const data = await refreshResp.json().catch(() => ({}));
  if (!data.access) return resp;

  await chrome.storage.local.set({ jwtAccess: data.access });
  options.headers.Authorization = "Bearer " + data.access;
  return fetch(`${baseUrl}${path}`, options);
}

// ------------------------------------------------------------------ commands
async function runCommand(text, { fromVoice = false } = {}) {
  const clean = (text || "").trim();
  if (!clean) return;

  // Barge-in: a fresh voice command cuts off whatever Luna is saying.
  if (fromVoice) stopSpeaking();

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

// Open a YouTube search and best-effort click the first video to auto-play it.
async function actYoutubePlay(a) {
  const tab = await chrome.tabs.create({ url: a.url });
  const clickFirst = () => {
    let tries = 0;
    const timer = setInterval(() => {
      const link = document.querySelector(
        "ytd-video-renderer a#video-title, a#video-title-link, ytd-video-renderer a#thumbnail"
      );
      if (link) {
        clearInterval(timer);
        link.click();
      } else if (++tries > 40) {
        clearInterval(timer);
      }
    }, 250);
  };
  const listener = (tabId, info) => {
    if (tabId === tab.id && info.status === "complete") {
      chrome.tabs.onUpdated.removeListener(listener);
      chrome.scripting
        .executeScript({ target: { tabId: tab.id }, func: clickFirst })
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

const HANDLERS = {
  open_tab: actOpenTab,
  search_web: actSearchWeb,
  youtube_play: actYoutubePlay,
  switch_tab: actSwitchTab,
  close_tab: actCloseTab,
  list_tabs: actListTabs,
  summarize_page: actSummarizePage,
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
