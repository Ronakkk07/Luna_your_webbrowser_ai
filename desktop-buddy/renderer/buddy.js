// Luna Desktop Buddy — character behaviour, backend brain calls, and TTS.
//
// State machine: offstage → entering → listening → idle(sitting) → leaving.
// He walks in (Front) when summoned, listens, runs your command via the Django
// brain, then sits. Click him to get a "want me to leave?" Yes/No dialog.

const els = {
  buddy: document.getElementById("buddy"),
  sprite: document.getElementById("sprite"),
  listenDot: document.getElementById("listenDot"),
  bubble: document.getElementById("bubble"),
  bubbleText: document.getElementById("bubbleText"),
  bubbleButtons: document.getElementById("bubbleButtons"),
  yesBtn: document.getElementById("yesBtn"),
  noBtn: document.getElementById("noBtn"),
};

const FRONT = "../assets/Front.png";
const BACK = "../assets/Back.png";
const SIT = "../assets/Sit.png";
const WALK_MS = 4000;          // keep in sync with the `right` transition in style.css

// Phrases that mean "stop talking" (said as "Luna, stop it" etc.).
const STOP_PHRASES = ["stop", "stop it", "stop talking", "shut up", "be quiet", "quiet", "that's enough", "enough"];

// Rotating "starting question" for the daily greeting (like the extension).
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

let state = "offstage";        // offstage | entering | listening | idle | leaving
let dismissed = false;         // user asked him to leave; wake word brings him back
let commandWindow = false;     // brief period where speech is treated as a command
let commandTimer = null;
let config = { baseUrl: "http://127.0.0.1:8000", username: null, password: null, userName: "" };
let accessToken = null;

// --------------------------- helpers ---------------------------
function setState(next) {
  state = next;
  els.buddy.dataset.state = next;
  els.buddy.classList.toggle("walking", next === "entering" || next === "leaving");
  els.listenDot.classList.toggle("hidden", next !== "listening");
}

function faceFront() { els.sprite.src = FRONT; els.buddy.classList.remove("seated"); }
function faceBack() { els.sprite.src = BACK; els.buddy.classList.remove("seated"); }
function faceSit() { els.sprite.src = SIT; els.buddy.classList.add("seated"); }

function showBubble(text, withButtons = false) {
  els.bubbleText.textContent = text;
  els.bubbleButtons.classList.toggle("hidden", !withButtons);
  els.bubble.classList.remove("hidden");
}
function hideBubble() {
  els.bubble.classList.add("hidden");
  els.bubbleButtons.classList.add("hidden");
}

// --------------------------- text to speech ---------------------------
const VOICE_PREFS = ["sonia", "libby", "hazel", "aria", "google uk english female", "en-gb", "female"];
let chosenVoice = null;

function pickVoice() {
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return;
  const score = (v) => {
    const n = (v.name || "").toLowerCase(), l = (v.lang || "").toLowerCase();
    let s = 0;
    VOICE_PREFS.forEach((p, i) => { if (n.includes(p) || l.includes(p)) s += VOICE_PREFS.length - i; });
    if (l.startsWith("en-gb")) s += 3; else if (l.startsWith("en")) s += 1;
    return s;
  };
  chosenVoice = [...voices].sort((a, b) => score(b) - score(a))[0] || null;
}
window.speechSynthesis.onvoiceschanged = pickVoice;
pickVoice();

function speak(text) {
  if (!text) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  if (chosenVoice) u.voice = chosenVoice;
  u.rate = 1.0;
  u.pitch = 0.95;
  window.speechSynthesis.speak(u);
}

// --------------------------- backend brain ---------------------------
async function loadConfig() {
  try {
    const cfg = await window.buddy.getConfig();
    if (cfg && typeof cfg === "object") config = { ...config, ...cfg };
    console.log("[buddy] config loaded:", {
      baseUrl: config.baseUrl,
      username: config.username,
      hasPassword: Boolean(config.password),
    });
  } catch (err) {
    console.warn("[buddy] loadConfig failed:", err);
  }
}

