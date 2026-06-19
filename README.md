# 🤖 AI Browser Agent

A Full-Stack Autonomous Computer-Use Agent built with Python, Playwright, FastAPI, and React.

## 🎯 What This Project Does

This agent can:

- Autonomously browse websites using Playwright
- Think and plan using LLMs (Claude/GPT/Groq)
- Parse natural language commands into structured browser actions
- Remember past executions using Vector Databases
- Self-correct its own mistakes
- Run reliably in the background for hours

## 🛠️ Tech Stack

- **Python** — core language
- **Playwright** — browser automation
- **LangChain + LangGraph** — agent orchestration
- **Groq API** — LLM inference (free tier)
- **FastAPI** — backend API server
- **WebSockets** — real-time communication
- **React** — frontend dashboard
- **ChromaDB** — vector memory

## 📅 Progress

- [x] Week 1 — Environment Setup + Python Async + CSS Selectors
- [x] Week 2 — Playwright Browser Automation (Navigator, Form Filler, Tab Manager)
- [x] Week 3 — LLMs + Prompt Engineering (Intent Parser with 10 command tests)
- [x] Week 4 — Agentic AI + LangChain (Browser agent with tool calling + memory)
- [ ] Week 5 — FastAPI + WebSockets
- [ ] Week 6 — React Dashboard + Memory

## 📁 Project Structure

```
ai-browser-agent/
├── users.json                  # User profile data
├── user_profile.json           # Agent profile store
├── read_users.py               # Week 1 — async user reader
├── selectors.txt               # Week 1 — CSS selectors reference
├── script1_navigator.py        # Week 2 — scrape HN top 5 articles
├── script2_form_filler.py      # Week 2 — auto-fill demoqa form
├── script3_tab_manager.py      # Week 2 — parallel tab management
├── script4_intent_parser.py    # Week 3 — NL → JSON action parser
├── script5_agent.py            # Week 4 — LangChain browser agent
├── articles.json               # Output: scraped articles
├── tab_results.json            # Output: tab manager results
├── intent_results.json         # Output: intent parser results
└── form_filled.png             # Output: form screenshot
```

## 🚀 Setup

```bash
git clone https://github.com/srisanskar/ai-browser-agent.git
cd ai-browser-agent
python -m venv venv
venv\Scripts\activate
pip install playwright langchain langchain-groq langgraph google-genai python-dotenv groq
playwright install chromium
```

Create a `.env` file:
```
GROQ_API_KEY=your_groq_api_key_here
```

## 👤 Author

Sanskar Srivastava — [GitHub](https://github.com/srisanskar)