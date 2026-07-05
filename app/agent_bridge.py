"""
agent_bridge.py
----------------
Real integration with the Week 4 agent (script5_agent.py — LangGraph ReAct
agent + synchronous Playwright + Groq).

Why a SEPARATE PROCESS, not a thread
=====================================
Playwright's sync API needs to launch a subprocess (the browser driver).
On Windows, subprocess creation only works under the Proactor event loop —
but FastAPI/uvicorn/anyio can end up forcing a Selector event loop for their
own socket handling, and that choice can leak into any thread in the same
process no matter what event-loop policy we set beforehand. The result is a
bare `NotImplementedError` the instant Playwright tries to start, with no
useful message.

Running the agent in a genuinely separate OS process sidesteps this
entirely: that process gets its own clean, default asyncio state, exactly
like running `python script5_agent.py` directly — which is what worked in
Week 4. Communication with the parent (FastAPI) process happens over two
`multiprocessing.Queue`s:

  - cmd_queue   : parent -> child, one {"command": "..."} per /command call
  - event_queue : child -> parent, "step" / "result" / "error" events

The child process launches the browser ONCE and keeps it open across
commands (matching script5_agent.py's original interactive_mode design),
so you don't pay browser-launch cost on every single command.

Setup required
==============
  1. Put script5_agent.py (and resume.pdf if you use it) in the project
     ROOT, i.e. next to requirements.txt, one level above app/.
  2. Create a .env file in the project root with:
         GROQ_API_KEY=your_key_here
  3. `playwright install chromium` (one-time, downloads the browser binary)
"""

import asyncio
import multiprocessing as mp
import queue as pyqueue
from pathlib import Path
from typing import Callable, Awaitable

OnStep = Callable[[dict], Awaitable[None]]

_ctx = mp.get_context("spawn")  # "spawn" = clean fresh interpreter (required on Windows anyway)

_cmd_queue = None
_event_queue = None
_worker_process = None
_command_lock = asyncio.Lock()


# --------------------------------------------------------------------------
# Runs INSIDE the child process only.
# --------------------------------------------------------------------------
def _worker_main(cmd_queue, event_queue):
    import sys
    import time
    from pathlib import Path as _Path

    # script5_agent.py lives in the project root (one level above app/)
    sys.path.insert(0, str(_Path(__file__).parent.parent))

    from script5_agent import create_agent, close_browser
    from langchain_core.messages import AIMessage, ToolMessage

    def describe(msg) -> str:
        if isinstance(msg, AIMessage):
            if getattr(msg, "tool_calls", None):
                calls = ", ".join(
                    f"{tc['name']}({tc.get('args', {})})" for tc in msg.tool_calls
                )
                return f"Agent decided to call tool(s): {calls}"
            return f"Agent: {msg.content}"
        if isinstance(msg, ToolMessage):
            return f"Tool '{msg.name}' returned: {msg.content}"
        return str(getattr(msg, "content", msg))

    try:
        agent = create_agent()  # launches the browser once, in THIS process
        event_queue.put({"type": "worker_ready"})
    except Exception as e:
        event_queue.put({"type": "startup_error", "error": f"{type(e).__name__}: {e}"})
        return

    while True:
        item = cmd_queue.get()  # blocks until the parent sends something
        if item is None:  # shutdown signal
            close_browser()
            break

        command = item["command"]
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                seen = 0
                final_text = None
                for chunk in agent.stream(
                    {"messages": [__import__("langchain_core.messages", fromlist=["HumanMessage"]).HumanMessage(content=command)]},
                    stream_mode="values",
                ):
                    messages = chunk["messages"]
                    for msg in messages[seen:]:
                        seen += 1
                        text = describe(msg)
                        event_queue.put({"type": "step", "step": seen, "message": text})
                        final_text = text
                event_queue.put({"type": "result", "output": final_text})
                break  # success, don't retry
            except Exception as e:
                error_str = str(e)
                is_retryable = "tool_use_failed" in error_str or "Failed to call a function" in error_str
                if is_retryable and attempt < max_retries:
                    event_queue.put({
                        "type": "step", "step": 0,
                        "message": f"⚠️ Groq returned a malformed tool call, retrying ({attempt}/{max_retries})...",
                    })
                    time.sleep(2)
                    continue
                event_queue.put({"type": "error", "error": f"{type(e).__name__}: {e}"})
                break


# --------------------------------------------------------------------------
# Runs in the parent (FastAPI) process.
# --------------------------------------------------------------------------

def _ensure_worker():
    global _cmd_queue, _event_queue, _worker_process
    if _worker_process is None or not _worker_process.is_alive():
        _cmd_queue = _ctx.Queue()
        _event_queue = _ctx.Queue()
        _worker_process = _ctx.Process(
            target=_worker_main, args=(_cmd_queue, _event_queue), daemon=True
        )
        _worker_process.start()


async def run_agent(command: str, on_step: OnStep) -> dict:
    loop = asyncio.get_event_loop()

    async with _command_lock:
        _ensure_worker()
        _cmd_queue.put({"command": command})

        while True:
            if not _worker_process.is_alive() and _event_queue.empty():
                raise RuntimeError("Agent worker process died unexpectedly. Check the terminal for a traceback printed by the child process.")

            try:
                event = await loop.run_in_executor(None, lambda: _event_queue.get(timeout=60))
            except pyqueue.Empty:
                raise RuntimeError("Agent worker timed out with no response after 60s.")

            etype = event.get("type")
            if etype == "worker_ready":
                continue  # only happens once, right after browser launch
            if etype == "startup_error":
                raise RuntimeError(f"Failed to start the agent/browser: {event['error']}")
            if etype == "step":
                await on_step({"step": event["step"], "message": event["message"]})
            elif etype == "result":
                return {"output": event["output"]}
            elif etype == "error":
                raise RuntimeError(event["error"])


async def shutdown_agent():
    global _worker_process
    if _worker_process is not None and _worker_process.is_alive():
        try:
            _cmd_queue.put(None)
            _worker_process.join(timeout=5)
        except Exception:
            pass
        if _worker_process.is_alive():
            _worker_process.terminate()
