from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.models.schemas import Employee, Project, Metadata


class DataStore:
    """Read-only grounding layer for organization.csv, projects.csv and metadata.json."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.organization = self._load_organization(data_dir / "organization.csv")
        self.projects = self._load_projects(data_dir / "projects.csv")
        self.metadata_index = self._load_metadata(data_dir / "metadata.json")

    @staticmethod
    def _load_organization(path: Path) -> dict[str, Employee]:
        if not path.exists():
            raise RuntimeError(f"organization.csv not found at {path}")
        employees: dict[str, Employee] = {}
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                employee = Employee(
                    employee_id=row["employee_id"].strip().upper(),
                    name=row["name"].strip(),
                    email=(row.get("email") or None),
                    role=(row.get("role") or None),
                    department=(row.get("department") or None),
                    manager_id=(row.get("manager_id") or None),
                )
                employees[employee.employee_id] = employee
        return employees

    @staticmethod
    def _load_projects(path: Path) -> dict[str, Project]:
        if not path.exists():
            raise RuntimeError(f"projects.csv not found at {path}")
        projects: dict[str, Project] = {}
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                members = [m.strip().upper() for m in (row.get("members") or "").split(",") if m.strip()]
                project = Project(
                    project_id=row["project_id"].strip().upper(),
                    name=row["name"].strip(),
                    description=(row.get("description") or "").strip(),
                    status=(row.get("status") or "").strip().lower(),
                    members=members,
                )
                projects[project.project_id] = project
        return projects

    @staticmethod
    def _load_metadata(path: Path) -> dict[str, Metadata]:
        if not path.exists():
            return {}
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
        return {
            item["transcript_id"]: Metadata(
                meeting_title=item["meeting_title"],
                date=item["date"],
                participants=item["participants"],
            )
            for item in raw.get("transcripts", [])
        }

    def validate_participants(self, participant_ids: Iterable[str]) -> list[Employee]:
        ids = [pid.strip().upper() for pid in participant_ids]
        missing = [pid for pid in ids if pid not in self.organization]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown participant employee_id(s): {', '.join(missing)}",
            )
        return [self.organization[pid] for pid in ids]

    def get_participant_context(self, participant_ids: Iterable[str]) -> list[dict[str, str | None]]:
        return [employee.model_dump() for employee in self.validate_participants(participant_ids)]

    def active_projects(self) -> list[Project]:
        return [project for project in self.projects.values() if project.status == "active"]


@lru_cache
def get_data_store() -> DataStore:
    return DataStore(get_settings().data_dir)
