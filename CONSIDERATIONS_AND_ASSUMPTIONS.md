# Considerations & Assumptions

**Project:** Nzyme — Meeting Transcript → Task Distribution API  
**Scope:** System limitations, improvement vectors, integration notes, and every assumption made during implementation.

---

## Assumptions Made

### Data & Inputs

1. **Employee IDs are case-insensitive.** The API normalises all participant IDs to uppercase on ingestion so that `emp001`, `EMP001`, and `Emp001` are treated identically.

2. **A task can be assigned to a non-participant.** If the transcript explicitly names a person (e.g. "Clara needs to write the report") and that person exists in `organization.csv`, the task is assigned to them even if they were not listed as a meeting participant. This reflects real-world delegation dynamics.

3. **Multi-person collaboration resolves to one owner.** When two people are jointly mentioned for a task, the system assigns the person who is explicitly asked to drive or deliver it. The collaborator is not treated as a secondary assignee (the schema has no such field), though this is noted as a limitation.

4. **Project linking requires an explicit reference.** A `project_id` is attached only when the task description or topic hint clearly references a project name, alias, or workstream present in `projects.csv`. Vague thematic overlap does not trigger a link.

5. **Vague deadlines remain null.** Phrases such as "soon," "ASAP," "next sprint," and "no rush" are deliberately not converted to dates. Only concrete relative expressions (tomorrow, next Wednesday, end of July, the 16th, etc.) are normalised. Returning null for genuinely vague dates is more honest and less error-prone than guessing.

6. **The final stated deadline wins.** When a deadline is revised mid-meeting (e.g. "Wednesday EOD… actually, let's say Monday EOD"), the parser uses the last accepted value, not the first.

7. **Notion is always dry-run by default.** `NOTION_DRY_RUN=true` is the default setting. A live Notion write requires explicit opt-in via environment variables. This ensures the system is runnable locally with zero external credentials.

8. **The `data/` directory layout is fixed.** The service expects `organization.csv`, `projects.csv`, `metadata.json`, and `transcripts/*.txt` to live under the path set by `DATA_DIR` (default `./data`). Changing the layout requires updating `DataStore`.

9. **Participant validation is strict at the orchestrator level.** If any `participant` ID in the request does not exist in `organization.csv`, the `/process-transcript` endpoint raises a 422 error. The modular endpoints (e.g. `/resolve-assignees`) are more lenient to support partial debugging flows.

10. **The LLM is trusted for extraction but not for grounding.** The LLM output is used to identify what tasks exist and who might own them (as a raw hint). All final assignee IDs, project IDs, and dates are resolved deterministically downstream. The LLM cannot invent an employee or project that is not in the databases.

---

## System Limitations

### Extraction Quality

- **Single-language support.** The extraction prompts and deterministic fallback are English-only. Multilingual transcripts would require additional work on both the LLM system prompt and the fuzzy matching normalisation.

- **Speaker attribution relies on transcript formatting.** The system assumes a `Speaker Name:` prefix format (e.g. `Diego: I'll have this done by Friday`). Transcripts without clear speaker labels degrade extraction quality significantly.

- **Under-extraction is the deliberate default.** The noise filter and deduplication are conservative: when in doubt, the system drops a candidate task rather than keeping a false positive. This can miss genuine edge-case action items (e.g. commitments phrased as questions or hypotheticals).

- **No coreference resolution.** Pronouns ("she said she'd do it") are not resolved to specific people. If the LLM cannot identify the speaker from context, the task will have a null assignee.

- **Deterministic fallback is sample-specific.** The `deterministic_extractor.py` fallback is tuned to the two provided assessment transcripts. For new transcripts without an API key, the fallback will return an empty task list, not a generic extraction.

### Assignee Resolution

- **Ambiguous names return null, not a guess.** If "Alex" matches two employees in the organization, the assignee is set to null and a warning is emitted. The system deliberately refuses to guess rather than risk assigning work to the wrong person.

- **No role/department fallback heuristic.** The spec mentions a role/department fallback for unresolved assignees. This was not implemented because applying it incorrectly (e.g. assigning all engineering tasks to the only Engineer in the meeting) would produce worse output than returning null. The warning system flags these cases for human review instead.

- **Fuzzy matching threshold is fixed at 86.** This was calibrated on the sample data. Names with heavy abbreviation (e.g. "Fitz" for "Fitzgerald") may fall below the threshold and not resolve.

### Deadline Parsing

- **Timezone-agnostic.** All dates are normalised to Python `date` objects with no timezone. Meetings spanning midnight or occurring across time zones are not handled.

- **Relative dates anchor to the meeting date, not today.** `tomorrow` always means `meeting_date + 1 day`, regardless of when the API is called. This is correct behaviour but means historical transcripts produce historical deadlines.

