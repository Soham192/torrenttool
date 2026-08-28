from typing import Optional
from pydantic import BaseModel, Field


class TaskStatus(BaseModel):
    task_id: str
    name: str
    progress: float = Field(ge=0.0, le=1.0)
    download_speed: int = Field(ge=0)
    state: str
    eta_seconds: int


class AcquireRequest(BaseModel):
    source_url: str
    display_name: Optional[str] = None
    save_path: Optional[str] = None
