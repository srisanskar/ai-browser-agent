from pydantic import BaseModel, EmailStr
from typing import Optional, Any


class CommandRequest(BaseModel):
    command: str


class CommandResponse(BaseModel):
    task_id: str
    status: str = "queued"


class StepLog(BaseModel):
    step: int
    message: str
    timestamp: str


class TaskStatusResponse(BaseModel):
    task_id: str
    command: str
    status: str  # queued | running | completed | failed
    steps: list[dict]
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


class UserProfile(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    resume_text: Optional[str] = None
    # Flexible bucket for anything else the agent learns along the way —
    # LinkedIn URL, college, degree, skills, etc. Grows without a schema
    # migration every time a new field type shows up (Module 6).
    extra_fields: dict[str, Any] = {}


class SummaryResponse(BaseModel):
    id: int
    source_url: Optional[str] = None
    title: Optional[str] = None
    summary_text: str
    tags: list[str] = []
    created_at: str
