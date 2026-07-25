from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Position(BaseModel):
    x: float = 0
    y: float = 0


class Node(BaseModel):
    id: str = Field(default_factory=lambda: f"node-{uuid4().hex[:8]}")
    type: str
    name: str
    position: Position = Field(default_factory=Position)
    config: dict[str, Any] = Field(default_factory=dict)


class Edge(BaseModel):
    id: str = Field(default_factory=lambda: f"edge-{uuid4().hex[:8]}")
    source: str
    target: str
    source_handle: str = "default"
    target_handle: str = "input"


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()


class Workflow(WorkflowCreate):
    id: str = Field(default_factory=lambda: f"wf-{uuid4().hex[:10]}")
    version: int = 1
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class RunRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    session_id: str = "default"


class RunEvent(BaseModel):
    node_id: str
    node_name: str
    status: Literal["success", "error"]
    output: Any = None
    duration_ms: int = 0
    timestamp: str = Field(default_factory=utc_now)


class RunResult(BaseModel):
    id: str = Field(default_factory=lambda: f"run-{uuid4().hex[:10]}")
    workflow_id: str
    status: Literal["success", "error"]
    input: dict[str, Any]
    output: Any = None
    events: list[RunEvent] = Field(default_factory=list)
    error: str | None = None
    started_at: str = Field(default_factory=utc_now)
    finished_at: str = Field(default_factory=utc_now)
