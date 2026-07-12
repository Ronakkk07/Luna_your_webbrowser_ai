"""Agentic tool-loop (ReAct-style, model-agnostic).

The brain can call **server tools** to gather info or take server-side actions
(time, web research, news, reminders, shopping), see each result, and chain the
next step — then emit a final answer plus any **browser actions** for the extension
to run (open_tab, highlight, find_history, ...). This replaces one-shot
intent→action for the reasoning-heavy commands, while the deterministic fast path
in intent.py still handles obvious commands with no LLM call.

Design notes:
- Protocol is plain JSON over ``providers.complete`` so it works with any model
  (Gemini / Groq / HF) — no dependency on a provider's native function-calling.
- The server/extension split means browser tools can't return results mid-loop, so
  they're planned into the final ``actions`` list; server tools loop with observations.
- Everything is defensive: on a parse error, missing provider, or exhausted steps we
  return ``None`` and the caller falls back to the classic ``route_intent`` pipeline.
- Adding a tool = one ``_TOOLS`` entry (open/closed) — no change to the loop.
"""
import json
from collections import namedtuple

from assistant.services import providers

Ctx = namedtuple("Ctx", ["user", "user_id", "history"])
Tool = namedtuple("Tool", ["name", "description", "args", "run"])

# Browser actions the extension knows how to execute (see background.js HANDLERS).
# The agent may only emit these in its final step; execution happens client-side.
_BROWSER_ACTIONS = {
    "open_tab": '{"type":"open_tab","url":"https://..."}',
    "search_web": '{"type":"search_web","query":"...","url":"https://www.google.com/search?q=..."}',
    "youtube_play": '{"type":"youtube_play","query":"...","url":"https://www.youtube.com/results?search_query=..."}',
    "switch_tab": '{"type":"switch_tab","hint":"gmail"}',
    "close_tab": '{"type":"close_tab","hint":"youtube" }',
    "list_tabs": '{"type":"list_tabs"}',
    "summarize_page": '{"type":"summarize_page"}',
    "read_page": '{"type":"read_page","question":"..."}',
    "highlight": '{"type":"highlight","query":"the text to highlight"}',
    "find_history": '{"type":"find_history","query":"topic"}',
}
_BROWSER_ACTION_TYPES = set(_BROWSER_ACTIONS)
_MAX_OBS = 1400  # cap each observation so the prompt stays bounded


# --------------------------------------------------------------------------- #
# Server tools                                                                  #
# --------------------------------------------------------------------------- #
def _t_get_time(args, ctx):
    from assistant.services.router import _handle_get_time

    return _handle_get_time()["speak"]


def _t_web_research(args, ctx):
    from assistant.services.web_research import gather
    from assistant.services.llm import research_answer

    query = (args.get("query") or "").strip()
    if not query:
        return "No query given."
    return research_answer(query, gather(query), history=ctx.history, user_id=ctx.user_id)


def _t_get_news(args, ctx):
    from assistant.services.news import fetch_headlines, NewsLookupError
    from assistant.services.llm import news_briefing

    query = (args.get("query") or "").strip() or None
    try:
        headlines = fetch_headlines(query=query, limit=8)
    except NewsLookupError:
        return "The news service is unavailable right now."
    return news_briefing(headlines, query=query, user_id=ctx.user_id)


def _t_create_reminder(args, ctx):
    from reminders.tasks import build_reminder_datetime, create_reminder_for_user

    task = (args.get("task") or "").strip() or "General reminder"
    dt = build_reminder_datetime(args.get("datetime"))
    r = create_reminder_for_user(user=ctx.user, task_name=task, dt=dt)
    return f"Reminder set: {r.task} at {r.date_time.strftime('%A %I:%M %p')}."


def _t_list_reminders(args, ctx):
    rs = ctx.user.reminders.all()
    if not rs.exists():
        return "You have no reminders."
    return "Reminders: " + ", ".join(
        f"{r.task} at {r.date_time.strftime('%A %I:%M %p')}" for r in rs
    )


def _t_add_shopping(args, ctx):
    from shopping.tasks import add_shopping_items_for_user

    added = add_shopping_items_for_user(ctx.user, args.get("items", []))
    return f"Added: {', '.join(added)}." if added else "Those items were already on the list."


def _t_list_shopping(args, ctx):
    items = ctx.user.shopping_items.all()
    if not items.exists():
        return "Your shopping list is empty."
    return "Shopping list: " + ", ".join(f"{i.item_name} ({i.quantity})" for i in items)


