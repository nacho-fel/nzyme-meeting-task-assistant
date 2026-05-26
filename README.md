# Nzyme — Meeting Transcript → Task Distribution API

A FastAPI service that turns raw meeting transcripts into structured, actionable work items — with an optional Streamlit dashboard and grounded chatbot.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Project Structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Setup](#setup)
5. [Environment Variables](#environment-variables)
6. [Running the API](#running-the-api)
7. [Running the Dashboard (Bonus)](#running-the-dashboard-bonus)
8. [API Reference](#api-reference)
9. [Reproducing Sample Outputs](#reproducing-sample-outputs)
10. [Running Tests](#running-tests)

---

## Architecture

The system is built around one orchestrator endpoint that internally calls four modular, independently-callable steps. Each step is exposed as its own endpoint so the pipeline can be debugged and partially re-run without going through the full flow.

```
POST /process-transcript
  │
  ├── 1. Parse & Validate
  │       └── Confirm all participant IDs exist in organization.csv
  │
  ├── 2. POST /extract-tasks
  │       ├── OpenAI GPT-4o-mini call (when OPENAI_API_KEY is set)
  │       ├── Deterministic high-precision fallback (for sample transcripts)
  │       └── Deduplication + noise filtering (fuzz threshold 86, NOISE_PATTERNS)
  │
  ├── 3. POST /resolve-assignees
  │       ├── Fuzzy name matching vs. participants first, then full org
  │       ├── Handles non-participant assignees (e.g. "Clara" mentioned but absent)
  │       └── Returns null instead of hallucinating on ambiguous matches
  │
  ├── 4. Deadline Normalisation (inside resolve step)
  │       └── today / tomorrow / weekday / next week / ordinal / end-of-month / end-of-July
  │
  ├── 5. Project Linking (inside resolve step)
  │       └── Fuzzy project name + alias matching against projects.csv
  │
  ├── 6. POST /group-by-topic
  │       ├── LLM topic clustering (when key is set and no topic_hints present)
  │       └── Deterministic fallback using topic_hint fields from extraction
  │
  └── 7. POST /push-to-notion
          ├── Live Notion page creation (when NOTION_TOKEN + NOTION_PARENT_PAGE_ID set)
          └── Dry-run URL fallback: dry-run://notion/{transcript_id}


Bonus Dashboard
  Streamlit app ──► GET /bonus/tasks   (reads from Notion or local response JSON)
                └─► POST /bonus/chat   (deterministic grounded chatbot)
```

**Key design decisions:**
- The LLM is used only for open-ended semantic extraction and topic clustering. All grounding (assignees, projects, deadlines) is done deterministically to prevent hallucination.
- A fuzzy deduplication pass (RapidFuzz token-set-ratio ≥ 86) runs after extraction to eliminate repeated phrasing of the same action item.
- The service runs fully offline. Notion and OpenAI are optional; local fallbacks cover both.

---

## Project Structure

```
nzyme_final_draft/
├── app/
│   ├── main.py                          FastAPI app entry point
│   ├── api/
│   │   └── routes.py                    All endpoints (orchestrator + modular + bonus)
│   ├── core/
│   │   └── config.py                    Pydantic-settings configuration
│   ├── models/
│   │   └── schemas.py                   All Pydantic request/response models
│   └── services/
│       ├── pipeline.py                  Orchestration, deduplication, noise filtering
│       ├── llm_service.py               OpenAI wrapper + deterministic fallback
│       ├── deterministic_extractor.py   High-precision fallback for sample transcripts
│       ├── assignee_resolver.py         Fuzzy org-grounded assignee resolution
│       ├── deadline_parser.py           Conservative relative-deadline normalisation
│       ├── project_linker.py            Active project fuzzy linking
│       ├── notion_service.py            Notion API integration / dry-run mode
│       ├── task_repository.py           Reads tasks from Notion or local JSON
│       ├── chatbot_service.py           Deterministic grounded chatbot service
│       └── data_store.py               Loads organization.csv + projects.csv
├── dashboard/
│   ├── streamlit_app.py                 Bonus Streamlit dashboard + chatbot UI
│   └── assets/
│       └── nzyme_logo.png
├── data/
│   ├── organization.csv
│   ├── projects.csv
│   ├── metadata.json
│   └── transcripts/
│       ├── transcript_001.txt
│       └── transcript_002.txt
├── scripts/
│   ├── build_requests.py               Builds request_001.json and request_002.json
│   └── run_samples.py                  Sends requests and saves response JSON files
├── tests/
│   ├── test_deadline_parser.py
│   ├── test_pipeline_outputs.py
│   └── test_bonus_chatbot.py
├── request_001.json
├── request_002.json
├── response_001_final_final_draft.json
├── response_002_final_final_draft.json
├── requirements.txt
├── pytest.ini
└── .env
```

---

## Prerequisites

- **Python 3.11+**
- No Docker required — everything runs locally

---

## Setup

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/nzyme-transcript-api.git
cd nzyme-transcript-api/nzyme_final_draft

# 2. Create and activate a virtual environment
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env file
cp .env.example .env
# Then edit .env with your credentials (see Environment Variables below)
```

---

## Environment Variables

Create a `.env` file in the project root (`nzyme_final_draft/`). All variables are optional — the service runs fully locally without any of them.

```env
# ── OpenAI (optional) ─────────────────────────────────────────────────────────
# When set, the API uses GPT-4o-mini for task extraction and topic grouping.
# When absent, the deterministic fallback is used for the supplied sample transcripts.
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o-mini          # Default model; change to gpt-4o for higher quality

# ── Notion (optional) ─────────────────────────────────────────────────────────
# When set, tasks are persisted to your Notion workspace.
# When absent (or NOTION_DRY_RUN=true), a dry-run URL is returned instead.
NOTION_TOKEN=secret_...
NOTION_PARENT_PAGE_ID=<your-page-id>   # The Notion page that will contain transcript sub-pages
NOTION_DRY_RUN=true                    # Set to false to write to Notion

# ── Data & Logging ────────────────────────────────────────────────────────────
DATA_DIR=./data                        # Path to the folder containing CSVs and transcripts
LOG_LEVEL=INFO
```

## Running the API

```bash
# From the nzyme_final_draft/ directory, with your .venv active:
uvicorn app.main:app --reload
```

The API starts at `http://127.0.0.1:8000`.

Open the interactive docs at:
```
http://127.0.0.1:8000/docs
```

**Quick health check:**
```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","employees_loaded":15,"projects_loaded":8}
```

**Process a transcript (example):**
```bash
curl -X POST http://127.0.0.1:8000/process-transcript \
  -H "Content-Type: application/json" \
  -d @request_001.json
```

---

## Running the Dashboard (Bonus)

The dashboard requires the API to be running in a separate terminal.

**Terminal 1 — API:**
```bash
uvicorn app.main:app --reload
```

**Terminal 2 — Dashboard:**
```bash
streamlit run dashboard/streamlit_app.py
```

The dashboard opens automatically at `http://localhost:8501`.

**What the dashboard shows:**
- Open tasks table pulled from Notion (or local response JSON in dry-run mode)
- Filters by assignee, project, and deadline/stale status
- Workload-by-member bar chart
- Grounded chatbot panel — example questions:
  - `What does Nora have on her plate?`
  - `Show tasks for PRJ007`
  - `Which tasks have deadlines?`
  - `List active projects`
  - `Are there any stale tasks?`

> **Note:** In dry-run mode, the dashboard reads from `response_*final*.json` files in the project root. Run `python scripts/run_samples.py` first to generate them if they don't exist.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Liveness check — reports counts of loaded employees and projects |
| `POST` | `/process-transcript` | Full pipeline orchestrator |
| `POST` | `/extract-tasks` | LLM extraction only — returns raw `RawTask` list |
| `POST` | `/resolve-assignees` | Grounds raw tasks against org DB, parses deadlines, links projects |
| `POST` | `/group-by-topic` | Clusters resolved tasks under topic headings |
| `POST` | `/push-to-notion` | Persists grouped tasks to Notion (or returns dry-run URL) |
| `GET` | `/bonus/tasks` | Returns all open tasks for the dashboard |
| `POST` | `/bonus/chat` | Grounded chatbot — answers from org/project/task data only |

**Orchestrator request body:**
```json
{
  "transcript_id": "transcript_001",
  "transcript": "<full meeting transcript text>",
  "metadata": {
    "meeting_title": "Q2 Engineering Sprint Planning",
    "date": "2025-05-15",
    "participants": ["EMP001", "EMP003", "EMP007"]
  }
}
```

**Orchestrator response:**
```json
{
  "transcript_id": "transcript_001",
  "topics": [
    {
      "topic": "Atlas Migration",
      "tasks": [
        {
          "description": "Write migration runbook for Atlas cluster cutover",
          "assignee": { "employee_id": "EMP003", "name": "Nora Kim" },
          "deadline": "2025-05-19",
          "project_id": "PRJ004"
        }
      ]
    }
  ],
  "notion_page_url": "https://notion.so/...",
  "warnings": []
}
```

---

## Reproducing Sample Outputs

```bash
# Build the two request JSON files from the data/ folder
python scripts/build_requests.py

# Send both requests to the running API and save response files
python scripts/run_samples.py
```

This writes:
```
response_001_final_final_draft.json
response_002_final_final_draft.json
```

---

## Running Tests

```bash
pytest -q
```

Expected output:
```
4 passed
```

The test suite covers:
- `test_deadline_parser.py` — relative and absolute deadline normalisation edge cases
- `test_pipeline_outputs.py` — end-to-end extraction quality against expected tasks
- `test_bonus_chatbot.py` — chatbot grounding and refusal behaviour
