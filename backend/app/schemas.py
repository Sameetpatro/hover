from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProjectOut(BaseModel):
    id: str
    name: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    name: str = "Untitled Project"


class JobOut(BaseModel):
    id: str
    project_id: str
    status: str
    stage: str
    progress: float
    error: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompleteUploadIn(BaseModel):
    upload_id: str | None = None


class ArchitectureOut(BaseModel):
    id: str
    version: int
    summary: str
    data: dict[str, Any]
    created_at: datetime
