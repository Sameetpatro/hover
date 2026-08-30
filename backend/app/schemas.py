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


class FeatureOut(BaseModel):
    id: str
    feature_key: str
    name: str
    description: str
    method: str
    path: str
    entry_file: str
    entry_function: str
    category: str
    color: str


class FeatureFlowOut(BaseModel):
    id: str
    feature_id: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    insights: list[dict[str, Any]]


class ProjectMetaOut(BaseModel):
    tech_stack: list[dict[str, Any]]
    system_design: str
    patterns: list[dict[str, Any]]
    db_schema: list[dict[str, Any]]
    profile: dict[str, Any]


class ChatMessageIn(BaseModel):
    message: str


class ChatMessageOut(BaseModel):
    id: str
    project_id: str
    role: str
    content: str
    sources: list[dict[str, Any]] = []
    created_at: datetime


