# Luna Browser Assistant (Chrome / Edge extension)

An Alexa/FRIDAY-style voice assistant that lives in your browser. Talk to it
hands-free to set reminders, hear the news and the time, control your tabs
(open, search, switch, close, list), play things on YouTube, and summarize the
current page.

**Design in one line:** the extension is the **ears + hands + voice**; the Django
backend (`luna_backend`) is the **brain** that turns your speech into an *action
plan* the extension executes.

> For the full story of how this was built — every architecture decision, the
> challenges we hit, and why each fix was chosen — see
> [`../docs/ENGINEERING_JOURNEY.md`](../docs/ENGINEERING_JOURNEY.md).

---

## Architecture at a glance

```
  ┌─────────────────────────── Chrome / Edge extension ───────────────────────────┐
  │                                                                                │
  │   Side panel (UI)          Background service worker         Offscreen doc     │
  │   • login / settings  ───▶  • auth + calls backend    ◀────  • Vosk WASM STT   │
  │   • conversation log       • runs action plan (tabs)         • mic capture     │
  │   • manual mic (Web        • speaks via chrome.tts           • wake-word gate   │
  │     Speech one-shot)       • daily greeting (onStartup)      (works panel-closed)│
  │                                    │                                           │
  └────────────────────────────────────┼──────────────────────────────────────────┘
                                        │ JSON over HTTPS (JWT)
                                        ▼
                        ┌───────────────────────────────┐
                        │  Django backend  (the brain)   │
                        │  POST /api/assistant/command/  │
                        │  text ─▶ Gemini intent ─▶      │
                        │  router ─▶ { speak, actions }  │
                        │  + reminders / shopping / news │
                        └───────────────────────────────┘
```

---

## Prerequisites

1. Run the backend:
   ```bash
   python manage.py migrate
   python manage.py runserver            # http://127.0.0.1:8000
   ```
   (Optional, for scheduled reminders: run Redis + `celery -A luna_backend worker -l info`.)
2. Create a login:
   ```bash
   python manage.py createsuperuser
   ```
3. Fetch the offline speech assets (one-time, ~46 MB, git-ignored):
   ```bash
   python scripts/build_vosk_vendor.py
   ```
   This downloads + patches the Vosk WASM engine into `extension/vendor/` and the
   model into `extension/models/`. (See the journey doc for *why* it needs patching.)

## Load the extension

1. Open `chrome://extensions` (or `edge://extensions`) and enable **Developer mode**.
2. **Load unpacked** → select this `extension/` folder.
3. Click the Luna toolbar icon to open the side panel.
4. (⚙ Settings) confirm the Server URL is `http://127.0.0.1:8000`, then **Log in**.
5. **Microphone:** the first time you use voice, Luna opens a small permission tab
   (a Chrome side panel can't show the mic prompt itself). Click **Enable
   microphone → Allow**, close that tab, and come back.

> After changing extension files, prefer **Remove + Load unpacked** over the reload
> ↻ button. A plain reload may leave the previous **offscreen document running old
> code** (see Troubleshooting).

## Using it

- **Tap the mic** for a single command, or tick **“Always listen (offline) for
  Luna”** and just say `Luna, …` any time — even with the side panel closed.
- Try: *"open YouTube"*, *"open youtube and play lofi beats"*, *"search for weather
  in London"*, *"what time is it"*, *"give me the news"*, *"list my tabs"*, *"switch
  to the gmail tab"*, *"close this tab"*, *"summarize this page"*, *"remind me to
  call mom in 10 minutes"*, *"add milk and eggs to my shopping list"*.
- **Interrupt her:** while Luna is speaking, say `Luna, …` again — she stops and
  takes the new command. Or click **Stop talking**.

## Always-on listening (headless, offline) & greeting

- **Listening** runs in a hidden **offscreen document** using an on-device **Vosk**
  speech engine (WebAssembly). It keeps working with the side panel **closed**.
  Nothing is uploaded — audio is transcribed locally; only the command *text* is
  sent to your backend.
- **First enable** loads the ~40 MB model (*“Loading speech model…”*), a few seconds.
- It **resumes on browser start** (if it was on and you're logged in), and Luna
  greets you by name for the time of day with a question that rotates daily —
  *"Hi Ronak, good morning… What's the plan for today?"*
- **Speaking** uses the `chrome.tts` engine from the background worker, so the
  greeting and replies work even with no page open.
- **Chrome always shows a microphone-in-use indicator** while listening. That's a
  privacy guarantee and can't be hidden — but it needs no open panel or screen space.

## Voice (⚙ Settings)

- Pick a **Voice** and adjust **Speed / Pitch**, then **Test voice**.
- The default auto-picks the most FRIDAY-like voice available — a British female
  voice (e.g. *Microsoft Sonia / Hazel* on Windows, *Google UK English Female* in
  Chrome). Edge's online "Natural" voices sound closest to FRIDAY.

---

## File map

| Path | Role |
|------|------|
| `manifest.json` | MV3 config: permissions, CSP (`wasm-unsafe-eval`), web-accessible assets |
| `background.js` | Controller: auth, backend calls, action executor, `chrome.tts`, greeting, offscreen lifecycle |
| `offscreen.html/js` | Hidden page: mic capture + Vosk STT + wake-word gating |
| `sidepanel.html/js/css` | UI: login, settings, voice picker, transcript log, manual mic |
| `permission.html/js` | One-shot page to grant the microphone (side panels can't prompt) |
| `vendor/vosk.js` | Vosk loader, patched to load its worker from a packaged file |
| `vendor/vosk-worker.js` | Vosk WASM engine + model glue, patched to be **eval-free** |
| `models/model.tar.gz` | `vosk-model-small-en-us-0.15` (~40 MB, git-ignored) |

---

## Troubleshooting

- **`EvalError … 'unsafe-eval' is not an allowed source`** in `vosk-worker.js`:
  you're running **stale worker code**. Remove the extension and Load unpacked
  again. Confirm the offscreen console prints `[vosk-worker] … eval-free loaded`
  (open `chrome://extensions` → Luna → **Inspect views: offscreen.html**).
- **"Microphone is blocked"**: open the side panel and use the permission tab it
  offers; or set the mic to *Allow* for the extension in Chrome site settings.
- **No transcript when you speak**: check the offscreen console for the model-load
  logs; make sure `models/model.tar.gz` exists (run the build script).
- **Nothing happens on a command**: check the background service-worker console
  (`chrome://extensions` → Luna → **Inspect views: service worker**) and that the
  Django server is running at the configured Server URL.

## Privacy

- Audio is processed **locally** (Vosk WASM). Only the recognized command text —
  and, for “summarize this page”, the page's visible text — is sent to your own
  backend. No third-party speech service is used for always-on listening.
