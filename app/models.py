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
