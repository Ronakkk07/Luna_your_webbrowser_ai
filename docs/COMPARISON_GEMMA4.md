# Luna vs. Transformers.js Gemma‑4 Browser Assistant

A feature-by-feature comparison between **Luna** (this project) and
**[nico-martin/gemma4-browser-extension](https://github.com/nico-martin/gemma4-browser-extension)**,
and the plan for what Luna adopts while keeping its base layer (Django brain + voice + `{speak, actions}`).

## What the Gemma‑4 extension is

A Chrome MV3 assistant that runs **Gemma 4 E2B entirely in the browser** via
**Transformers.js + WebGPU**. No backend, no API keys, nothing leaves the device.
It's a **text chat** agent in a side panel with real (native) tool‑calling.

## Its tools

| Group | Tools | What it does |
|---|---|---|
| Tabs | `get_open_tabs`, `go_to_tab`, `open_url`, `close_tab` | list / switch / open / close tabs by natural language |
| Page RAG | `ask_website`, `highlight_website_element` | answer questions about the current page via **semantic retrieval**, and **visually highlight + scroll** to the element |
| History | `find_history` | **semantic search of browsing history** (by meaning, not keywords) |
| Web | `google_search` | external search for info gathering |

## Under the hood

- **Model:** `onnx-community/gemma-4-E2B-it-ONNX` (quantized ONNX) on **WebGPU**, loaded
  once in the **background service worker** and shared across tabs / panel / content script.
- **Embeddings:** `all-MiniLM-L6-v2` for semantic search. Page content is chunked
  (headings / paragraphs / lists) and embedded; **visited pages are indexed into an
  IndexedDB vector store** for history search. That's real RAG.
- **Agentic loop:** Gemma emits a tool‑call token block → background executes the tool →
  feeds the result back into the model → it keeps reasoning (multi‑step).
- **Stack:** React 19 + Tailwind + Vite; content script for DOM extraction + highlighting.

**Limits:** needs Chrome 113+ with a WebGPU‑capable GPU; a multi‑GB model download on
first use; **text‑only (no voice)**; the small on‑device model is **much weaker than
Gemini** and can't do live/heavy work well.

## Luna vs. Gemma‑4 extension

| | **Luna** | **Gemma‑4 ext** |
|---|---|---|
| Brain | Django backend + **Gemini/HF** (strong, tiered) | **Gemma 4 E2B in‑browser** (small, weaker) |
| Input/Output | **Voice‑first** (wake word, Whisper) + **TTS** | text chat only |
| Live data | **web research** (Google News) | limited |
| Privacy | text → server + cloud LLM | **100% local** |
| Deployment | needs backend running | **zero backend** |
| Requirements | server + tunnel | WebGPU GPU + big download |
| Tool use | single‑shot intent → `{speak, actions}` | **agentic multi‑step loop** |
| Page Q&A | whole‑page text → LLM | **RAG (embeddings + retrieval)** |
| History search | ❌ | ✅ semantic |
| Highlighting | ❌ | ✅ |
| Personality/buddy | ✅ voice companion, desktop buddy | ❌ |

**Luna already wins:** voice + hands‑free, a much stronger brain (Gemini), live web
research, and the companion/desktop‑buddy experience.

**They win (what to steal):** agentic tool‑loop, RAG page Q&A, semantic history search,
element highlighting, and zero‑backend privacy mode.

## What Luna adopts (keeping the base layer)

Base = **Django brain + `{speak, actions}` + voice**. Each slots in without changing that:

1. **Tab tools** (`get_open_tabs`, `go_to_tab`, `open_url`, `close_tab`) — pure
   extension‑side actions; the brain emits them, the extension executes via `chrome.tabs`.
2. **Semantic history search** (`find_history`) — client‑side IndexedDB vector store +
   Transformers.js `all-MiniLM` embeddings (history is private → keep it local).
3. **RAG page Q&A** (`ask_website`) — chunk + embed + retrieve relevant sections instead
   of dumping the whole page. Done server‑side so it stays in the base.
4. **Element highlighting** (`highlight_website_element`) — new `highlight` action + a
   content script that scrolls to and outlines the element.
5. **Agentic tool‑loop** — evolve the backend router from single‑shot into a Gemini
   tool‑calling loop (call tools, feed results back, iterate) that still outputs `{speak, actions}`.
6. **Optional local‑Gemma fallback** — bundle Transformers.js + a small model for
   offline / privacy mode; fall back to Gemini for heavy lifting (hybrid brain).

## Strategic takeaway

Don't rebuild as fully‑local — that trades Gemini's quality and Luna's voice‑first edge
for a weaker model and a huge download. Make Luna **hybrid**: cloud brain (primary) + these
on‑device tricks. Keep everything that makes Luna better, gain their privacy/agentic strengths.

Sources: [GitHub repo](https://github.com/nico-martin/gemma4-browser-extension),
[DeepWiki architecture](https://deepwiki.com/nico-martin/gemma4-browser-extension),
[HF blog](https://huggingface.co/blog/transformersjs-chrome-extension),
[Chrome Web Store](https://chromewebstore.google.com/detail/transformersjs-gemma-4-br/dhaknnnkcdkjhcclchmnfdhddoehoool).
