"""
agent_bridge.py
----------------
Real integration with the agent (script5_agent.py — LangGraph ReAct
agent + synchronous Playwright + Groq).

Why a SEPARATE PROCESS, not a thread
=====================================
Playwright's sync API needs to launch a subprocess (the browser driver).
On Windows, subprocess creation only works under the Proactor event loop —
but FastAPI/uvicorn/anyio can end up forcing a Selector event loop for their
own socket handling, and that choice can leak into any thread in the same
process no matter what event-loop policy we set beforehand. Running the
agent in a genuinely separate OS process sidesteps this entirely.

Communication with the parent (FastAPI) process happens over two
multiprocessing.Queues: cmd_queue (parent -> child) and event_queue
(child -> parent, "step"/"result"/"error" events).

Setup required
==============
  1. script5_agent.py in the project ROOT, one level above app/.
  2. .env in the project root with GROQ_API_KEY=your_key_here
  3. `playwright install chromium` (one-time)
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

    sys.path.insert(0, str(_Path(__file__).parent.parent))

    from script5_agent import create_agent, close_browser, CORE_TOOLS, FORM_TOOLS, SUMMARY_TOOLS
    from langchain_core.messages import AIMessage, ToolMessage

    _FORM_KEYWORDS = (
        "form", "fill", "field", "apply", "application", "sign up", "signup",
        "register", "registration", "checkout"
    )
    _SUMMARY_KEYWORDS = (
        "summarize", "summary", "summarise", "tldr", "compare", "comparison",
        "analyze", "analyse", "job description", "recap"
    )

    def classify_command(command: str) -> list[str]:
        text = command.lower()
        tools = list(CORE_TOOLS)
        if any(k in text for k in _FORM_KEYWORDS):
            tools += FORM_TOOLS
        if any(k in text for k in _SUMMARY_KEYWORDS):
            tools += SUMMARY_TOOLS
        return tools

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
        from script5_agent import get_page
        get_page()
        event_queue.put({"type": "worker_ready"})
    except Exception as e:
        event_queue.put({"type": "startup_error", "error": f"{type(e).__name__}: {e}"})
        return

    while True:
        item = cmd_queue.get()  # blocks until the parent sends something
        if item is None:  # shutdown signal
            close_browser()
            break

        if item.get("direct_action") == "submit_current_form":
            from script5_agent import submit_current_form as _submit_fn
            try:
                result = _submit_fn()
                event_queue.put({"type": "direct_result", "output": result})
            except Exception as e:
                event_queue.put({"type": "direct_error", "error": f"{type(e).__name__}: {e}"})
            continue

        command = item["command"]
        tool_names = classify_command(command)
        event_queue.put({
            "type": "step", "step": 0,
            "message": f"🧭 Routed to tools: {', '.join(tool_names)}",
        })

        # Retry plan uses only CONFIRMED-VALID, non-deprecated Groq models
        # (per console.groq.com/docs/deprecations): openai/gpt-oss-120b is
        # the official recommended replacement for the deprecated
        # llama-3.3-70b-versatile. openai/gpt-oss-20b as a lighter fallback.
        retry_plan = [
            {"temperature": 0, "model": "openai/gpt-oss-120b"},
            {"temperature": 0.3, "model": "openai/gpt-oss-120b"},
            {"temperature": 0, "model": "openai/gpt-oss-20b"},
            {"temperature": 0.3, "model": "openai/gpt-oss-20b"},
        ]
        max_retries = len(retry_plan)
        agent = create_agent(temperature=retry_plan[0]["temperature"], tool_names=tool_names, model=retry_plan[0]["model"])

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
                    next_cfg = retry_plan[attempt]
                    event_queue.put({
                        "type": "step", "step": 0,
                        "message": f"⚠️ Malformed tool call, retrying with model={next_cfg['model']} temperature={next_cfg['temperature']} ({attempt}/{max_retries - 1})...",
                    })
                    time.sleep(2)
                    agent = create_agent(temperature=next_cfg["temperature"], tool_names=tool_names, model=next_cfg["model"])
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
                continue
            if etype == "startup_error":
                raise RuntimeError(f"Failed to start the agent/browser: {event['error']}")
            if etype == "step":
                await on_step({"step": event["step"], "message": event["message"]})
            elif etype == "result":
                return {"output": event["output"]}
            elif etype == "error":
                raise RuntimeError(event["error"])


async def submit_current_form() -> str:
    loop = asyncio.get_event_loop()
    async with _command_lock:
        _ensure_worker()
        _cmd_queue.put({"direct_action": "submit_current_form"})
        try:
            event = await loop.run_in_executor(None, lambda: _event_queue.get(timeout=30))
        except pyqueue.Empty:
            raise RuntimeError("Submit action timed out with no response after 30s.")
        if event.get("type") == "direct_result":
            return event["output"]
        elif event.get("type") == "direct_error":
            raise RuntimeError(event["error"])
        raise RuntimeError(f"Unexpected event during submit: {event}")


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