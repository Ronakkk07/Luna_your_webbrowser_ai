# Publishing the Luna extension

## The one hard prerequisite: a reachable backend

The extension is only the *face*. Every command goes to a **Luna server** (your
Django backend) for intent, transcription (Whisper), and answers. So:

- **Personal / small (do this first):** run the backend yourself (locally or on a
  small host) and set the **Server URL** in Settings. You can publish the extension
  as **Unlisted** (only people with the link install it) or just **Load unpacked**.
- **Public listing (bigger project):** every user needs the backend reachable, so
  **you must host a multi-user backend** with the AI keys server-side. Note the
  cost/latency reality: **Whisper transcription runs per command** — on shared CPU
  hosting that's slow and can get expensive at scale. Budget for a GPU or a cloud
  STT before a wide launch. See `DEPLOY.md` for hosting the backend.

> Before a public build, change the default `DEFAULT_BASE_URL` (in
> `extension/background.js` and `extension/sidepanel.js`) from `127.0.0.1:8000` to
> your hosted **https://** URL, and restrict the backend's CORS/ALLOWED_HOSTS.

## Build the package

```bash
python scripts/package_extension.py
# -> dist/luna-extension-0.1.0.zip  (upload this)
```

## Chrome Web Store steps

1. Create a developer account (one-time \$5): https://chrome.google.com/webstore/devconsole
2. **New item** → upload `dist/luna-extension-<version>.zip`.
3. Fill the listing:
   - **Category:** Productivity
   - **Description:** from the manifest, expanded.
   - **Icon:** `icons/icon128.png` (already bundled).
   - **Screenshots:** 1280×800 or 640×400 — capture the side panel, a command +
     spoken answer, and the settings. (At least one required.)
   - **Privacy policy URL:** host `docs/PRIVACY.md` somewhere public and paste the URL.
4. **Privacy practices** tab — declare data use (see below) and certify no remote code.
5. Submit for review (usually a few days). The broad permissions + microphone will
   get scrutiny — the justifications below are what the reviewer wants.

## Permission justifications (paste into the review form)

| Permission | Why Luna needs it |
|---|---|
| `tabs` | Open, switch, close, and list tabs on voice command. |
| `scripting` | Read the current page when you ask Luna to summarize/answer about it, and press play on YouTube when you ask it to play a video. Only on your request. |
| `storage` | Store your login token and settings (name, server URL, voice) locally. |
| `sidePanel` | The assistant's UI lives in the side panel. |
| `search` | Run a web search in your default engine when you ask. |
| `offscreen` | Run the on-device wake-word listener + speech engine in the background so "Luna" works with the panel closed. |
| `tts` | Speak responses aloud. |
| `host_permissions: <all_urls>` | (1) Read the page you ask Luna about; (2) control YouTube playback on youtube.com; (3) send commands to the Luna server URL you configure (any domain). |

- **Remote code:** None. The speech engine (Vosk WASM) and model are **bundled** in
  the package — no code is fetched at runtime. (MV3-compliant.)

## Data-use declaration (Privacy practices tab)

- **Audio:** collected to process voice commands (wake word handled on-device;
  command audio sent to the user's configured server).
- **Website content:** collected only when the user asks about a page, to answer.
- **Authentication info:** username/password sent to the user's server for a login token.
- Not sold; not used for advertising or unrelated purposes.

## Pre-submit checklist

- [ ] Backend hosted at an HTTPS URL (for public) and `DEFAULT_BASE_URL` updated.
- [ ] `python manage.py check` clean; keys (`GEMINI_API_KEY`, `HF_API_TOKEN`) set as env vars on the host, not committed.
- [ ] `.env` git-ignored; rotate any keys that were ever shared.
- [ ] Privacy policy hosted; URL added to the listing.
- [ ] Screenshots captured.
- [ ] `python scripts/package_extension.py` produced the zip; test it via Load unpacked once more.
