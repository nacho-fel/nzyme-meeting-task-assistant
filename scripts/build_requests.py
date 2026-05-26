from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

metadata = json.loads((DATA / "metadata.json").read_text(encoding="utf-8"))["transcripts"]
for item in metadata:
    transcript_id = item["transcript_id"]
    transcript = (DATA / item["file"]).read_text(encoding="utf-8")
    payload = {
        "transcript_id": transcript_id,
        "transcript": transcript,
        "metadata": {
            "meeting_title": item["meeting_title"],
            "date": item["date"],
            "participants": item["participants"],
        },
    }
    (ROOT / f"request_{transcript_id[-3:]}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