- **"Next sprint" stays null.** Sprint length is not configurable, so this phrase is treated as vague rather than guessing a two-week window.

### Notion Integration

- **Simple page structure, not a database.** Tasks are persisted as bullet-point blocks under a heading per topic. A proper Notion database with filterable properties (status, assignee, deadline) would be more powerful but requires a more complex page creation schema.

- **100-block limit applied.** The Notion API has limits on child blocks per request. The implementation caps the first write at 100 blocks. Large meetings with many tasks would need pagination.

- **No update support.** Running `/process-transcript` twice with the same transcript creates two separate Notion pages. There is no upsert/deduplication logic at the Notion level.

### Dashboard & Chatbot

- **Chatbot is deterministic, not generative.** The chatbot uses pattern matching and templated responses rather than an LLM. This guarantees zero hallucination but means it cannot handle paraphrased or complex natural-language queries gracefully.

- **Dashboard does not poll for live updates.** The task table is loaded once per session. A page refresh is required to see newly processed transcripts.

- **Dry-run mode reads local JSON.** In dry-run mode, the dashboard reads from `response_*final*.json` files. These must exist before the dashboard is started (generated by `scripts/run_samples.py`).

---

## Improvement Vectors

### Short-Term (High Impact)

- **Streaming extraction.** Long transcripts can hit LLM context limits. A chunking strategy (e.g. sliding window with overlap) would handle hour-long meeting recordings.

- **Notion database instead of page.** Replacing bullet-point pages with a properly structured Notion database would enable native filtering, sorting, and status tracking inside Notion itself.

- **Upsert logic for re-processing.** An idempotent `/process-transcript` that checks if a page for a given `transcript_id` already exists and updates it rather than creating a duplicate.

- **Confidence scores on assignee resolution.** Surfacing the fuzzy match score and resolution reason in the API response would help consumers decide when to trust the assignment.

- **Role/department heuristic as an opt-in.** Implement the fallback assignee heuristic (assign to the meeting participant whose role/department best fits the task topic) but expose it as an explicit flag (`resolve_by_role=true`) so callers can choose whether to accept it.

### Medium-Term

- **Webhook / async processing.** For production use, `/process-transcript` should be async (accept → 202 → poll or webhook callback). LLM calls on long transcripts can take 10–30 seconds.

- **Speaker diarisation pre-processing.** Integrate with a speech-to-text + diarisation service (e.g. AssemblyAI, Deepgram) so the system can ingest raw audio files, not just pre-formatted text transcripts.

- **Multi-assignee tasks.** Extend the `Task` schema to support `assignees: list[Assignee]` for genuinely collaborative deliverables.

- **Deadline reminder integration.** After persisting to Notion, send a calendar invite or Slack/Teams message to the assignee with the task deadline.

- **LLM provider abstraction.** The current implementation is tightly coupled to OpenAI. Wrapping the LLM calls behind a provider interface would make it easy to swap in Anthropic Claude, Google Gemini, or a locally-hosted model.

### Long-Term

- **Fine-tuned extraction model.** A fine-tuned smaller model (e.g. GPT-4o-mini or Llama 3) trained on labelled meeting transcripts would outperform zero-shot prompting and reduce cost per transcript significantly.

- **Feedback loop.** Allow assignees to confirm/reject tasks via Slack/email and feed those signals back into the extraction model as training examples.

- **Multi-workspace / multi-tenant support.** Currently the service is single-tenant (one `organization.csv`, one Notion workspace). A proper multi-tenant design would scope all data by `workspace_id`.

---

## Integrability with Other Meeting Tools

| Tool | Integration Notes |
|------|-------------------|
| **Granola** | Granola exports meeting notes as structured markdown with speaker labels. The transcript ingestion layer could directly accept Granola's export format with minor parsing changes. |
| **Google Meet / Zoom** | Both services offer auto-generated transcripts via their APIs (Google Meet with Workspace, Zoom with the Recall.ai or native transcript API). These could feed `/process-transcript` automatically on meeting end via a webhook. |
| **Notion** | Already integrated. A natural extension is to use a Notion database (not just a page) so tasks become first-class, filterable records with a status lifecycle. |
| **Slack** | After `/process-transcript`, a Slack bot could DM each assignee their tasks. The `/bonus/chat` chatbot endpoint could also be exposed as a Slack slash command. |
| **Microsoft Teams** | Teams provides transcript exports in VTT format. A lightweight VTT → plain-text converter would make the service compatible with Teams recordings. |
| **Linear / Jira** | Instead of (or in addition to) Notion, the `project_id` field already maps to a project. A `push-to-linear` or `push-to-jira` endpoint following the same `PushToNotionRequest` interface would be straightforward to add. |
| **Calendar (Google / Outlook)** | When a deadline is resolved to a concrete date, a calendar event could be created for the assignee automatically using the Google Calendar or Microsoft Graph APIs. |
