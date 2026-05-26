from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, field_validator


class Metadata(BaseModel):
    meeting_title: str = Field(..., min_length=1)
    date: date
    participants: list[str] = Field(..., min_length=1)

    @field_validator("participants")
    @classmethod
    def uppercase_participant_ids(cls, value: list[str]) -> list[str]:
        return [participant.strip().upper() for participant in value]


class TranscriptRequest(BaseModel):
    transcript_id: str = Field(..., min_length=1)
    transcript: str = Field(..., min_length=1)
    metadata: Metadata


class Employee(BaseModel):
    employee_id: str
    name: str
    email: str | None = None
    role: str | None = None
    department: str | None = None
    manager_id: str | None = None


class Project(BaseModel):
    project_id: str
    name: str
    description: str
    status: str
    members: list[str]


class RawTask(BaseModel):
    description: str = Field(..., min_length=3)
    raw_assignee: str | None = None
    raw_deadline: str | None = None
    project_hint: str | None = None
    topic_hint: str | None = None
    evidence: str | None = None


class Assignee(BaseModel):
    employee_id: str
    name: str


class ResolutionStatus(str, Enum):
    resolved = "resolved"
    unresolved = "unresolved"
    ambiguous = "ambiguous"


class Task(BaseModel):
    description: str
    assignee: Assignee | None = None
    deadline: date | None = None
    project_id: str | None = None

    # Internal audit fields, excluded from the public JSON response.
    raw_assignee: str | None = Field(default=None, exclude=True)
    raw_deadline: str | None = Field(default=None, exclude=True)
    project_hint: str | None = Field(default=None, exclude=True)
    topic_hint: str | None = Field(default=None, exclude=True)
    evidence: str | None = Field(default=None, exclude=True)
    resolution_status: ResolutionStatus | None = Field(default=None, exclude=True)
    resolution_reason: str | None = Field(default=None, exclude=True)


class TopicGroup(BaseModel):
    topic: str
    tasks: list[Task]


class ProcessTranscriptResponse(BaseModel):
    transcript_id: str
    topics: list[TopicGroup]
    notion_page_url: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ExtractTasksRequest(BaseModel):
    transcript: str = Field(..., min_length=1)
    metadata: Metadata


class ExtractTasksResponse(BaseModel):
    tasks: list[RawTask]


class ResolveAssigneesRequest(BaseModel):
    tasks: list[RawTask]
    metadata: Metadata


class ResolveAssigneesResponse(BaseModel):
    tasks: list[Task]
    warnings: list[str] = Field(default_factory=list)


class GroupByTopicRequest(BaseModel):
    tasks: list[Task]
    metadata: Metadata | None = None


class GroupByTopicResponse(BaseModel):
    topics: list[TopicGroup]


class PushToNotionRequest(BaseModel):
    transcript_id: str
    metadata: Metadata
    topics: list[TopicGroup]


class PushToNotionResponse(BaseModel):
    notion_page_url: str | None = None
    dry_run: bool = False
    warnings: list[str] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    detail: str | list[dict[str, Any]]


class BonusTask(BaseModel):
    description: str
    assignee: Assignee | None = None
    deadline: date | None = None
    project_id: str | None = None
    project_name: str | None = None
    topic: str
    transcript_title: str | None = None
    notion_page_url: str | None = None
    status: str = "open"


class BonusTasksResponse(BaseModel):
    tasks: list[BonusTask]


class BonusChatRequest(BaseModel):
    question: str = Field(..., min_length=1)


class BonusChatResponse(BaseModel):
    answer: str
    tasks: list[BonusTask] = Field(default_factory=list)
