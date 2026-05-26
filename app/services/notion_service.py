from __future__ import annotations

import logging
from app.core.config import get_settings
from app.models.schemas import Metadata, TopicGroup

logger = logging.getLogger(__name__)


class NotionService:
    """Persist grouped tasks to Notion, or return a deterministic dry-run URL.

    The assessment can run fully locally with NOTION_DRY_RUN=true. If credentials
    are supplied, this class creates a simple transcript page. The output schema
    is unchanged either way.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    def push_transcript_tasks(self, transcript_id: str, metadata: Metadata, topics: list[TopicGroup]) -> tuple[str, bool, list[str]]:
        if self.settings.notion_dry_run or not self.settings.notion_token or not self.settings.notion_parent_page_id:
            return f"dry-run://notion/{transcript_id}", True, []

        try:
            from notion_client import Client
            notion = Client(auth=self.settings.notion_token)
            children = []
            for group in topics:
                children.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": group.topic}}]}})
                for task in group.tasks:
                    assignee = task.assignee.name if task.assignee else "Unresolved"
                    deadline = task.deadline.isoformat() if task.deadline else "No deadline"
                    project = task.project_id or "No project"
                    children.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": f"{task.description} — {assignee} — {deadline} — {project}"}}]}})
            page = notion.pages.create(
                parent={"page_id": self.settings.notion_parent_page_id},
                properties={"title": {"title": [{"type": "text", "text": {"content": f"{metadata.meeting_title} — {metadata.date.isoformat()}"}}]}},
                children=children[:100],
            )
            return page.get("url", ""), False, []
        except Exception as exc:  # keep the API usable if Notion errors
            logger.exception("Notion write failed; returning dry-run URL")
            return f"dry-run://notion/{transcript_id}", True, [f"Notion write failed: {exc}"]
