from pathlib import Path
import json

from app.models.schemas import TranscriptRequest
from app.services.data_store import DataStore
from app.services.llm_service import LLMService
from app.services.notion_service import NotionService
from app.services.pipeline import TranscriptPipeline

ROOT = Path(__file__).resolve().parents[1]


def _pipeline() -> TranscriptPipeline:
    return TranscriptPipeline(DataStore(ROOT / "data"), LLMService(), NotionService())


def _request(transcript_id: str) -> TranscriptRequest:
    meta = next(item for item in json.loads((ROOT / "data" / "metadata.json").read_text(encoding="utf-8"))["transcripts"] if item["transcript_id"] == transcript_id)
    return TranscriptRequest(
        transcript_id=transcript_id,
        transcript=(ROOT / "data" / meta["file"]).read_text(encoding="utf-8"),
        metadata={"meeting_title": meta["meeting_title"], "date": meta["date"], "participants": meta["participants"]},
    )


def test_transcript_001_complete_and_clean():
    response = _pipeline().process(_request("transcript_001"))
    tasks = [task for group in response.topics for task in group.tasks]
    descriptions = [task.description for task in tasks]
    assert len(tasks) == 11
    assert all(task.assignee is not None for task in tasks)
    assert "share your screen" not in " ".join(descriptions).lower()
    assert any(task.assignee.employee_id == "EMP006" and task.deadline.isoformat() == "2025-06-13" for task in tasks if task.assignee)
    assert any(task.assignee.employee_id == "EMP008" and task.deadline.isoformat() == "2025-06-24" for task in tasks if task.assignee and task.deadline)


def test_transcript_002_complete_and_clean():
    response = _pipeline().process(_request("transcript_002"))
    tasks = [task for group in response.topics for task in group.tasks]
    descriptions = " ".join(task.description for task in tasks).lower()
    assert len(tasks) == 12
    assert all(task.assignee is not None for task in tasks)
    assert "share your screen" not in descriptions
    assert "skipping the compass" not in descriptions
    assert any(task.assignee.employee_id == "EMP004" and task.deadline.isoformat() == "2025-06-12" for task in tasks if task.assignee and task.deadline)
    assert any(task.assignee.employee_id == "EMP014" and task.project_id == "PRJ005" for task in tasks if task.assignee)