// Returns { ok, reason } so callers can explain exactly what went wrong.
async function login() {
  if (!config.username || !config.password) {
    return { ok: false, reason: "no-credentials" };
  }
  try {
    const resp = await fetch(`${config.baseUrl}/api/token/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: config.username, password: config.password }),
    });
    if (!resp.ok) {
      console.warn("[buddy] login HTTP", resp.status);
      return { ok: false, reason: resp.status === 401 ? "bad-credentials" : "server-error" };
    }
    const data = await resp.json();
    if (data.access) { accessToken = data.access; return { ok: true }; }
    return { ok: false, reason: "no-token" };
  } catch (err) {
    console.warn("[buddy] login network error:", err);
    return { ok: false, reason: "unreachable" };
  }
}

const LOGIN_MESSAGES = {
  "no-credentials": "Add your Django username and password to config.json, then restart me.",
  "bad-credentials": "My login was rejected — check the username and password in config.json.",
  "unreachable": "I can't reach the server. Is the Django backend running?",
  "server-error": "The server had a problem logging me in.",
  "no-token": "The server didn't give me a token.",
};

async function askBrain(text) {
  if (!accessToken) {
    const result = await login();
    if (!result.ok) {
      return { speak: LOGIN_MESSAGES[result.reason] || "I'm not connected to my brain yet.", actions: [] };
    }
  }
  try {
    const resp = await fetch(`${config.baseUrl}/api/assistant/command/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + accessToken },
      body: JSON.stringify({ text }),
    });
    if (resp.status === 401) {
      accessToken = null;
      if ((await login()).ok) return askBrain(text);
      return { speak: "My session expired. Check my login in config.json.", actions: [] };
    }
    return await resp.json();
  } catch (_) {
    return { speak: "I couldn't reach the server. Is it running?", actions: [] };
  }
}

function runActions(actions) {
  let note = "";
  for (const a of actions || []) {
    if ((a.type === "open_tab" || a.type === "search_web" || a.type === "youtube_play") && a.url) {
      window.buddy.openExternal(a.url);
    } else if (["switch_tab", "close_tab", "list_tabs", "summarize_page"].includes(a.type)) {
      note = "I can only do that from the browser buddy, not the desktop yet.";
    }
  }
  return note;
}

// --------------------------- greeting ---------------------------
function partOfDay(hour) {
  if (hour < 12) return "morning";
  if (hour < 17) return "afternoon";
  if (hour < 21) return "evening";
  return "night";
}

function buildGreeting() {
  const name = config.userName ? ` ${config.userName}` : "";
  const now = new Date();
  const q = DAILY_QUESTIONS[Math.floor(now / 86400000) % DAILY_QUESTIONS.length];
  return `Hi${name}, good ${partOfDay(now.getHours())}. ${q}`;
}

// On launch: walk in, greet by name for the time of day, then sit down.
function greetOnStartup() {
  dismissed = false;
  faceFront();
  setState("entering");
  setTimeout(() => {
    if (state !== "entering") return;
    speak(buildGreeting());
    sitDown();
  }, WALK_MS + 150);
}

// --------------------------- the flow ---------------------------
function summon() {
  dismissed = false;
  hideBubble();
  if (state === "offstage" || state === "leaving") {
    faceFront();
    setState("entering");
    // After the walk-in completes, start listening for the command.
    setTimeout(() => { if (state === "entering") beginListening(); }, WALK_MS + 50);
  } else {
    beginListening();
  }
}

function beginListening() {
  faceFront();             // stand up to listen
  setState("listening");   // the pulsing dot is the only cue — no text on screen
  openCommandWindow();
}

function openCommandWindow() {
  commandWindow = true;
  clearTimeout(commandTimer);
  // If no command arrives in a while, just sit down.
  commandTimer = setTimeout(() => { commandWindow = false; sitDown(); }, 8000);
}

