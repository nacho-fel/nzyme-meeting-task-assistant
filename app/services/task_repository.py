from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from app.core.config import get_settings
from app.models.schemas import Assignee, BonusTask
from app.services.data_store import DataStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedTaskLine:
    description: str
    assignee_name: str | None
    deadline: date | None
    project_id: str | None
    topic: str
    transcript_title: str | None = None
    source_url: str | None = None


class TaskRepository:
    """Read-only task repository for the bonus dashboard/chatbot.

    Source priority:
      1. Real Notion transcript pages when NOTION_DRY_RUN=false and Notion
         credentials are configured.
      2. Local response_*.json files only when Notion is not configured or dry-run
         mode is enabled.

    This avoids the previous confusing behaviour where the dashboard silently fell
    back to old dry-run JSON outputs even when the app was meant to be reading
    from Notion. In live Notion mode, if Notion returns no readable tasks, the
    repository returns an empty list instead of mixing in stale fallback data.
    """

    def __init__(self, data_store: DataStore) -> None:
        self.settings = get_settings()
        self.data_store = data_store

    def list_open_tasks(self) -> list[BonusTask]:
        notion_enabled = (
            not self.settings.notion_dry_run
            and bool(self.settings.notion_token)
            and bool(self.settings.notion_parent_page_id)
        )

        if notion_enabled:
            try:
                tasks = self._read_tasks_from_notion()
                tasks = self._deduplicate(tasks)
                logger.info("Read %s open task(s) from Notion.", len(tasks))
                return tasks
            except Exception as exc:
                logger.exception("Could not read tasks from Notion: %s", exc)

                # Safe default for production-like Notion mode: do not silently
                # display old local dry-run outputs as if they came from Notion.
                # Set ALLOW_LOCAL_TASK_FALLBACK=true only for demos.
                if os.getenv("ALLOW_LOCAL_TASK_FALLBACK", "false").lower() in {"1", "true", "yes"}:
                    logger.warning("ALLOW_LOCAL_TASK_FALLBACK=true; falling back to local JSON outputs.")
                    return self._read_tasks_from_local_outputs()
                return []

        return self._read_tasks_from_local_outputs()

    # ---------------------------------------------------------------------
    # Notion reader
    # ---------------------------------------------------------------------

    def _read_tasks_from_notion(self) -> list[BonusTask]:
        from notion_client import Client

        notion = Client(auth=self.settings.notion_token)
        parent_page_id = str(self.settings.notion_parent_page_id)
        child_pages = self._list_child_pages(notion, parent_page_id)

        tasks: list[BonusTask] = []
        for page in child_pages:
            page_id = page["id"]
            title = self._page_title(page) or "Notion transcript page"
            page_url = page.get("url") or self._page_url(notion, page_id)

            blocks = self._list_blocks_recursive(notion, page_id)
            current_topic = "Ungrouped"

            for block in blocks:
                block_type = block.get("type")
                if not block_type:
                    continue

                if block_type in {"heading_1", "heading_2", "heading_3"}:
                    current_topic = self._rich_text_plain(block.get(block_type, {}).get("rich_text", [])) or current_topic
                    continue

                line = self._block_text(block)
                if not line:
                    continue

                parsed = self._parse_task_line(line, current_topic, title, page_url)
                if parsed:
                    tasks.append(self._enrich_task(parsed))

        return tasks

    def _list_child_pages(self, notion: Any, parent_page_id: str) -> list[dict[str, Any]]:
        """Return direct child pages under the configured parent page.

        Notion returns child pages as blocks of type "child_page". The block
        object does not always include the final page URL, so we retrieve that
        later through pages.retrieve().
        """
        pages: list[dict[str, Any]] = []
        for child in self._paginate_blocks(notion, parent_page_id):
            if child.get("type") == "child_page":
                page_id = child["id"]
                page = {"id": page_id, "child_page": child.get("child_page", {})}
                try:
                    page.update(notion.pages.retrieve(page_id=page_id))
                except Exception:
                    # Keep the block-level page if retrieve fails; we can still
                    # attempt to read its children.
                    pass
                pages.append(page)
        return pages

    def _list_blocks_recursive(self, notion: Any, block_id: str) -> list[dict[str, Any]]:
        """Read a page's block tree recursively.

        This makes the repository tolerant to Notion pages where task bullets are
        nested inside toggles, lists or other containers.
        """
        out: list[dict[str, Any]] = []
        stack = list(self._paginate_blocks(notion, block_id))

        while stack:
            block = stack.pop(0)
            out.append(block)
            if block.get("has_children"):
                stack[0:0] = list(self._paginate_blocks(notion, block["id"]))

        return out

    @staticmethod
    def _paginate_blocks(notion: Any, block_id: str) -> Iterable[dict[str, Any]]:
        cursor: str | None = None
        while True:
            response = notion.blocks.children.list(block_id=block_id, page_size=100, start_cursor=cursor)
            for result in response.get("results", []):
                yield result
            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")

    @staticmethod
    def _page_title(page: dict[str, Any]) -> str | None:
        child_title = page.get("child_page", {}).get("title")
        if child_title:
            return child_title

        props = page.get("properties", {})
        for value in props.values():
            if value.get("type") == "title":
                text = "".join(part.get("plain_text", "") for part in value.get("title", []))
                return text.strip() or None
        return None

    @staticmethod
    def _page_url(notion: Any, page_id: str) -> str | None:
        try:
            return notion.pages.retrieve(page_id=page_id).get("url")
        except Exception:
            return None

    @staticmethod
    def _rich_text_plain(rich_text: list[dict[str, Any]]) -> str:
        return "".join(part.get("plain_text", "") for part in rich_text).strip()

    def _block_text(self, block: dict[str, Any]) -> str:
        block_type = block.get("type")
        if not block_type:
            return ""

        payload = block.get(block_type, {})
        rich_text = payload.get("rich_text")
        if isinstance(rich_text, list):
            return self._rich_text_plain(rich_text)

        # Some Notion blocks, such as child_page, store title differently.
        if block_type == "child_page":
            return payload.get("title", "").strip()

        return ""

    # ---------------------------------------------------------------------
    # Parsing and enrichment
    # ---------------------------------------------------------------------

    def _parse_task_line(
        self,
        line: str,
        topic: str,
        transcript_title: str | None,
        source_url: str | None,
    ) -> ParsedTaskLine | None:
        """Parse task lines written by NotionService.

        Supported formats:
          1. description — assignee — deadline — project
          2. description | Assignee: X | Deadline: YYYY-MM-DD | Project: PRJ007
          3. description  Assignee: X | Deadline: ... | Project: ...

        The parser is intentionally permissive because the Notion block text can
        lose markdown styling when converted to plain text.
        """
        line = self._clean_line(line)
        if not line:
            return None

        parsed = self._parse_em_dash_format(line, topic, transcript_title, source_url)
        if parsed:
            return parsed

        parsed = self._parse_labelled_format(line, topic, transcript_title, source_url)
        if parsed:
            return parsed

        return None

    @staticmethod
    def _clean_line(line: str) -> str:
        line = line.strip()
        # Remove common bullet/check prefixes if they come through as text.
        line = re.sub(r"^\s*[-•*]\s+", "", line)
        line = re.sub(r"^\s*\[[ xX]\]\s+", "", line)
        return re.sub(r"\s+", " ", line).strip()

    def _parse_em_dash_format(
        self,
        line: str,
        topic: str,
        transcript_title: str | None,
        source_url: str | None,
    ) -> ParsedTaskLine | None:
        if " — " not in line:
            return None
        parts = [part.strip() for part in line.split(" — ")]
        if len(parts) < 4:
            return None

        description, assignee_name, deadline_raw, project_raw = parts[0], parts[1], parts[2], parts[3]
        if not description:
            return None

        return ParsedTaskLine(
            description=description,
            assignee_name=self._normalise_assignee_name(assignee_name),
            deadline=self._parse_date(deadline_raw),
            project_id=self._normalise_project_id(project_raw),
            topic=topic,
            transcript_title=transcript_title,
            source_url=source_url,
        )

    def _parse_labelled_format(
        self,
        line: str,
        topic: str,
        transcript_title: str | None,
        source_url: str | None,
    ) -> ParsedTaskLine | None:
        # Split on pipes first, then parse key/value fields.
        pieces = [p.strip() for p in line.split("|")]
        if not pieces:
            return None

        description = pieces[0]
        fields: dict[str, str] = {}

        # Also support "Description Assignee: X Deadline: Y Project: Z".
        labelled_tail = " | ".join(pieces[1:])
        if not labelled_tail and re.search(r"\b(assignee|owner|deadline|due|project)\s*:", line, re.I):
            first_label = re.search(r"\b(assignee|owner|deadline|due|project)\s*:", line, re.I)
            if first_label:
                description = line[: first_label.start()].strip(" -—|")
                labelled_tail = line[first_label.start():]

        for key, value in re.findall(
            r"(assignee|owner|deadline|due|project)\s*:\s*([^|]+?)(?=\s+\b(?:assignee|owner|deadline|due|project)\s*:|$|\|)",
            labelled_tail,
            flags=re.IGNORECASE,
        ):
            fields[key.lower()] = value.strip()

        if not description or not fields:
            return None

        assignee_name = fields.get("assignee") or fields.get("owner")
        deadline_raw = fields.get("deadline") or fields.get("due")
        project_raw = fields.get("project")

        return ParsedTaskLine(
            description=description.strip(" -—|"),
            assignee_name=self._normalise_assignee_name(assignee_name),
            deadline=self._parse_date(deadline_raw),
            project_id=self._normalise_project_id(project_raw),
            topic=topic,
            transcript_title=transcript_title,
            source_url=source_url,
        )

    @staticmethod
    def _normalise_assignee_name(value: Any) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        if value.lower() in {"unresolved", "none", "null", "", "no assignee"}:
            return None
        return value

    @staticmethod
    def _normalise_project_id(value: Any) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        if value.lower() in {"no project", "none", "null", "", "n/a", "na", "—", "-"}:
            return None

        match = re.search(r"\bPRJ\d{3}\b", value, flags=re.IGNORECASE)
        if match:
            return match.group(0).upper()
        return value

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if value in (None, "", "No deadline", "N/A", "n/a", "—", "-"):
            return None
        if isinstance(value, date):
            return value

        raw = str(value).strip()
        if raw.lower() in {"no deadline", "none", "null", "n/a", "na", "—", "-"}:
            return None

        match = re.search(r"\d{4}-\d{2}-\d{2}", raw)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(0), "%Y-%m-%d").date()
        except ValueError:
            return None

    def _enrich_task(self, parsed: ParsedTaskLine) -> BonusTask:
        assignee = None
        if parsed.assignee_name:
            normalized = parsed.assignee_name.strip().lower()
            for employee in self.data_store.organization.values():
                if employee.name.lower() == normalized:
                    assignee = Assignee(employee_id=employee.employee_id, name=employee.name)
                    break

        project_id = parsed.project_id
        project_name = None
        if project_id and project_id in self.data_store.projects:
            project_name = self.data_store.projects[project_id].name

        return BonusTask(
            description=parsed.description,
            assignee=assignee,
            deadline=parsed.deadline,
            project_id=project_id,
            project_name=project_name,
            topic=parsed.topic,
            transcript_title=parsed.transcript_title,
            notion_page_url=parsed.source_url,
            status="open",
        )

    # ---------------------------------------------------------------------
    # Local fallback
    # ---------------------------------------------------------------------

    def _read_tasks_from_local_outputs(self) -> list[BonusTask]:
        root = Path.cwd()
        candidates = sorted(root.glob("response_*final*.json")) + sorted((root / "results").glob("response_*final*.json"))

        tasks: list[BonusTask] = []
        for path in candidates:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue

            transcript_title = payload.get("transcript_id", path.stem)
            source_url = payload.get("notion_page_url")

            for group in payload.get("topics", []):
                topic = group.get("topic", "Ungrouped")
                for raw_task in group.get("tasks", []):
                    assignee = raw_task.get("assignee") or {}
                    parsed = ParsedTaskLine(
                        description=raw_task.get("description", ""),
                        assignee_name=assignee.get("name"),
                        deadline=self._parse_date(raw_task.get("deadline")),
                        project_id=raw_task.get("project_id"),
                        topic=topic,
                        transcript_title=transcript_title,
                        source_url=source_url,
                    )
                    tasks.append(self._enrich_task(parsed))

        return self._deduplicate(tasks)

    @staticmethod
    def _deduplicate(tasks: list[BonusTask]) -> list[BonusTask]:
        seen: set[tuple[str, str, str, str, str]] = set()
        unique: list[BonusTask] = []
        for task in tasks:
            key = (
                task.description.strip().lower(),
                task.assignee.employee_id if task.assignee else "",
                task.deadline.isoformat() if task.deadline else "",
                task.project_id or "",
                task.topic.strip().lower(),
            )
            if key not in seen:
                seen.add(key)
                unique.append(task)
        return unique
