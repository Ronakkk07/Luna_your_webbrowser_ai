# Luna — Privacy Policy

_Last updated: 2026-07-11_

Luna is a voice assistant browser extension. This policy explains what data it
handles and why. Host this page at a public URL and put that URL in the Chrome
Web Store listing (a privacy policy URL is required).

## What Luna processes

- **Your voice (commands):** When you use the microphone, audio is captured to
  understand your command.
  - The **wake word** ("Luna") is detected **on your device** (offline, via the
    bundled Vosk engine). This audio is not sent anywhere.
  - Your **spoken command** is sent to **your configured Luna server** (the
    "Server URL" you set in Settings) to be transcribed and acted on.
- **Page content (only on request):** When you ask Luna to "summarize this page"
  or a question about the page you're viewing, the visible text of that page is
  sent to your Luna server to produce an answer. Luna does **not** read or send
  page content unless you ask.
- **Account credentials:** Your username/password are sent to your Luna server to
  obtain a login token, which is stored locally in the browser's extension
  storage. Passwords are not stored.
- **Settings:** Your name, server URL, and voice preferences are stored locally in
  extension storage.

## Where data goes

Luna sends data only to the **server you configure** (your own Luna backend). That
server may use third-party AI services (e.g. Google Gemini, Hugging Face) to
generate responses, and Google News for news/web results. Luna does not sell data
or use it for advertising.

## What Luna does NOT do

- It does not record or transmit audio unless you invoke it (wake word or mic button).
- It does not continuously read your screen or browsing.
- It does not share data with third parties beyond the AI/services your server uses
  to fulfill your request.

## Your control

- Turn off "Always listen" to stop background wake-word detection.
- Log out to clear stored tokens.
- Remove the extension to delete all locally stored data.

## Contact

Questions: <your-email@example.com>
