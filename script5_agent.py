"""
Script 5 — LangChain Agent with Playwright Browser Tools
Uses synchronous Playwright + LangGraph ReAct agent.
Includes retry logic for inconsistent tool call formatting.
"""

import json
import os
import time
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, BrowserContext
from langchain.tools import tool
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage

load_dotenv()

# ── Global browser state ───────────────────────────────────────────────────────
_playwright_instance = None
_browser = None
_context: BrowserContext = None
_page: Page = None


def get_page() -> Page:
    global _playwright_instance, _browser, _context, _page
    if _page is None:
        _playwright_instance = sync_playwright().start()
        _browser = _playwright_instance.chromium.launch(headless=False)
        _context = _browser.new_context()
        _page = _context.new_page()
        print("🌐 Browser launched.")
    return _page


def close_browser():
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


# ── User profile ───────────────────────────────────────────────────────────────

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
    page = get_page()
    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        title = page.title()
        return f"✅ Navigated to {url} — Page title: '{title}'"
    except Exception as e:
        return f"❌ Failed to navigate to {url}: {e}"


@tool
def click_element(selector: str) -> str:
    """Click an element on the current page using a CSS selector. Input: CSS selector like 'button[type=submit]'"""
    page = get_page()
    try:
        page.wait_for_selector(selector, timeout=8000)
        page.click(selector)
        return f"✅ Clicked element: {selector}"
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
    page = get_page()
    try:
        page.wait_for_selector(selector, timeout=8000)
        page.fill(selector, text)
        return f"✅ Typed '{text}' into {selector}"
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
    page = get_page()
    try:
        title = page.title()
        url = page.url
        return f"Current page: '{title}' at {url}"
    except Exception as e:
        return f"❌ Could not get page title: {e}"


# ── Agent ──────────────────────────────────────────────────────────────────────

def create_agent():
    # Launch browser once upfront — prevents double window
    get_page()

    llm = ChatGroq(
        api_key=os.getenv("GROQ_API_KEY"),
        model="llama-3.3-70b-versatile",
        temperature=0
    )
    tools = [navigate_to, click_element, type_text, get_user_profile, get_page_title]
    agent = create_react_agent(
        llm,
        tools,
        prompt="You are an AI browser agent. Control the browser to complete tasks. Always navigate to a page before clicking or typing. Confirm each action."
    )
    return agent


# ── Run agent with retry logic ─────────────────────────────────────────────────

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


# ── Test tasks ─────────────────────────────────────────────────────────────────

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


# ── Main ───────────────────────────────────────────────────────────────────────

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
