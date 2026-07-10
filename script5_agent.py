"""
Script 5 — LangChain Agent with Playwright Browser Tools
Uses synchronous Playwright + LangGraph ReAct agent.
Includes retry logic for inconsistent tool call formatting.

FIX APPLIED: LangGraph's ToolNode calls each tool from a fresh worker
thread every time (even for a single sequential tool call). Playwright's
sync API locks its Page/Browser objects to whichever exact thread created
them, so calling from a different thread throws:
    "Cannot switch to a different thread"
The fix: route EVERY actual Playwright operation (browser launch + every
tool's page interaction) through one dedicated, persistent single-worker
thread, via _run_on_pw_thread(). No matter which thread LangGraph calls
the @tool function from, the real Playwright work always happens on that
same pinned thread underneath.

FINAL PROJECT ADDITIONS — Module 1 (Intelligent Form Filling) and
Module 3 (Page/Content Summarization). New tools read/write the SAME
SQLite database the FastAPI backend uses (app_data.db, one level up),
via plain sync `sqlite3` — safe to do from a separate process since
SQLite handles concurrent access from multiple processes natively.
"""

import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, BrowserContext
from langchain.tools import tool
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage
from groq import Groq as _GroqClient

load_dotenv()

# Same database file the FastAPI backend (app/database.py) uses.
DB_PATH = Path(__file__).parent / "app_data.db"
CORE_PROFILE_FIELDS = {"name", "email", "phone", "address", "resume_text"}


# ── Dedicated Playwright thread ────────────────────────────────────────────────
_pw_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright-worker")


def _run_on_pw_thread(fn, *args, **kwargs):
    return _pw_executor.submit(fn, *args, **kwargs).result()


# ── Global browser state (only ever touched from the pw thread) ───────────────
_playwright_instance = None
_browser = None
_context: BrowserContext = None
_page: Page = None


def _get_page_impl() -> Page:
    global _playwright_instance, _browser, _context, _page

    # SELF-HEALING CHECK: the original version of this function only ever
    # checked `if _page is None`, meaning it launched a browser exactly once
    # and then returned that same Page object forever — even after it had
    # been closed (window closed by hand, crash, etc). Every tool call after
    # that point failed identically ("Target page, context or browser has
    # been closed") no matter what URL was passed, because it's the SAME
    # dead Page being reused. Now we actually check liveness and relaunch.
    needs_relaunch = (
        _page is None
        or _page.is_closed()
        or _browser is None
        or not _browser.is_connected()
    )

    if needs_relaunch:
        for obj in (_context, _browser, _playwright_instance):
            try:
                if obj:
                    obj.close() if hasattr(obj, "close") else obj.stop()
            except Exception:
                pass
        _playwright_instance = sync_playwright().start()
        _browser = _playwright_instance.chromium.launch(headless=False)
        _context = _browser.new_context()
        _page = _context.new_page()
        print("🌐 Browser (re)launched.")

    return _page


def get_page() -> Page:
    return _run_on_pw_thread(_get_page_impl)


def _close_browser_impl():
    global _playwright_instance, _browser, _context, _page
    try:
        if _page and not _page.is_closed():
            _page.close()
        if _context:
            _context.close()
        if _browser:
            _browser.close()
        if _playwright_instance:
            _playwright_instance.stop()
    except Exception:
        pass
    finally:
        _page = None
        _context = None
        _browser = None
        _playwright_instance = None
    print("🔒 Browser closed.")


def close_browser():
    _run_on_pw_thread(_close_browser_impl)


# ── User profile (legacy JSON — kept for backward compat with Week 4) ─────────

PROFILE_FILE = "user_profile.json"

def load_profile() -> dict:
    if os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE, "r") as f:
            return json.load(f)
    return {
        "name": "Arjun Sharma",
        "email": "arjun.sharma@example.com",
        "phone": "9876543210",
        "address": "12 MG Road, Kanpur, UP",
        "resume_path": "resume.pdf"
    }

def save_profile(profile: dict):
    with open(PROFILE_FILE, "w") as f:
        json.dump(profile, f, indent=2)


# ── Tools ──────────────────────────────────────────────────────────────────────

@tool
def navigate_to(url: str) -> str:
    """Navigate the browser to a URL. Input: full URL like https://www.google.com"""
    def _do():
        page = _get_page_impl()
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        title = page.title()
        return f"✅ Navigated to {url} — Page title: '{title}'"
    try:
        return _run_on_pw_thread(_do)
    except Exception as e:
        return f"❌ Failed to navigate to {url}: {e}"