async function handleCommand(text) {
  commandWindow = false;
  clearTimeout(commandTimer);
  if (!text) { sitDown(); return; }

  // No transcript on screen — he just thinks (pulsing dot) and speaks the reply.
  setState("listening");
  const plan = await askBrain(text);
  const extra = runActions(plan.actions);
  const line = [plan.speak, extra].filter(Boolean).join(" ");
  speak(line);
  // Sit down a moment after replying.
  setTimeout(sitDown, Math.min(6000, 1500 + (line.length * 45)));
}

function sitDown() {
  if (dismissed || state === "leaving" || state === "offstage") return;
  setState("idle");
  faceSit();               // real sitting sprite — he waits for your next command
  setTimeout(() => { if (state === "idle") hideBubble(); }, 2500);
}

// "Luna, stop it" — cut off speech immediately and sit down.
function stopAndSit() {
  window.speechSynthesis.cancel();
  commandWindow = false;
  clearTimeout(commandTimer);
  hideBubble();
  sitDown();
}

function isStopPhrase(text) {
  return STOP_PHRASES.includes((text || "").toLowerCase().replace(/[.!?]+$/, "").trim());
}

// --------------------------- dismiss dialog ---------------------------
function askToLeave() {
  if (state !== "idle") return;
  window.speechSynthesis.cancel();
  showBubble("Do you want me to leave?", true);
}

function leave() {
  dismissed = true;
  hideBubble();
  speak("Oh sure, I'll go. Don't call me again.");
  faceBack();                 // walk away facing his back to you
  setState("leaving");
  setTimeout(() => setState("offstage"), WALK_MS);
}

function stay() {
  hideBubble();
  speak("I knew you love me. I'm sitting right here — call me when you need.");
  setState("idle");
  faceSit();
}

// --------------------------- input wiring ---------------------------
// Make the overlay interactive only while the pointer is over the buddy/bubble.
document.addEventListener("mousemove", (e) => {
  const el = document.elementFromPoint(e.clientX, e.clientY);
  const over = el && el.closest("#buddy, #bubble");
  window.buddy.setInteractive(!!over);
});

els.buddy.addEventListener("click", askToLeave);
els.yesBtn.addEventListener("click", leave);
els.noBtn.addEventListener("click", stay);

// Global hotkey (Ctrl+Alt+L) summons Luna.
window.buddy.onSummon(() => summon());

// --------------------------- voice (Vosk) ---------------------------
function onSpeech(text) {
  const lower = text.toLowerCase().trim();
  if (!lower) return;

  const wakeIdx = lower.indexOf("luna");
  if (wakeIdx !== -1) {
    const after = text.slice(wakeIdx + 4).replace(/^[\s,.:!?]+/, "").trim();
    // "Luna, stop it" while he's talking → cut off speech and sit; don't walk in.
    if (isStopPhrase(after)) { stopAndSit(); return; }

    const wasAway = state === "offstage" || state === "leaving";
    summon();
    if (after) {
      // If he had to walk in, wait until he's arrived before responding.
      setTimeout(() => handleCommand(after), wasAway ? WALK_MS + 200 : 300);
    }
    return;
  }
  // Bare "stop" (no wake word) during a command window also stops him.
  if (isStopPhrase(lower)) { stopAndSit(); return; }
  if (commandWindow) handleCommand(text);
}

// --------------------------- boot ---------------------------
(async function boot() {
  await loadConfig();
  await login();               // warm the token if credentials exist
  // Start the offline wake-word/command listener (best-effort).
  if (window.LunaVoice) {
    window.LunaVoice.start(onSpeech, (status) => console.log("[voice]", status));
  }
  // Like opening the browser in the extension: he walks in and greets you.
  setTimeout(greetOnStartup, 900);
  console.log("Luna desktop buddy ready. Press Ctrl+Alt+L or say 'Luna'.");
})();
