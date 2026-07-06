"""
models.py — Data contracts for the AI Browser Agent
=====================================================
Assignment 6 deliverable: Pydantic models for UserProfile, Task, and
AgentAction. These are the shared "shapes" that every layer of the system
agrees on — frontend, FastAPI backend, and the LangGraph agent all pass
data around in these forms. Weeks 7-10 build directly on these contracts,
so getting them right now saves rework later.

Where each one is used today:
  - UserProfile : matches the SQLite `users` table from Week 5
                  (GET/POST /user/profile)
  - Task        : matches the SQLite `tasks` table + the shape streamed
                  over the Week 5 WebSocket (/ws/{task_id})
  - AgentAction : matches the intent-parser schema from Week 3
                  (parse_intent() -> dict), now formalized as a real model
                  instead of a loose dict so the LLM's structured output
                  can be validated on the way in.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field


# ── UserProfile ────────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    """The agent's 'memory' of who it's acting on behalf of."""

    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    resume_text: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Arjun Sharma",
                "email": "arjun.sharma@example.com",
                "phone": "9876543210",
                "address": "12 MG Road, Kanpur, UP",
                "resume_text": "Experienced software engineer with 5 years...",
            }
        }
    }


# ── AgentAction ────────────────────────────────────────────────────────────

class ActionType(str, Enum):
    """The action vocabulary the Week 3 intent parser outputs.
    Matches the schema given in the Week 3 assignment exactly."""

    FILL_FORM = "fill_form"
    NAVIGATE = "navigate"
    EMAIL = "email"
    SUMMARIZE = "summarize"
    CLICK = "click"


class AgentAction(BaseModel):
    """A single structured action plan produced by parse_intent().

    Example — "apply to this job":
        {
          "action": "fill_form",
          "target_url": "https://jobs.example.com/apply/123",
          "data": {"name": "Arjun Sharma", "email": "arjun.sharma@example.com"},
          "steps": ["navigate to target_url", "fill form fields from data", "submit"]
        }
    """

    action: ActionType
    target_url: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
    steps: list[str] = Field(default_factory=list)

    model_config = {
        "json_schema_extra": {
            "example": {
                "action": "navigate",
                "target_url": "https://github.com/trending",
                "data": {},
                "steps": ["navigate to target_url", "read page title"],
            }
        }
    }


# ── Task ───────────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStep(BaseModel):
    """One entry in a Task's step log — one line of the live activity feed."""

    step: int
    message: str


class Task(BaseModel):
    """The full lifecycle record of one agent run: what was asked, what
    happened step by step, and how it ended up. This is what /status/{id}
    returns and what streams (incrementally) over the WebSocket."""

    task_id: str
    command: str
    status: TaskStatus = TaskStatus.QUEUED
    steps: list[TaskStep] = Field(default_factory=list)
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "json_schema_extra": {
            "example": {
                "task_id": "97282e6d-45ba-4eb8-8e66-026864bb46e2",
                "command": "go to https://github.com/trending and tell me the page title",
                "status": "completed",
                "steps": [
                    {"step": 1, "message": "go to https://github.com/trending and tell me the page title"},
                    {"step": 2, "message": "Agent decided to call tool(s): navigate_to(...)"},
                ],
                "result": {"output": "Agent: The page title is ..."},
                "error": None,
                "created_at": "2026-07-05T09:58:01.215240+00:00",
                "updated_at": "2026-07-05T09:58:10.917461+00:00",
            }
        }
    }
