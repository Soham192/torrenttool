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


class SearchQuery(BaseModel):
    query: str
    category: str = "all"
    min_seeders: int = 1
    max_results: int = 20


class SearchResult(BaseModel):
    title: str
    download_url: str
    size_bytes: int = Field(default=0, ge=0)
    seeders: int = Field(default=0, ge=0)
    indexer: str = "qBitPlugin"
    info_hash: Optional[str] = None
