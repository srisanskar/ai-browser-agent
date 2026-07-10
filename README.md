# AI Browser Agent

A personal AI assistant that lives alongside a browser and does the repetitive digital
grunt work - filling forms, summarizing pages, navigating sites - using an LLM agent
that actually drives a real Chromium tab.

Built over a 8-week structured curriculum, followed by a final project extending it
with two production-ready modules.

## Tech stack

- **Browser automation:** Playwright (sync API)
- **Agent reasoning:** LangGraph (ReAct agent) + Groq (`openai/gpt-oss-120b`)
- **Backend:** FastAPI + SQLite (aiosqlite) + WebSockets
- **Frontend:** React (Vite)
- **Intent parsing:** Groq chat completions, structured JSON output

## Progress

- [x] Week 1 - Environment setup, first Playwright script
- [x] Week 2 - Browser automation scripts (navigation, form filling, tab management)
- [x] Week 3 - Intent parser: natural language → structured action JSON (`script4_intent_parser.py`)
- [x] Week 4 - LangGraph ReAct agent wired to Playwright tools (`script5_agent.py`)
- [x] Week 5 - FastAPI backend: `/command`, `/status/{task_id}`, `/user/profile`, WebSocket streaming
- [x] Week 6 - React frontend: command bar, live activity log, profile settings, architecture doc, pytest tests
- [x] Final Project - Module 1 (Intelligent Form Filling) + Module 3 (Page Summarization)

## Final project - what's actually implemented

Picked 2 modules to make genuinely production-ready rather than spreading thin across
all 6 (per the mentor's advice):

### Module 1 - Intelligent Form Filling
- Detects every input/select/textarea on a page (`detect_form_fields`)
- Matches fields by their actual label, not just position - won't put a name into a
  field labeled "Password" just because it's the first text input
- Looks up known data from a persistent profile (`get_profile_value`); if something's
  missing, it asks instead of guessing, and remembers the answer for next time
  (`save_profile_field`)
- Drafts long-form answers (SOP, "why this role") from stored profile + resume
  (`generate_long_text`)
- **Never submits a form itself.** There's no submit tool available to the LLM at all -
  submission only happens through a separate `/form/submit` endpoint the UI calls after
  a human reviews the filled-in fields. This was a deliberate design choice, not an
  oversight - the agent fills and reports, a person approves and submits.

### Module 3 - Page & Content Summarization
- `summarize_current_page` / `summarize_url` - TL;DR, key points, action items, tags
- `analyze_job_description` - required skills, nice-to-haves, what to highlight from
  your own background
- `compare_pages` - side-by-side comparison table across multiple URLs
- Every summary saves automatically to a history table, viewable in the UI's Summaries tab

### Module 6 (partial) - Profile memory
Rolled into Module 1's implementation: the SQLite profile grew a flexible `extra_fields`
column so the agent can learn and store new fields (LinkedIn URL, college, skills) it
wasn't originally given, without a schema change every time.

## Project structure

```
ai-browser-agent/
├── script5_agent.py         # LangGraph agent + all browser/form/summary tools
├── user_profile.json        # legacy Week 4 profile (auto-migrated into SQLite)
├── models.py                 # Pydantic data contracts (UserProfile, Task, AgentAction)
├── architecture.md           # system diagram + design decisions
├── test_intent_parser.py     # pytest suite for the Week 3 intent parser
├── app/                       # FastAPI backend
│   ├── main.py
│   ├── database.py
│   ├── agent_bridge.py        # runs the agent in a separate process (see below)
│   ├── models.py
│   └── websocket_manager.py
└── frontend/                  # React UI
    └── src/
        ├── App.jsx
        ├── api.js
        └── components/
```

## Running it

```bash
# backend
venv\Scripts\activate
uvicorn app.main:app --reload --reload-dir app --port 8000

# frontend (separate terminal)
cd frontend
npm run dev
```

Needs a `.env` in the project root with `GROQ_API_KEY=your_key`.

## Things that broke and how they got fixed

Keeping this section because the debugging was most of the actual learning:

- **Playwright + Windows + asyncio:** `sync_playwright()` needs the Proactor event loop
  for subprocess creation, but uvicorn forces the Selector loop for its own socket
  handling - and that choice leaks into any thread in the same process. Fix: run the
  agent in a genuinely separate OS process instead of a thread, communicating with
  FastAPI over `multiprocessing.Queue`.
- **"Cannot switch to a different thread":** LangGraph's `ToolNode` calls each tool from
  its own worker thread, but Playwright's sync API locks a `Page` to whichever thread
  created it. Fix: pin every real Playwright call through one dedicated, persistent
  worker thread inside the agent process.
- **Malformed tool calls (`tool_use_failed`):** turned out to be two stacked issues -
  `llama-3.3-70b-versatile` got deprecated by Groq mid-project, and separately,
  LangGraph's default tool binding left `tool_choice` effectively forced instead of
  optional, which pushes the model into broken output on any turn where it just wants
  to reply in plain text. Fixed by switching to `openai/gpt-oss-120b` and explicitly
  binding tools with `tool_choice="auto"`.
- **Orphaned processes:** `uvicorn --reload` only restarts the main FastAPI process -
  the agent's child process survives reloads on purpose (so the browser doesn't
  relaunch every edit), which means a stale agent process can quietly keep answering
  requests with old code long after you think you've updated something. Worth a full
  process kill + restart whenever something doesn't behave like the code you just wrote.

## What's next

Module 2 (Email) and Module 4 (Calendar) are the natural next additions, but both need
real Google OAuth setup rather than just new agent tools - bigger lift than what's here.
Module 5 (cross-module commands like "apply, add to calendar, and email my mentor")
only makes sense once at least two of those are solid.