@tool
def click_element(selector: str) -> str:
    """Click an element on the current page using a CSS selector. Input: CSS selector like 'button[type=submit]'"""
    def _do():
        page = _get_page_impl()
        page.wait_for_selector(selector, timeout=8000)
        page.click(selector)
        return f"✅ Clicked element: {selector}"
    try:
        return _run_on_pw_thread(_do)
    except Exception as e:
        return f"❌ Could not click '{selector}': {e}"


@tool
def type_text(input: str) -> str:
    """
    Type text into an input field on the current page.
    Input format: 'selector|||text to type'
    Example: 'input[name=q]|||Python tutorials'
    """
    try:
        selector, text = input.split("|||", 1)
        selector = selector.strip()
        text = text.strip()
    except ValueError:
        return "❌ Input must be in format: 'selector|||text to type'"

    def _do():
        page = _get_page_impl()
        page.wait_for_selector(selector, timeout=8000)
        page.fill(selector, text)
        return f"✅ Typed '{text}' into {selector}"
    try:
        return _run_on_pw_thread(_do)
    except Exception as e:
        return f"❌ Could not type into '{selector}': {e}"


@tool
def get_user_profile(field: str) -> str:
    """Get a field from the user profile. Fields: name, email, phone, address, resume_path"""
    profile = load_profile()
    value = profile.get(field.strip().lower())
    if value:
        return f"User's {field}: {value}"
    return f"❌ Field '{field}' not found. Available: {list(profile.keys())}"


@tool
def get_page_title(dummy: str = "") -> str:
    """Get the title and URL of the current browser page."""
    def _do():
        page = _get_page_impl()
        title = page.title()
        url = page.url
        return f"Current page: '{title}' at {url}"
    try:
        return _run_on_pw_thread(_do)
    except Exception as e:
        return f"❌ Could not get page title: {e}"


# ── Shared DB helpers (sync sqlite3 — safe alongside FastAPI's aiosqlite) ─────

def _read_profile_from_db() -> dict:
    if not DB_PATH.exists():
        return {}
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM users ORDER BY id LIMIT 1").fetchone()
    conn.close()
    if not row:
        return {}
    d = dict(row)
    extra = json.loads(d.pop("extra_fields", None) or "{}")
    d.update(extra)
    return d


