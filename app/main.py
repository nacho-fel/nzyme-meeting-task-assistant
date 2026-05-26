from __future__ import annotations

import logging
from fastapi import FastAPI
from app.api.routes import router
from app.core.config import get_settings

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

app = FastAPI(
    title="Nzyme Meeting Transcript Task Distribution API",
    version="1.0.0-final-draft",
    description="Transforms meeting transcripts into grounded tasks grouped by topic and optionally persisted to Notion.",
)
app.include_router(router)
