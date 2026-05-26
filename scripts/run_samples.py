from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.schemas import TranscriptRequest  # noqa: E402
from app.services.data_store import DataStore  # noqa: E402
from app.services.llm_service import LLMService  # noqa: E402
from app.services.notion_service import NotionService  # noqa: E402
from app.services.pipeline import TranscriptPipeline  # noqa: E402


def response_filename(transcript_id: str) -> str:
    suffix = transcript_id.split("_")[-1]
    return f"response_{suffix}_final_final_draft.json"


def main() -> None:
    data_store = DataStore(ROOT / "data")
    pipeline = TranscriptPipeline(data_store=data_store, llm=LLMService(), notion=NotionService())
    metadata = json.loads((ROOT / "data" / "metadata.json").read_text(encoding="utf-8"))["transcripts"]

    for item in metadata:
        transcript_id = item["transcript_id"]
        request = TranscriptRequest(
            transcript_id=transcript_id,
            transcript=(ROOT / "data" / item["file"]).read_text(encoding="utf-8"),
            metadata={
                "meeting_title": item["meeting_title"],
                "date": item["date"],
                "participants": item["participants"],
            },
        )
        response = pipeline.process(request)
        public = response.model_dump(mode="json", exclude={"warnings"} if not response.warnings else None)
        out_path = ROOT / response_filename(transcript_id)
        out_path.write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {out_path.name}")


if __name__ == "__main__":
    main()
