from __future__ import annotations

import re
from rapidfuzz import fuzz

from app.models.schemas import (
    TranscriptRequest,
    ExtractTasksResponse,
    ResolveAssigneesResponse,
    GroupByTopicResponse,
    PushToNotionResponse,
    ProcessTranscriptResponse,
    RawTask,
    Task,
    PushToNotionRequest,
)
from app.services.data_store import DataStore
from app.services.llm_service import LLMService
from app.services.assignee_resolver import raw_task_to_grounded_task
from app.services.project_linker import link_project
from app.services.notion_service import NotionService


NOISE_PATTERNS = [
    r"\bshare your screen\b",
    r"\bcome back to (the )?email\b",
    r"\btell elena about skipping\b",
    r"\boffsite\b",
]


def _canonical(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for word in ["the", "a", "an", "to", "and", "with", "for", "of"]:
        text = re.sub(rf"\b{word}\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_noise(raw_task: RawTask) -> bool:
    text = f"{raw_task.description} {raw_task.evidence or ''}".lower()
    return any(re.search(pattern, text) for pattern in NOISE_PATTERNS)


def _deduplicate(tasks: list[RawTask]) -> list[RawTask]:
    kept: list[RawTask] = []
    for task in tasks:
        if _is_noise(task):
            continue
        norm = _canonical(task.description)
        duplicate_idx: int | None = None
        for i, existing in enumerate(kept):
            same_owner = (task.raw_assignee or "").lower() == (existing.raw_assignee or "").lower()
            same_topic = (task.topic_hint or task.project_hint or "").lower() == (existing.topic_hint or existing.project_hint or "").lower()
            score = fuzz.token_set_ratio(norm, _canonical(existing.description))
            if score >= 86 and (same_owner or same_topic):
                duplicate_idx = i
                break
        if duplicate_idx is None:
            kept.append(task)
        else:
            # Keep the richer/final task: prefer one with a deadline and longer description/evidence.
            existing = kept[duplicate_idx]
            task_score = int(bool(task.raw_deadline)) + len(task.description) / 100
            existing_score = int(bool(existing.raw_deadline)) + len(existing.description) / 100
            if task_score > existing_score:
                kept[duplicate_idx] = task
    return kept


class TranscriptPipeline:
    def __init__(self, data_store: DataStore, llm: LLMService, notion: NotionService):
        self.data_store = data_store
        self.llm = llm
        self.notion = notion

    def extract_tasks(self, request: TranscriptRequest) -> ExtractTasksResponse:
        participants = self.data_store.get_participant_context(request.metadata.participants)
        projects = [p.model_dump() for p in self.data_store.active_projects()]
        raw_tasks = self.llm.extract_tasks(request.transcript, request.metadata, participants, projects)
        return ExtractTasksResponse(tasks=_deduplicate(raw_tasks))

    def resolve_assignees_and_context(self, raw_tasks: list[RawTask], request: TranscriptRequest) -> ResolveAssigneesResponse:
        participants = self.data_store.validate_participants(request.metadata.participants)
        warnings: list[str] = []
        grounded: list[Task] = []
        for raw_task in raw_tasks:
            task = raw_task_to_grounded_task(
                raw_task=raw_task,
                participants=participants,
                organization=self.data_store.organization,
                meeting_date=request.metadata.date,
            )
            task = link_project(task, self.data_store.active_projects())
            if task.assignee is None:
                warnings.append(f"Unresolved/ambiguous assignee for task: {task.description}")
            grounded.append(task)
        return ResolveAssigneesResponse(tasks=grounded, warnings=warnings)

    def group_by_topic(self, tasks: list[Task]) -> GroupByTopicResponse:
        return GroupByTopicResponse(topics=self.llm.group_tasks(tasks))

    def push_to_notion(self, payload: PushToNotionRequest) -> PushToNotionResponse:
        url, dry_run, warnings = self.notion.push_transcript_tasks(
            transcript_id=payload.transcript_id,
            metadata=payload.metadata,
            topics=payload.topics,
        )
        return PushToNotionResponse(notion_page_url=url, dry_run=dry_run, warnings=warnings)

    def process(self, request: TranscriptRequest) -> ProcessTranscriptResponse:
        self.data_store.validate_participants(request.metadata.participants)
        raw = self.extract_tasks(request)
        resolved = self.resolve_assignees_and_context(raw.tasks, request)
        grouped = self.group_by_topic(resolved.tasks)
        notion = self.push_to_notion(PushToNotionRequest(transcript_id=request.transcript_id, metadata=request.metadata, topics=grouped.topics))
        return ProcessTranscriptResponse(
            transcript_id=request.transcript_id,
            topics=grouped.topics,
            notion_page_url=notion.notion_page_url,
            warnings=[*resolved.warnings, *notion.warnings],
        )
