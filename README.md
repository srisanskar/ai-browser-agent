# Week 5 — Backend API Server

FastAPI backend that the frontend talks to. It wraps your **real Week 4
agent** (`script5_agent.py` — LangGraph ReAct agent + synchronous Playwright
+ Groq).

## Project layout

```
week5-backend/
├── script5_agent.py          # <-- COPY THIS IN from your repo (Week 4)
├── user_profile.json         # <-- optional: copy this in too, gets auto-migrated to SQLite
├── .env                      # <-- create this: GROQ_API_KEY=...
├── app/
│   ├── main.py                # FastAPI app + all routes
│   ├── database.py            # SQLite (aiosqlite) for users + tasks, migrates user_profile.json
│   ├── models.py              # Pydantic request/response schemas
│   ├── agent_bridge.py        # wires script5_agent.py into the API
│   └── websocket_manager.py   # tracks WS clients per task_id, broadcasts steps
├── requirements.txt
└── README.md
```

## 1. Setup

```bash
cd week5-backend

# copy your Week 4 files in
cp /path/to/ai-browser-agent/script5_agent.py .
cp /path/to/ai-browser-agent/user_profile.json .   # optional, auto-migrates to SQLite

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
playwright install chromium   # one-time browser download

echo "GROQ_API_KEY=your_key_here" > .env
```

## 2. Run

```bash
uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000/docs** for Swagger UI.

Note: `script5_agent.py` launches Chromium with `headless=False`, so a real
browser window will pop up the first time you send a command — that's
expected (same behaviour as your Week 4 script). Change it to `headless=True`
inside `script5_agent.py` if you deploy this to a headless server.

## 3. Try it via Swagger UI

1. `GET /user/profile` — you should already see Arjun Sharma's profile,
   auto-migrated from `user_profile.json` the first time the server starts.
2. `POST /command` with `{"command": "Go to https://github.com/trending and tell me the page title"}`.
   Copy the returned `task_id`.
3. `GET /status/{task_id}` repeatedly — `status` goes
   `queued -> running -> completed`, `steps` fills in with each tool
   call/tool result as the agent works (navigate_to, get_page_title, etc.)

## 4. Try the WebSocket (live step-by-step)

```bash
wscat -c ws://localhost:8000/ws/<task_id>
```

You'll see a `history` message first, then a `step` message per tool
call/tool result as the LangGraph agent executes, then a final `status:
completed` message with the result.

## How the integration works

- `app/agent_bridge.py` imports `create_agent` and `close_browser` directly
  from your `script5_agent.py`. It calls `agent.stream(..., stream_mode="values")`
  instead of `.invoke()` so every intermediate LangGraph message (tool calls
  + tool results) streams out as it happens — that's what powers the
  WebSocket step-by-step updates.
- `script5_agent.py` is 100% synchronous (sync Playwright API + a global
  browser/page). Since Playwright's sync API is thread-affine, all agent
  calls run on a single dedicated background thread
  (`ThreadPoolExecutor(max_workers=1)`), and an `asyncio.Lock` makes sure
  only one command runs at a time (there's only one shared browser tab —
  matches your Week 4 design).
- The browser launches lazily on the first `/command` call and stays open
  across requests (like running `interactive_mode()` in your original
  script). It's closed cleanly on server shutdown.

## Notes on design decisions

- **Background execution**: `POST /command` uses FastAPI's `BackgroundTasks`
  so the HTTP request returns instantly with a `task_id`; the agent keeps
  running after the response is sent.
- **Persistence**: task status/steps are written to SQLite as they happen,
  so `GET /status/{task_id}` survives a server restart mid-run (the
  WebSocket connection itself won't, obviously — reconnect to get the
  `history` replay).
- **Resume field**: your Week 4 profile stores `resume_path` (a file path);
  the assignment asks for resume *text* in SQLite. The migration seeds
  `resume_text` with the path as a placeholder — send a real
  `POST /user/profile` with extracted resume text to fix that up properly
  (e.g. parse the PDF with a library like `pypdf` first).
- **CORS**: wide open (`allow_origins=["*"]`) for now so your Cloudflare
  Pages frontend can call it from any origin during development — tighten
  this before deploying for real.
