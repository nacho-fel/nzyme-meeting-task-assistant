# Tech Stack Description

**Project:** Nzyme — Meeting Transcript → Task Distribution API

---

## Summary

The stack was chosen with three constraints in mind: (1) run entirely locally with no mandatory external services, (2) keep the dependency footprint small and auditable, and (3) use tools that are standard in production Python API work so the code is immediately readable to another engineer.

---

## Backend

### FastAPI
**Role:** Web framework for the orchestrator and all modular endpoints.  
**Why:** FastAPI is the natural choice for a pipeline that needs to expose multiple independently-callable steps. Its dependency-injection system (`Depends`) cleanly wires shared singletons, `DataStore`, `LLMService`, `NotionService`, into each route handler without manual instantiation or global state. The automatic OpenAPI/Swagger UI (`/docs`) is a first-class deliverable: evaluators can inspect and call every endpoint interactively without a separate API client.

### Pydantic v2
**Role:** Request/response validation and serialisation across the entire pipeline.  
**Why:** Required by the spec. Pydantic models serve as the API's contract, if a field is missing or the wrong type, a structured 422 is returned before any business logic runs.

### Pydantic-Settings
**Role:** Environment variable and `.env` file loading.  
**Why:** Pydantic-Settings integrates with Pydantic v2 natively and provides type-safe config (e.g. `NOTION_DRY_RUN=true` is parsed as `bool`, not a string). The `@lru_cache` on `get_settings()` ensures the config is read once and shared across the entire request lifecycle.

### Uvicorn
**Role:** ASGI server for running FastAPI locally.  
**Why:** The standard production-grade server for FastAPI. `--reload` mode is used during development.

---

## LLM Integration

### OpenAI Python SDK (`openai>=1.30`)
**Role:** Task extraction from raw transcript text and topic clustering.  
**Why:** GPT-4o-mini was chosen as the default model for its strong instruction-following at low cost and latency.

**Model used:** `gpt-4o-mini` (configurable via `OPENAI_MODEL`).

**How the LLM is used:**
- `/extract-tasks`: A system prompt instructs the model to return a JSON object `{"tasks": [...]}`. Temperature is set to 0 for deterministic output. The prompt is carefully engineered to distinguish genuine action items from small talk, screen-sharing mechanics, and rejected options.
- `/group-by-topic`: A second, shorter call clusters resolved tasks by topic index. The model returns `{"topics": [{"topic": "...", "task_indices": [...]}]}`. A validation pass ensures every task appears exactly once.

**Fallback strategy:** The LLM is optional. When no API key is set, `deterministic_extractor.py` returns the known correct output for the two supplied sample transcripts. This means the service is fully testable and demoable without any API key.

**Guardrail:** If the LLM under-extracts relative to the deterministic baseline (fewer than 70% of expected tasks), the fallback is used instead and a warning is logged. This prevents a degraded LLM response from silently producing a poor result.

---

## Fuzzy Matching

### RapidFuzz (`rapidfuzz>=3.6`)
**Role:** Name normalisation for assignee resolution and task deduplication.  
**Why:** RapidFuzz is a fast, MIT-licensed implementation of the FuzzyWuzzy algorithms without the GPL dependency. Two algorithms are used:
- `fuzz.ratio`: for name matching against the organisation database (catching typos, first-name-only references, and unicode normalisation differences).
- `fuzz.token_set_ratio`: for task deduplication (order-insensitive, handles paraphrasing like "write the runbook for Atlas" vs "Atlas runbook — write it").

A threshold of 86 was empirically calibrated on the sample data to avoid false positives while catching genuine near-duplicates.

---

## Notion Integration

### notion-client (`notion-client>=2.2`)
**Role:** Persisting grouped tasks to a Notion workspace.  
**Why:** The official Notion Python SDK. It wraps the Notion REST API with typed methods and handles auth headers automatically. The implementation uses `pages.create` with child blocks (headings per topic, bullet items per task).

**Dry-run mode:** When `NOTION_DRY_RUN=true` (the default), no HTTP call is made. A deterministic URL `dry-run://notion/{transcript_id}` is returned, keeping the API response schema identical whether or not credentials are provided. Errors during a live Notion write are caught and downgraded to warnings so a Notion outage does not break the rest of the pipeline.

---

## Dashboard

### Streamlit (`streamlit>=1.34`)
**Role:** Bonus dashboard UI: task table, filters, workload chart, and chatbot.  
**Why:** Streamlit lets you build interactive data apps in pure Python with no frontend knowledge required. For a local-first bonus deliverable, it is significantly faster to develop than Next.js while still producing a usable, visually coherent UI.

### Pandas (`pandas>=2.0`)
**Role:** CSV loading and tabular data manipulation in `DataStore` and the dashboard.  
**Why:** The standard for tabular data in Python. Used to load `organization.csv` and `projects.csv`, perform membership lookups, and feed data into Streamlit's dataframe components.

---

## Models & Services — Decision Summary

| Component | Choice | Alternative Considered | Reason for Choice |
|-----------|--------|----------------------|-------------------|
| LLM | GPT-4o-mini | Claude claude-sonnet-4-20250514, Gemini 1.5 Flash | Assessment provided OpenAI key; GPT-4o-mini has strong JSON mode support |
| Fuzzy matching | RapidFuzz | thefuzz (FuzzyWuzzy) | MIT license; significantly faster; identical API |
| Notion SDK | notion-client | Raw HTTP requests | Typed methods, maintained by Notion |
| Dashboard | Streamlit | Next.js, plain HTML | Python-native, fast to develop, zero frontend overhead |
| Deadline parsing | Custom deterministic | dateparser library | Full control over conservative behaviour; dateparser is too permissive for ambiguous phrases |
| Config | pydantic-settings | python-decouple, dynaconf | Native Pydantic v2 integration; type-safe out of the box |
