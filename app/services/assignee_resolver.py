from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from rapidfuzz import fuzz

from app.models.schemas import Employee, RawTask, Task, Assignee, ResolutionStatus
from app.services.deadline_parser import normalise_deadline


@dataclass(frozen=True)
class AssigneeResolution:
    assignee: Assignee | None
    status: ResolutionStatus
    reason: str


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-zA-Z\s-]", "", text).strip().lower()


def _variants(employee: Employee) -> set[str]:
    full = _normalise(employee.name)
    parts = full.split()
    return {full, *(parts[:1]), *(parts[-1:] if parts else [])}


def _match(raw_assignee: str, employees: list[Employee]) -> list[tuple[Employee, int]]:
    raw = _normalise(raw_assignee)
    if not raw:
        return []
    scored: list[tuple[Employee, int]] = []
    for employee in employees:
        best = max(fuzz.ratio(raw, variant) for variant in _variants(employee))
        if raw in _variants(employee):
            best = 100
        if best >= 86:
            scored.append((employee, int(best)))
    return sorted(scored, key=lambda x: x[1], reverse=True)


def resolve_assignee(raw_task: RawTask, participants: list[Employee], organization: dict[str, Employee]) -> AssigneeResolution:
    """Ground an extracted raw assignee against organization.csv.

    Explicit names are matched first against participants and then against the
    full organization so tasks can be assigned to non-participants such as Clara.
    The function returns null rather than inventing an employee on ambiguous input.
    """
    if not raw_task.raw_assignee:
        return AssigneeResolution(None, ResolutionStatus.unresolved, "No explicit assignee in raw task")

    participant_matches = _match(raw_task.raw_assignee, participants)
    if len(participant_matches) == 1:
        employee = participant_matches[0][0]
        return AssigneeResolution(Assignee(employee_id=employee.employee_id, name=employee.name), ResolutionStatus.resolved, "Matched participant")
    if len(participant_matches) > 1 and participant_matches[0][1] == participant_matches[1][1]:
        return AssigneeResolution(None, ResolutionStatus.ambiguous, "Explicit assignee matched multiple participants")

    org_matches = _match(raw_task.raw_assignee, list(organization.values()))
    if len(org_matches) == 1:
        employee = org_matches[0][0]
        return AssigneeResolution(Assignee(employee_id=employee.employee_id, name=employee.name), ResolutionStatus.resolved, "Matched organization")
    if len(org_matches) > 1:
        return AssigneeResolution(None, ResolutionStatus.ambiguous, "Explicit assignee matched multiple employees")

    return AssigneeResolution(None, ResolutionStatus.unresolved, "No organization match")


def raw_task_to_grounded_task(raw_task: RawTask, participants: list[Employee], organization: dict[str, Employee], meeting_date) -> Task:
    resolution = resolve_assignee(raw_task, participants, organization)
    return Task(
        description=raw_task.description.strip(),
        assignee=resolution.assignee,
        deadline=normalise_deadline(raw_task.raw_deadline, meeting_date),
        project_id=None,
        raw_assignee=raw_task.raw_assignee,
        raw_deadline=raw_task.raw_deadline,
        project_hint=raw_task.project_hint,
        topic_hint=raw_task.topic_hint,
        evidence=raw_task.evidence,
        resolution_status=resolution.status,
        resolution_reason=resolution.reason,
    )
