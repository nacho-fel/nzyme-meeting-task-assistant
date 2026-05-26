from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from app.models.schemas import BonusChatResponse, BonusTask
from app.services.data_store import DataStore
from app.services.task_repository import TaskRepository


class GroundedChatbotService:
    """A guarded, read-only chatbot for the bonus dashboard.

    It intentionally uses deterministic retrieval and templated answers instead
    of free-form generation. This prevents hallucinated employees, projects or
    tasks and keeps answers inside the assessment's allowed knowledge base.
    """

    REFUSAL = (
        "I can only answer questions grounded in organization.csv, projects.csv "
        "and the tasks currently stored in Notion for this pipeline."
    )

    def __init__(self, data_store: DataStore, repository: TaskRepository | None = None) -> None:
        self.data_store = data_store
        self.repository = repository or TaskRepository(data_store)

    def answer(self, question: str) -> BonusChatResponse:
        q = question.strip()
        q_lower = q.lower()
        tasks = self.repository.list_open_tasks()

        if not q:
            return BonusChatResponse(answer="Ask me about team workload, tasks by member, projects, deadlines, or stale tasks.", tasks=[])

        if self._is_out_of_scope(q_lower):
            return BonusChatResponse(answer=self.REFUSAL, tasks=[])

        employee = self._match_employee(q_lower)
        project_id = self._match_project(q_lower)

        # Entity-specific questions must take precedence over broad stale/deadline intents.
        # Otherwise phrases such as "on his plate" contain the substring "late" and
        # are incorrectly routed to the stale-task branch.
        if employee:
            filtered = [task for task in tasks if task.assignee and task.assignee.employee_id == employee.employee_id]
            if "deadline" in q_lower or "due" in q_lower or "when" in q_lower:
                filtered = sorted([task for task in filtered if task.deadline], key=lambda t: t.deadline)
                return self._task_answer(filtered, f"task with a deadline for {employee.name}")
            return self._task_answer(filtered, f"open task for {employee.name}")

        if project_id:
            filtered = [task for task in tasks if task.project_id == project_id]
            project_name = self.data_store.projects[project_id].name
            if "deadline" in q_lower or "due" in q_lower or "when" in q_lower:
                filtered = sorted([task for task in filtered if task.deadline], key=lambda t: t.deadline)
                return self._task_answer(filtered, f"task with a deadline for project {project_name}")
            return self._task_answer(filtered, f"open task for project {project_name}")

        if "stale" in q_lower or "overdue" in q_lower or re.search(r"\blate\b", q_lower):
            today = date.today()
            stale = [task for task in tasks if task.deadline and task.deadline < today]
            return self._task_answer(stale, "stale or overdue task")

        if "deadline" in q_lower or "due" in q_lower:
            filtered = tasks
            if employee:
                filtered = [task for task in filtered if task.assignee and task.assignee.employee_id == employee.employee_id]
            if project_id:
                filtered = [task for task in filtered if task.project_id == project_id]
            filtered = sorted([task for task in filtered if task.deadline], key=lambda t: t.deadline)
            return self._task_answer(filtered, "task with a deadline")


        if any(token in q_lower for token in ["workload", "plate", "per member", "by member", "everyone", "team"]):
            grouped: dict[str, list[BonusTask]] = defaultdict(list)
            for task in tasks:
                name = task.assignee.name if task.assignee else "Unresolved"
                grouped[name].append(task)
            if not grouped:
                return BonusChatResponse(answer="I found no open tasks in the current Notion task pages.", tasks=[])
            lines = ["Current workload by member:"]
            for name, member_tasks in sorted(grouped.items(), key=lambda kv: kv[0]):
                lines.append(f"- {name}: {len(member_tasks)} open task(s)")
            return BonusChatResponse(answer="\n".join(lines), tasks=tasks)

        if any(token in q_lower for token in ["list projects", "projects", "active projects"]):
            projects = self.data_store.active_projects()
            lines = ["Active projects in projects.csv:"]
            for project in projects:
                lines.append(f"- {project.project_id}: {project.name} — {project.description}")
            return BonusChatResponse(answer="\n".join(lines), tasks=[])

        if any(token in q_lower for token in ["list people", "employees", "members", "organization"]):
            lines = ["Employees in organization.csv:"]
            for employee in sorted(self.data_store.organization.values(), key=lambda e: e.employee_id):
                lines.append(f"- {employee.employee_id}: {employee.name} — {employee.role or 'Unknown role'}")
            return BonusChatResponse(answer="\n".join(lines), tasks=[])

        return BonusChatResponse(answer=self.REFUSAL, tasks=[])

    def _match_employee(self, q_lower: str):
        for employee in self.data_store.organization.values():
            full = employee.name.lower()
            first = full.split()[0]
            if full in q_lower or re.search(rf"\b{re.escape(first)}\b", q_lower):
                return employee
        return None

    def _match_project(self, q_lower: str) -> str | None:
        for project in self.data_store.projects.values():
            if project.project_id.lower() in q_lower or project.name.lower() in q_lower:
                return project.project_id
        aliases = {
            "atlas": "PRJ001",
            "pricing": "PRJ007",
            "north star": "PRJ007",
            "lighthouse": "PRJ005",
            "ranking": "PRJ006",
            "drift": "PRJ008",
            "latency": "PRJ008",
        }
        for alias, project_id in aliases.items():
            if alias in q_lower and project_id in self.data_store.projects:
                return project_id
        return None

    @staticmethod
    def _is_out_of_scope(q_lower: str) -> bool:
        forbidden = [
            "weather", "stock", "share price", "salary", "personal", "politics", "news",
            "write code", "generate", "who will win", "internet", "web", "linkedin",
        ]
        return any(token in q_lower for token in forbidden)

    def _task_answer(self, tasks: list[BonusTask], label: str) -> BonusChatResponse:
        if not tasks:
            return BonusChatResponse(answer=f"I found no {label}s in the current Notion task pages.", tasks=[])
        plural = "s" if len(tasks) != 1 else ""
        lines = [f"I found {len(tasks)} {label}{plural}:"]
        for task in tasks[:20]:
            assignee = task.assignee.name if task.assignee else "Unresolved"
            deadline = task.deadline.isoformat() if task.deadline else "No deadline"
            project = task.project_id or "No project"
            lines.append(f"- {task.description} — {assignee} — {deadline} — {project}")
        return BonusChatResponse(answer="\n".join(lines), tasks=tasks)
