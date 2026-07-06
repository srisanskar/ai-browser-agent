"""
test_intent_parser.py — Assignment 6: 5 pytest tests for the intent parser
=============================================================================
Tests parse_intent() from script4_intent_parser.py, one test per action type
in its schema: navigate, fill_form, email, summarize, click.

Why mock the Groq call instead of hitting the real API:
  - Deterministic: the LLM can phrase JSON slightly differently between
    runs; a mock guarantees the exact response we're testing against.
  - Fast: no network round-trip, tests run in milliseconds.
  - Free: doesn't burn your Groq token quota (which we've already hit
    once this project — see Week 5 rate-limit debugging).
  - Isolated: a test failure here means parse_intent's OWN logic broke
    (JSON parsing, code-fence stripping), not "the LLM had an off day."

How to run:
    pytest test_intent_parser.py -v

Setup: put this file in your project root, next to script4_intent_parser.py
(or adjust the sys.path insert below if you keep it in a tests/ folder).
Requires: pip install pytest  (you likely already have it via other deps)
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Make sure script4_intent_parser.py (project root) is importable regardless
# of where pytest is invoked from.
sys.path.insert(0, str(Path(__file__).parent))

import script4_intent_parser as intent_parser  # noqa: E402


def _mock_groq_response(json_payload: dict):
    """Builds a fake Groq API response object shaped like the real SDK's,
    so client.chat.completions.create(...) can be patched to return it."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(json_payload)
    return mock_response


def _run(coro):
    """parse_intent() is async; run it synchronously for a plain pytest test
    (avoids needing the pytest-asyncio plugin as an extra dependency)."""
    return asyncio.run(coro)


# ── 1. navigate ──────────────────────────────────────────────────────────────

def test_parse_intent_navigate():
    fake_action = {
        "action": "navigate",
        "target_url": "https://github.com/trending",
        "data": {},
        "steps": ["Open browser", "Navigate to https://github.com/trending"],
    }
    with patch.object(
        intent_parser.client.chat.completions, "create",
        return_value=_mock_groq_response(fake_action),
    ):
        result = _run(intent_parser.parse_intent("Go to GitHub trending page"))

    assert result["action"] == "navigate"
    assert result["target_url"] == "https://github.com/trending"
    assert isinstance(result["steps"], list) and len(result["steps"]) > 0


# ── 2. fill_form ─────────────────────────────────────────────────────────────

def test_parse_intent_fill_form():
    fake_action = {
        "action": "fill_form",
        "target_url": None,
        "data": {"name": "Arjun", "email": "arjun@example.com"},
        "steps": ["Locate name field", "Fill name with Arjun", "Submit"],
    }
    with patch.object(
        intent_parser.client.chat.completions, "create",
        return_value=_mock_groq_response(fake_action),
    ):
        result = _run(intent_parser.parse_intent(
            "Fill the contact form with my name Arjun and email arjun@example.com"
        ))

    assert result["action"] == "fill_form"
    assert result["data"]["name"] == "Arjun"
    assert result["data"]["email"] == "arjun@example.com"


# ── 3. email ─────────────────────────────────────────────────────────────────

def test_parse_intent_email():
    fake_action = {
        "action": "email",
        "target_url": None,
        "data": {"to": "boss", "subject": "Summary", "body": "summary content"},
        "steps": ["Open email client", "Set recipient", "Send email"],
    }
    with patch.object(
        intent_parser.client.chat.completions, "create",
        return_value=_mock_groq_response(fake_action),
    ):
        result = _run(intent_parser.parse_intent("Email this summary to my boss"))

    assert result["action"] == "email"
    assert result["data"]["to"] == "boss"
    assert "subject" in result["data"]


# ── 4. summarize ─────────────────────────────────────────────────────────────

def test_parse_intent_summarize():
    fake_action = {
        "action": "summarize",
        "target_url": None,
        "data": {},
        "steps": ["Extract all text from current page", "Send text to LLM", "Return summary"],
    }
    with patch.object(
        intent_parser.client.chat.completions, "create",
        return_value=_mock_groq_response(fake_action),
    ):
        result = _run(intent_parser.parse_intent("Summarize the current page"))

    assert result["action"] == "summarize"
    assert result["data"] == {}
    assert len(result["steps"]) >= 1


# ── 5. click ─────────────────────────────────────────────────────────────────

def test_parse_intent_click():
    fake_action = {
        "action": "click",
        "target_url": None,
        "data": {"element": "login button"},
        "steps": ["Find login button on page", "Click it", "Wait for response"],
    }
    with patch.object(
        intent_parser.client.chat.completions, "create",
        return_value=_mock_groq_response(fake_action),
    ):
        result = _run(intent_parser.parse_intent("Click the login button"))

    assert result["action"] == "click"
    assert result["data"]["element"] == "login button"


# ── Bonus: malformed JSON handling ───────────────────────────────────────────
# Not one of the 5 required action types, but worth having: confirms
# parse_intent's own error path (invalid JSON from the LLM) behaves as
# designed instead of crashing the caller.

def test_parse_intent_handles_invalid_json():
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "this is not valid JSON at all"

    with patch.object(
        intent_parser.client.chat.completions, "create",
        return_value=mock_response,
    ):
        result = _run(intent_parser.parse_intent("some ambiguous command"))

    assert result["action"] == "error"
    assert "raw_response" in result