_TOOLS = {
    t.name: t
    for t in [
        Tool("get_time", "Current date/time.", "{}", _t_get_time),
        Tool("web_research", "Look up CURRENT/real-time info from the web (news, scores, prices, 'latest').", '{"query":"..."}', _t_web_research),
        Tool("get_news", "Headlines/news briefing, optionally on a topic.", '{"query":"optional topic"}', _t_get_news),
        Tool("create_reminder", "Create a reminder.", '{"task":"...","datetime":"in 10 minutes"}', _t_create_reminder),
        Tool("list_reminders", "List the user's reminders.", "{}", _t_list_reminders),
        Tool("add_shopping", "Add items to the shopping list.", '{"items":["milk","eggs"]}', _t_add_shopping),
        Tool("list_shopping", "List the shopping list.", "{}", _t_list_shopping),
    ]
}


# --------------------------------------------------------------------------- #
# Loop                                                                          #
# --------------------------------------------------------------------------- #
def _build_prompt(text, history, scratchpad, force_final):
    tool_lines = "\n".join(f"- {t.name}{ ' ' + t.args if t.args != '{}' else '' }: {t.description}" for t in _TOOLS.values())
    action_lines = "\n".join(f"- {name}: {shape}" for name, shape in _BROWSER_ACTIONS.items())
    hist = f"\nConversation so far:\n{history}\n" if history else ""
    work = ""
    if scratchpad:
        work = "\nWork so far (tool results):\n" + "\n".join(
            f"- {name} -> {obs}" for name, obs in scratchpad
        ) + "\n"
    finalize = (
        "\nYou have gathered enough. You MUST now respond with action \"final\"."
        if force_final
        else ""
    )
    return f"""
You are Luna, a voice browser assistant. Decide the next step to handle the user's
request. You can call SERVER TOOLS to gather info or act, one at a time, and see each
result. When ready, give a FINAL spoken answer plus any BROWSER ACTIONS for the
extension to run.

SERVER TOOLS (callable, results come back to you):
{tool_lines}

BROWSER ACTIONS (only allowed inside the final response; they run in the browser):
{action_lines}
{hist}{work}
User request: "{text}"
{finalize}
Respond with ONE JSON object, nothing else:
- To call a tool: {{"action":"call_tool","tool":"<name>","args":{{...}}}}
- To finish:      {{"action":"final","speak":"<spoken reply, plain text>","browser_actions":[<zero or more browser actions>]}}

Rules:
- Speak naturally (1-5 sentences), no markdown. Put real info from tool results into "speak".
- Only use a browser action when the user wants something done in the browser.
- Don't call the same tool twice with the same args. Prefer finishing once you can answer.
JSON:
"""


def _parse(raw):
    if not raw:
        return None
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    # Grab the first JSON object if the model added stray text.
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        return json.loads(cleaned)
    except Exception:
        return None


def _sanitize_actions(actions):
    out = []
    if isinstance(actions, list):
        for a in actions:
            if isinstance(a, dict) and a.get("type") in _BROWSER_ACTION_TYPES:
                out.append(a)
    return out


def run_agent(text, user, history="", max_steps=4):
    """Run the tool-loop. Returns {"speak","actions"} or None to fall back."""
    user_id = getattr(user, "id", None)
    ctx = Ctx(user=user, user_id=user_id, history=history)
    scratchpad = []

    for step in range(max_steps):
        force_final = step == max_steps - 1
        prompt = _build_prompt(text, history, scratchpad, force_final)
        try:
            raw = providers.complete(prompt, user_id=user_id, tier="complex", max_tokens=700, temperature=0.3)
        except Exception as e:
            print("agent provider error:", e)
            return None

        decision = _parse(raw)
        if not isinstance(decision, dict):
            return None

        action = decision.get("action")
        if action == "final":
            speak = (decision.get("speak") or "").strip()
            actions = _sanitize_actions(decision.get("browser_actions"))
            if not speak and not actions:
                return None
            return {"speak": speak, "actions": actions}

        if action == "call_tool" and not force_final:
            name = decision.get("tool")
            tool = _TOOLS.get(name)
            if not tool:
                scratchpad.append((str(name), f"No such tool '{name}'."))
                continue
            try:
                obs = str(tool.run(decision.get("args") or {}, ctx))[:_MAX_OBS]
            except Exception as e:
                obs = f"failed: {e}"
            scratchpad.append((name, obs))
            continue

        # Unrecognized shape -> fall back.
        return None

    return None
