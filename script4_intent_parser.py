"""
Script 4 — Intent Parser
Converts natural language commands into structured browser actions using Groq API (free).
"""

import json
import asyncio
import os
from groq import Groq
from dotenv import load_dotenv

# Load API key from .env file
load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ── System prompt with few-shot examples ──────────────────────────────────────

SYSTEM_PROMPT = """
You are an intent parser for an AI browser agent.
Your job is to convert natural language commands into structured JSON actions.

SCHEMA:
{
  "action": "fill_form" | "navigate" | "email" | "summarize" | "click",
  "target_url": "full URL or null",
  "data": { ...any fields needed... },
  "steps": ["step 1", "step 2", ...]
}

RULES:
- Always return ONLY valid JSON. No explanation, no markdown, no code blocks.
- Do NOT wrap the JSON in ```json or ``` — return raw JSON only.
- If the command is ambiguous and you NEED more info to act, return this instead:
  { "action": "clarify", "question": "your clarifying question here" }
- Keep steps clear and short.

FEW-SHOT EXAMPLES:

User: "Go to GitHub trending page"
Output:
{
  "action": "navigate",
  "target_url": "https://github.com/trending",
  "data": {},
  "steps": ["Open browser", "Navigate to https://github.com/trending", "Wait for page to load"]
}

User: "Fill the contact form with my name Arjun and email arjun@example.com"
Output:
{
  "action": "fill_form",
  "target_url": null,
  "data": { "name": "Arjun", "email": "arjun@example.com" },
  "steps": ["Locate name field", "Fill name with Arjun", "Locate email field", "Fill email with arjun@example.com", "Take screenshot"]
}

User: "Email this summary to my boss"
Output:
{
  "action": "email",
  "target_url": null,
  "data": { "to": "boss", "subject": "Summary", "body": "summary content" },
  "steps": ["Open email client", "Set recipient to boss", "Paste summary as body", "Send email"]
}

User: "Summarize this page"
Output:
{
  "action": "summarize",
  "target_url": null,
  "data": {},
  "steps": ["Extract all text from current page", "Send text to LLM", "Return summary to user"]
}

User: "Click the login button"
Output:
{
  "action": "click",
  "target_url": null,
  "data": { "element": "login button" },
  "steps": ["Find login button on page", "Click it", "Wait for response"]
}

User: "Apply to this job"
Output:
{
  "action": "clarify",
  "question": "I need a bit more info — what is the URL of the job posting you want to apply to?"
}
"""

# ── 10 test commands ───────────────────────────────────────────────────────────

TEST_COMMANDS = [
    "Go to BBC News website",
    "Fill the signup form with name John and email john@test.com",
    "Email this summary to my boss",
    "Summarize the current page",
    "Click the submit button",
    "Apply to this job",
    "Close all tabs",
    "Search for Python tutorials on Google",
    "Download the PDF from this page",
    "Open YouTube and play lo-fi music",
]

# ── Core function ──────────────────────────────────────────────────────────────

async def parse_intent(user_command: str) -> dict:
    """
    Takes a natural language command and returns a structured action dict.
    """
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",  # free and fast on Groq
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_command}
        ],
        temperature=0.1  # low temperature = more consistent JSON output
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown code blocks if model adds them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "action": "error",
            "raw_response": raw,
            "message": "LLM did not return valid JSON"
        }


# ── Test runner ────────────────────────────────────────────────────────────────

async def run_tests():
    print("=" * 60)
    print("  Intent Parser — Testing 10 Commands")
    print("=" * 60)

    results = []

    for i, command in enumerate(TEST_COMMANDS, 1):
        print(f"\n[{i}/10] Command: \"{command}\"")
        print("-" * 50)

        try:
            result = await parse_intent(command)
            print(json.dumps(result, indent=2))
            results.append({"command": command, "result": result})

        except Exception as e:
            error = {"action": "error", "message": str(e)}
            print(f"❌ Error: {e}")
            results.append({"command": command, "result": error})

    # Save all results to JSON
    with open("intent_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 60)
    print(f"✅ All done! Results saved to intent_results.json")
    print("=" * 60)


# ── Interactive mode ───────────────────────────────────────────────────────────

async def interactive_mode():
    print("\n" + "=" * 60)
    print("  Interactive Mode — Type your own commands")
    print("  (type 'quit' to exit)")
    print("=" * 60)

    while True:
        command = input("\n> You: ").strip()
        if command.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break
        if not command:
            continue

        try:
            result = await parse_intent(command)
            print("\n📋 Parsed Intent:")
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"❌ Error: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

async def main():
    # Run the 10 test commands first
    await run_tests()

    # Then go into interactive mode
    await interactive_mode()


if __name__ == "__main__":
    asyncio.run(main())
