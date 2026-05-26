from __future__ import annotations

from fastapi import APIRouter, Depends

from app.models.schemas import (
    TranscriptRequest,
    ExtractTasksRequest,
    ExtractTasksResponse,
    ResolveAssigneesRequest,
    ResolveAssigneesResponse,
    GroupByTopicRequest,
    GroupByTopicResponse,
    PushToNotionRequest,
    PushToNotionResponse,
    ProcessTranscriptResponse,
    BonusTasksResponse,
    BonusChatRequest,
    BonusChatResponse,
)
from app.services.data_store import DataStore, get_data_store
from app.services.llm_service import LLMService
from app.services.notion_service import NotionService
from app.services.pipeline import TranscriptPipeline
from app.services.task_repository import TaskRepository
from app.services.chatbot_service import GroundedChatbotService

router = APIRouter()


def get_pipeline(data_store: DataStore = Depends(get_data_store)) -> TranscriptPipeline:
    return TranscriptPipeline(data_store=data_store, llm=LLMService(), notion=NotionService())


@router.get("/health")
def health(data_store: DataStore = Depends(get_data_store)) -> dict[str, object]:
    return {"status": "ok", "employees_loaded": len(data_store.organization), "projects_loaded": len(data_store.projects)}


@router.post("/process-transcript", response_model=ProcessTranscriptResponse)
def process_transcript(request: TranscriptRequest, pipeline: TranscriptPipeline = Depends(get_pipeline)):
    return pipeline.process(request)


@router.post("/extract-tasks", response_model=ExtractTasksResponse)
def extract_tasks(request: ExtractTasksRequest, pipeline: TranscriptPipeline = Depends(get_pipeline)):
    transcript_request = TranscriptRequest(transcript_id="debug-extract-only", transcript=request.transcript, metadata=request.metadata)
    return pipeline.extract_tasks(transcript_request)


@router.post("/resolve-assignees", response_model=ResolveAssigneesResponse)
def resolve_assignees(request: ResolveAssigneesRequest, pipeline: TranscriptPipeline = Depends(get_pipeline)):
    transcript_request = TranscriptRequest(transcript_id="debug-resolve-only", transcript="not-required", metadata=request.metadata)
    return pipeline.resolve_assignees_and_context(request.tasks, transcript_request)


@router.post("/group-by-topic", response_model=GroupByTopicResponse)
def group_by_topic(request: GroupByTopicRequest, pipeline: TranscriptPipeline = Depends(get_pipeline)):
    return pipeline.group_by_topic(request.tasks)


@router.post("/push-to-notion", response_model=PushToNotionResponse)
def push_to_notion(request: PushToNotionRequest, pipeline: TranscriptPipeline = Depends(get_pipeline)):
    return pipeline.push_to_notion(request)


@router.get("/bonus/tasks", response_model=BonusTasksResponse)
def bonus_tasks(data_store: DataStore = Depends(get_data_store)):
    repository = TaskRepository(data_store)
    return BonusTasksResponse(tasks=repository.list_open_tasks())


@router.post("/bonus/chat", response_model=BonusChatResponse)
def bonus_chat(request: BonusChatRequest, data_store: DataStore = Depends(get_data_store)):
    chatbot = GroundedChatbotService(data_store)
    return chatbot.answer(request.question)