def _write_profile_field(field_name: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM users ORDER BY id LIMIT 1").fetchone()
    now = datetime.now(timezone.utc).isoformat()
    key = field_name.strip().lower().replace(" ", "_")

    if row is None:
        core = {f: None for f in CORE_PROFILE_FIELDS}
        extra = {}
        if key in CORE_PROFILE_FIELDS:
            core[key] = value
        else:
            extra[key] = value
        conn.execute(
            """INSERT INTO users (name, email, phone, address, resume_text, extra_fields, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (core["name"], core["email"], core["phone"], core["address"],
             core["resume_text"], json.dumps(extra), now),
        )
    else:
        d = dict(row)
        extra = json.loads(d.get("extra_fields") or "{}")
        if key in CORE_PROFILE_FIELDS:
            d[key] = value
        else:
            extra[key] = value
        conn.execute(
            """UPDATE users SET name=?, email=?, phone=?, address=?,
               resume_text=?, extra_fields=?, updated_at=? WHERE id=?""",
            (d["name"], d["email"], d["phone"], d["address"],
             d["resume_text"], json.dumps(extra), now, d["id"]),
        )
    conn.commit()
    conn.close()


def _save_summary_to_db(url: str | None, title: str | None, summary: dict):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO summaries (source_url, title, summary_text, tags, created_at) VALUES (?, ?, ?, ?, ?)",
        (url, title, json.dumps(summary), json.dumps(summary.get("tags", [])), now),
    )
    conn.commit()
    conn.close()


_groq_client = _GroqClient(api_key=os.getenv("GROQ_API_KEY"))
_LLM_MODEL = "openai/gpt-oss-120b"  # llama-3.3-70b-versatile was deprecated by Groq on 2026-06-17


def _strip_code_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return raw


def _extract_page_text(max_chars: int = 6000) -> str:
    page = _get_page_impl()
    return page.inner_text("body")[:max_chars]


def _llm_summarize(text: str, url: str = "") -> dict:
    prompt = f"""Summarize the following page content{' from ' + url if url else ''}.
Return ONLY valid JSON (no markdown, no code fences) matching this schema:
{{"tldr": "3 sentence summary", "key_points": ["...", "...", "...", "...", "..."], "action_items": ["..."], "tags": ["...", "...", "..."]}}

CONTENT:
{text}
"""
    response = _groq_client.chat.completions.create(
        model=_LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    raw = _strip_code_fence(response.choices[0].message.content)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"tldr": raw, "key_points": [], "action_items": [], "tags": []}


def _format_summary(summary: dict, title: str = "", url: str = "") -> str:
    lines = []
    if title or url:
        lines.append(f"📄 {title or url}")
    lines.append(f"TL;DR: {summary.get('tldr', '')}")
    if summary.get("key_points"):
        lines.append("Key points:")
        lines += [f"  • {p}" for p in summary["key_points"]]
    if summary.get("action_items"):
        lines.append("Action items:")
        lines += [f"  → {a}" for a in summary["action_items"]]
    if summary.get("tags"):
        lines.append(f"Tags: {', '.join(summary['tags'])}")
    return "\n".join(lines)


# ── Module 1 — Intelligent Form Filling ───────────────────────────────────────

@tool
def detect_form_fields(dummy: str = "") -> str:
    """Scan the current page for every fillable field (input, select, textarea)
    and return them with a stable field_id to use with fill_form_field. Always
    call this FIRST before trying to fill anything on a new page."""
    def _do():
        page = _get_page_impl()
        page.evaluate("""
            () => {
                document.querySelectorAll('input, select, textarea').forEach((el, i) => {
                    if (!el.hasAttribute('data-agent-id')) el.setAttribute('data-agent-id', 'f' + i);
                });
            }
        """)
        fields = page.evaluate("""
            () => Array.from(document.querySelectorAll('[data-agent-id]')).map(el => ({
                field_id: el.getAttribute('data-agent-id'),
                tag: el.tagName.toLowerCase(),
                type: el.type || '',
                label: (el.labels && el.labels.length) ? el.labels[0].innerText
                       : (el.placeholder || el.name || el.id || ''),
                current_value: el.value || ''
            }))
        """)
        if not fields:
            return "No fillable fields found on the current page."
        lines = [
            f"- {f['field_id']}: label='{f['label']}' type={f['tag']}/{f['type']} current_value='{f['current_value']}'"
            for f in fields
        ]
        return "Detected fields:\n" + "\n".join(lines)
    try:
        return _run_on_pw_thread(_do)
    except Exception as e:
        return f"❌ Could not detect fields: {e}"


@tool
def get_profile_value(field_name: str) -> str:
    """Look up a value from the user's stored profile — name, email, phone,
    address, resume_text, or any custom field learned before (linkedin_url,
    college, skills, etc). Returns 'MISSING: ...' if not found — when you see
    that, ASK THE USER for the value directly instead of guessing or leaving
    it blank, then call save_profile_field with what they tell you."""
    profile = _read_profile_from_db()
    key = field_name.strip().lower().replace(" ", "_")
    synonyms = {
        "full_name": "name", "fullname": "name",
        "phone_number": "phone", "mobile": "phone", "mobile_number": "phone",
        "linkedin": "linkedin_url",
    }
    key = synonyms.get(key, key)
    value = profile.get(key)
    if value:
        return str(value)
    return f"MISSING: no stored value for '{field_name}'. Ask the user for it, then call save_profile_field to remember it."


@tool
def save_profile_field(input: str) -> str:
    """Save a new piece of profile information so it's remembered for next
    time. Input format: 'field_name|||value', e.g. 'linkedin_url|||https://linkedin.com/in/arjun'.
    Use this whenever the user gives you information about themselves — after
    asking for a missing field, or if they volunteer it unprompted."""
    try:
        field_name, value = input.split("|||", 1)
    except ValueError:
        return "❌ Input must be in format: 'field_name|||value'"
    try:
        _write_profile_field(field_name.strip(), value.strip())
        return f"✅ Saved {field_name.strip()} = '{value.strip()}' to your profile. I'll remember this next time."
    except Exception as e:
        return f"❌ Could not save profile field: {e}"


@tool
def fill_form_field(input: str) -> str:
    """Fill a field detected by detect_form_fields. Input format:
    'field_id|||value', e.g. 'f3|||Arjun Sharma'. Handles text inputs,
    dropdowns (select), and checkboxes/radios automatically."""
    try:
        field_id, value = input.split("|||", 1)
        field_id, value = field_id.strip(), value.strip()
    except ValueError:
        return "❌ Input must be in format: 'field_id|||value'"

    def _do():
        page = _get_page_impl()
        selector = f'[data-agent-id="{field_id}"]'
        el = page.query_selector(selector)
        if not el:
            return f"❌ No field found with field_id '{field_id}'. Run detect_form_fields again."
        tag = el.evaluate("el => el.tagName.toLowerCase()")
        type_attr = el.evaluate("el => el.type || ''")
        if tag == "select":
            el.select_option(label=value)
        elif type_attr in ("checkbox", "radio"):
            (el.check() if value.lower() in ("true", "yes", "1", "checked", "check") else el.uncheck())
        else:
            el.fill(value)
        return f"✅ Filled field {field_id} with '{value}'"
    try:
        return _run_on_pw_thread(_do)
    except Exception as e:
        return f"❌ Could not fill field '{field_id}': {e}"


@tool
def generate_long_text(input: str) -> str:
    """Draft long-form text for a form field (SOP, 'why do you want to join',
    project description) using the user's stored profile + resume as context.
    Input format: 'question_or_field_label|||optional extra context'.
    Example: 'Why do you want this internship?|||applying for a software engineering role'"""
    if "|||" in input:
        prompt_label, extra_context = input.split("|||", 1)
    else:
        prompt_label, extra_context = input, ""

    profile = _read_profile_from_db()
    context_bits = []
    for key in ("name", "resume_text"):
        if profile.get(key):
            context_bits.append(f"{key}: {profile[key]}")
    for k, v in profile.items():
        if k not in ("id", "name", "email", "phone", "address", "resume_text", "updated_at") and v:
            context_bits.append(f"{k}: {v}")
    context_str = "\n".join(context_bits) or "No profile information stored yet."

    try:
        response = _groq_client.chat.completions.create(
            model=_LLM_MODEL,
            messages=[
                {"role": "system", "content": (
                    "You write first-person application answers for forms (SOPs, "
                    "'why this role' essays, project descriptions) using the applicant's "
                    "real background. Be specific and concise (150-250 words unless asked "
                    "otherwise) — avoid generic filler."
                )},
                {"role": "user", "content": f"Applicant background:\n{context_str}\n\nQuestion/field: {prompt_label.strip()}\nExtra context: {extra_context.strip()}"},
            ],
            temperature=0.4,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Could not generate text: {e}"


def _submit_current_form_impl() -> str:
    """NOT an @tool — deliberately unreachable by the LLM."""
    page = _get_page_impl()
    candidates = [
        "button[type=submit]", "input[type=submit]",
        "button:has-text('Submit')", "button:has-text('Apply')", "button:has-text('Send')",
    ]
    for selector in candidates:
        try:
            el = page.query_selector(selector)
            if el:
                el.click()
                return f"✅ Clicked submit button matching: {selector}"
        except Exception:
            continue
    return "❌ Could not find a submit/apply/send button on the current page."


def submit_current_form() -> str:
    return _run_on_pw_thread(_submit_current_form_impl)


# ── Module 3 — Page & Content Summarization ───────────────────────────────────

@tool
def summarize_current_page(dummy: str = "") -> str:
    """Summarize whatever page is currently open in the browser. Returns a
    TL;DR, key points, action items, and tags. Saves the summary to history."""
    def _do():
        page = _get_page_impl()
        return page.url, page.title(), _extract_page_text()
    try:
        url, title, text = _run_on_pw_thread(_do)
        summary = _llm_summarize(text, url)
        _save_summary_to_db(url, title, summary)
        return _format_summary(summary, title, url)
    except Exception as e:
        return f"❌ Could not summarize page: {e}"


@tool
def summarize_url(url: str) -> str:
    """Navigate to a URL and summarize its content. Saves the summary to
    history automatically. Input: a full URL."""
    def _do():
        page = _get_page_impl()
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        return page.title(), _extract_page_text()
    try:
        title, text = _run_on_pw_thread(_do)
        summary = _llm_summarize(text, url)
        _save_summary_to_db(url, title, summary)
        return _format_summary(summary, title, url)
    except Exception as e:
        return f"❌ Could not summarize {url}: {e}"


@tool
def analyze_job_description(url: str = "") -> str:
    """Analyze a job/internship description for required skills, nice-to-haves,
    and what to highlight from the user's own background. Leave url empty to
    use the current page, or pass a URL to navigate there first."""
    def _do():
        page = _get_page_impl()
        if url.strip():
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
        return page.title(), page.url, _extract_page_text()
    try:
        title, current_url, text = _run_on_pw_thread(_do)
        profile = _read_profile_from_db()
        resume = profile.get("resume_text") or "No resume stored."
        prompt = f"""Analyze this job/internship description. Return ONLY valid JSON (no markdown):
{{"required_skills": ["..."], "nice_to_have": ["..."], "highlight_from_my_background": ["..."]}}

APPLICANT BACKGROUND: {resume}

JOB DESCRIPTION:
{text}
"""
        response = _groq_client.chat.completions.create(
            model=_LLM_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.2,
        )
        raw = _strip_code_fence(response.choices[0].message.content)
        try:
            analysis = json.loads(raw)
        except json.JSONDecodeError:
            return f"Job analysis (unstructured):\n{raw}"
        lines = [f"📋 Job analysis for: {title} ({current_url})"]
        lines.append("Required skills: " + ", ".join(analysis.get("required_skills", [])))
        lines.append("Nice to have: " + ", ".join(analysis.get("nice_to_have", [])))
        lines.append("Highlight from your background:")
        lines += [f"  • {h}" for h in analysis.get("highlight_from_my_background", [])]
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Could not analyze job description: {e}"


@tool
def compare_pages(urls: str) -> str:
    """Compare multiple pages (e.g. 3 course pages). Input: comma-separated
    URLs (at least 2). Returns a markdown comparison table."""
    url_list = [u.strip() for u in urls.split(",") if u.strip()]
    if len(url_list) < 2:
        return "❌ Provide at least 2 comma-separated URLs to compare."

    def _do():
        page = _get_page_impl()
        extracted = []
        for u in url_list:
            page.goto(u, timeout=30000, wait_until="domcontentloaded")
            extracted.append({"url": u, "title": page.title(), "text": _extract_page_text(3000)})
        return extracted
    try:
        pages_data = _run_on_pw_thread(_do)
        pages_block = "\n\n".join(
            f"URL: {p['url']}\nTITLE: {p['title']}\nCONTENT: {p['text']}" for p in pages_data
        )
        prompt = f"""Compare these pages. Return ONLY valid JSON (no markdown):
{{"comparison": [{{"aspect": "...", "values": ["value for page 1", "value for page 2", "..."]}}], "recommendation": "..."}}
Pick 4-6 relevant aspects based on what's actually in the content (price, duration, features, prerequisites, etc).

PAGES:
{pages_block}
"""
        response = _groq_client.chat.completions.create(
            model=_LLM_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.2,
        )
        raw = _strip_code_fence(response.choices[0].message.content)
        try:
            comp = json.loads(raw)
        except json.JSONDecodeError:
            return f"Comparison (unstructured):\n{raw}"
        lines = ["📊 Comparison:"]
        lines.append("| Aspect | " + " | ".join(p["url"] for p in pages_data) + " |")
        lines.append("|" + "---|" * (len(pages_data) + 1))
        for row in comp.get("comparison", []):
            lines.append("| " + row.get("aspect", "") + " | " + " | ".join(row.get("values", [])) + " |")
        if comp.get("recommendation"):
            lines.append(f"\nRecommendation: {comp['recommendation']}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Could not compare pages: {e}"


# ── Tool registry — used to build COMMAND-SCOPED agents ───────────────────────
TOOL_REGISTRY = {
    "navigate_to": navigate_to,
    "click_element": click_element,
    "type_text": type_text,
    "get_user_profile": get_user_profile,
    "get_page_title": get_page_title,
    "detect_form_fields": detect_form_fields,
    "get_profile_value": get_profile_value,
    "save_profile_field": save_profile_field,
    "fill_form_field": fill_form_field,
    "generate_long_text": generate_long_text,
    "summarize_current_page": summarize_current_page,
    "summarize_url": summarize_url,
    "analyze_job_description": analyze_job_description,
    "compare_pages": compare_pages,
}

CORE_TOOLS = ["navigate_to", "click_element", "type_text", "get_user_profile", "get_page_title"]
FORM_TOOLS = ["detect_form_fields", "get_profile_value", "save_profile_field",
              "fill_form_field", "generate_long_text"]
SUMMARY_TOOLS = ["summarize_current_page", "summarize_url", "analyze_job_description", "compare_pages"]


def create_agent(temperature: float = 0, tool_names: list[str] | None = None, model: str = "openai/gpt-oss-120b"):
    # Launch browser once upfront — prevents double window
    get_page()

    llm = ChatGroq(
        api_key=os.getenv("GROQ_API_KEY"),
        model=model,
        temperature=temperature
    )

    if tool_names is None:
        tool_names = list(TOOL_REGISTRY.keys())
    tools = [TOOL_REGISTRY[name] for name in tool_names]

    # Known langchain-groq issue: create_react_agent's default tool binding
    # can leave tool_choice effectively "required" — so on any turn where
    # the model would naturally just reply in plain text (no tool needed),
    # Groq's API rejects that valid response and the model degrades into
    # malformed `<function=...>` pseudo-JSON trying to comply anyway.
    # Explicitly binding with tool_choice="auto" makes tool use OPTIONAL
    # per-turn, which is what actually stops this failure mode.
    llm_with_tools = llm.bind_tools(tools, tool_choice="auto")

    agent = create_react_agent(
        llm_with_tools,
        tools,
        prompt=(
            "You are an AI browser agent. Control the browser to complete tasks. "
            "Always navigate to a page before clicking or typing. Confirm each action. "
            "Call exactly ONE tool at a time — wait for each result before the next action.\n\n"
            "FORM FILLING: call detect_form_fields first. Match fields by label, not "
            "position — never fill a field whose type obviously mismatches the data "
            "(e.g. name into a Password field). Use get_profile_value to check known "
            "data; if MISSING, ask the user instead of guessing, then save_profile_field "
            "once they answer. Use generate_long_text for SOP/essay-style fields. "
            "NEVER submit/apply/send — no such tool exists on purpose; just report what "
            "was filled and what's missing.\n\n"
            "SUMMARIZATION: summarize_current_page for 'summarize this', summarize_url "
            "for a link, analyze_job_description for postings, compare_pages to compare URLs. "
            "If a navigation or summarization tool fails with a browser/page error, retry the "
            "EXACT SAME URL at most once — do not try substituting a different URL, since a "
            "closed-browser error is not specific to the URL you asked for."
        )
    )
    return agent


# ── Run agent with retry logic (used by CLI test/interactive modes) ───────────

def run_agent(agent, messages: list, task: str, max_retries: int = 3) -> tuple[str, list]:
    """Run one task with retry logic for tool call failures."""
    for attempt in range(1, max_retries + 1):
        try:
            msgs = list(messages)
            msgs.append(HumanMessage(content=task))
            result = agent.invoke({"messages": msgs})
            reply = result["messages"][-1].content
            messages.append(HumanMessage(content=task))
            messages.append(AIMessage(content=reply))
            return reply, messages
        except Exception as e:
            error_str = str(e)
            if "tool_use_failed" in error_str or "Failed to call a function" in error_str:
                if attempt < max_retries:
                    print(f"  ⚠️  Tool call format error, retrying ({attempt}/{max_retries})...")
                    time.sleep(2)
                    continue
            raise e
    raise RuntimeError(f"Failed after {max_retries} attempts")


TEST_TASKS = [
    "Go to https://github.com/trending and tell me the page title",
    "What is my name and email from my profile?",
    "Go to https://www.python.org and tell me the page title",
]


def run_tests(agent):
    print("\n" + "=" * 60)
    print("  Testing Agent with 3 Tasks")
    print("=" * 60)

    for i, task in enumerate(TEST_TASKS, 1):
        print(f"\n📋 Task {i}: {task}")
        print("-" * 50)
        try:
            reply, _ = run_agent(agent, [], task)
            print(f"\n🤖 Agent: {reply}")
        except Exception as e:
            print(f"❌ Error after retries: {e}")

    print("\n" + "=" * 60)
    print("✅ Test tasks complete!")
    print("=" * 60)


def interactive_mode(agent):
    print("\n" + "=" * 60)
    print("  Interactive Mode — Give the agent tasks!")
    print("  Agent remembers the conversation.")
    print("  (type 'quit' to exit)")
    print("=" * 60)

    messages = []

    while True:
        task = input("\n> You: ").strip()
        if task.lower() in ("quit", "exit", "q"):
            close_browser()
            print("Bye!")
            break
        if not task:
            continue
        try:
            reply, messages = run_agent(agent, messages, task)
            print(f"\n🤖 Agent: {reply}")
        except Exception as e:
            print(f"❌ Error: {e}")
            messages = []
            print("  (Memory reset due to error)")


def main():
    print("=" * 60)
    print("  Script 5 — LangChain Browser Agent")
    print("=" * 60)

    if not os.path.exists(PROFILE_FILE):
        save_profile(load_profile())
        print(f"✅ Created {PROFILE_FILE}")

    agent = create_agent()
    run_tests(agent)
    interactive_mode(agent)


if __name__ == "__main__":
    main()