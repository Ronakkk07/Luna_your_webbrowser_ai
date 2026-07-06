# Luna — Desktop Buddy (Electron)

A mini pixel-art companion who **walks into your screen from the right** when you
say *"Luna"*, listens to your command, runs it via your Django brain, then **sits
on an imaginary floor** in the corner. Click him and he asks *"Do you want me to
leave?"* — say **Yes** and he walks off; **No** and he stays.

He's a transparent, always-on-top overlay that's **click-through everywhere except
over the character**, so he never blocks your work.

```
        say "Luna"  ──▶  🚶 walks in (Front.png, from right edge)
                    ──▶  👂 listens (offline Vosk) until you finish
                    ──▶  🧠 Django brain → { speak, actions }
                    ──▶  🗣️ speaks + acts (opens browser for web commands)
                    ──▶  🧍 sits idle in the corner
        click him   ──▶  💬 "Do you want me to leave?"  [Yes] [No]
             Yes    ──▶  "Oh sure, I'll go…"  🚶 walks out (Back.png)
             No     ──▶  "I knew you love me…"  stays put
```

## Setup

1. **Backend** (the brain) must be running:
   ```bash
   python manage.py runserver          # from the repo root
   ```
2. **Assets** (already copied for you): `assets/Front.png`, `assets/Back.png`,
   `vendor/vosk.js`, `models/model.tar.gz`. If missing, re-copy from `../media`
   and fetch Vosk:
   ```bash
   curl -o vendor/vosk.js https://cdn.jsdelivr.net/npm/vosk-browser@0.0.8/dist/vosk.js
   cp ../extension/models/model.tar.gz models/
   ```
3. **Login config**: copy `config.example.json` → `config.json` and fill in your
   Django username/password (used to fetch a token for the brain).
4. **Install & run**:
   ```bash
   npm install
   npm start
   ```

## Using him

- **Summon:** say *"Luna"* (offline wake word) **or** press **Ctrl+Alt+L** (a
  reliable trigger while we tune the voice).
- **Command:** *"Luna, what time is it"*, *"Luna, give me the news"*,
  *"Luna, open youtube"* (web commands open your default browser),
  *"Luna, remind me to stretch in 20 minutes"*.
- **Stop him talking:** while he's speaking, say **"Luna, stop it"** (or "Luna,
  stop") — he cuts off immediately and sits back down.
- **Dismiss:** click him → **Yes** (leaves; say "Luna" to bring him back) or
  **No** (stays).

When he's not doing anything he uses the **sitting sprite** (`assets/Sit.png`) and
waits; he stands (`Front.png`) to listen and speak, and turns his back
(`Back.png`) to walk off.

## How it works (files)

| File | Role |
|------|------|
| `main.js` | Electron main: transparent, always-on-top overlay; click-through toggle; global hotkey; `openExternal` |
| `preload.js` | Safe IPC bridge (`setInteractive`, `openExternal`, `onSummon`) |
| `renderer/index.html` | The stage: character + speech bubble |
| `renderer/style.css` | Walk-in/out transitions, floor shadow, idle breathing, bubble |
| `renderer/buddy.js` | State machine, backend calls, TTS, dismiss dialog |
| `renderer/voice.js` | Offline Vosk wake-word + command listening |
| `config.json` | Your Django login (git-ignored) |

## Notes & known rough edges (to iterate on)

- **Can't run headless from CI** — needs a desktop. If something misbehaves, open
  the window's DevTools (temporarily add `win.webContents.openDevTools({mode:'detach'})`
  in `main.js`) and share the console.
- **Sprites:** we only have Front/Back, so walk-in uses Front, walk-out uses Back,
  and "sitting" is a settle+shrink. A dedicated sitting sprite would look nicer.
- **Voice:** if the Vosk model is slow/absent, the **Ctrl+Alt+L** hotkey still
  summons him; the console logs `[voice] …` status.
- **Web commands** (open/search/youtube) open your **default browser**. Precise
  tab control would need the browser extension via a native-messaging bridge (later).
