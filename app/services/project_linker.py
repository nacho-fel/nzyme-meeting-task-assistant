from __future__ import annotations

from rapidfuzz import fuzz, process

from app.models.schemas import Project, Task


ALIASES = {
    "atlas": "PRJ001",
    "atlas mobile": "PRJ001",
    "compass": "PRJ002",
    "compass analytics": "PRJ002",
    "beacon": "PRJ003",
    "harbor": "PRJ004",
    "harbor enterprise": "PRJ004",
    "lighthouse": "PRJ005",
    "lighthouse content": "PRJ005",
    "ranking model": "PRJ006",
    "ranking": "PRJ006",
    "tide": "PRJ006",
    "tide ml ranking": "PRJ006",
    "pricing": "PRJ007",
    "european pricing": "PRJ007",
    "eu pricing": "PRJ007",
    "north star pricing": "PRJ007",
    "vat": "PRJ007",
    "drift": "PRJ008",
    "p99 latency": "PRJ008",
    "reliability": "PRJ008",
}


def _search_text(project: Project) -> str:
    return f"{project.name} {project.description}".lower()


def link_project(task: Task, active_projects: list[Project], min_score: int = 88) -> Task:
    if not active_projects:
        return task
    projects_by_id = {project.project_id: project for project in active_projects}
    candidate_text = " ".join(part for part in [task.project_hint, task.description, task.evidence] if part).lower()

    for alias, project_id in sorted(ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in candidate_text and project_id in projects_by_id:
            task.project_id = project_id
            return task

    for project in active_projects:
        if project.name.lower() in candidate_text:
            task.project_id = project.project_id
            return task

    choices = {project.project_id: _search_text(project) for project in active_projects}
    match = process.extractOne(candidate_text, choices, scorer=fuzz.token_set_ratio)
    if match and match[1] >= min_score:
        task.project_id = match[2]
    return task
