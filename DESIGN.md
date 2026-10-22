# Design Note

Voice Notes is a FastAPI + SQLite service with self-hosted `faster-whisper` STT, a
provider-agnostic OpenAI-compatible LLM, and a vanilla JS dashboard. README covers
setup and API usage; this note covers the important design decisions.

## Architecture

```text
Browser: upload / live PCM / typed text
   |           |              |
 ffmpeg     wrap WAV          |
   \__________/               |
        |                     |
  faster-whisper              |
        \_____________________/
                  |
       Note saved before the LLM
                  |
   LLM -> Pydantic validation -> one repair retry
                  |
   task action -> {note, intent, action}
```

- `app/api` handles HTTP validation, status codes, pagination, and WebSocket setup.
- `app/services` contains orchestration, ffmpeg/STT, LLM extraction, task resolution,
  and streaming.
- `app/repositories.py` owns every SQLAlchemy query; `app/models.py` defines `notes` and
  `tasks`.
- STT and LLM sit behind `Transcriber` and `IntentExtractor` protocols, so tests use
  fakes instead of downloading a model or calling the network.

## Key invariants

1. A successful transcription becomes a committed note **before** LLM extraction.
2. A failed LLM or task action never deletes the transcript; the note keeps
   `processing_error`.
3. Task mutation and note linking commit together, or roll back together.
4. The final full transcription is authoritative; live partials are provisional.
5. Task lookup is deterministic and never guesses on ambiguity.
6. Timestamps are UTC; due dates are date-only.

## Data model

| Table | Important fields |
|---|---|
| `notes` | `id`, `raw_transcript`, `created_at`, `source`, `task_id`, `intent`, `processing_error` |
| `tasks` | `id`, `title`, `description`, `status`, `priority`, `due_date`, `created_at`, `updated_at` |

A note optionally links to one task. Deleting a task sets `note.task_id` to `NULL`;
notes are never cascade-deleted. SQLite foreign-key enforcement is enabled per
connection so that behavior actually holds.

## Request flows

**Voice upload:** size-check the upload, convert to 16 kHz mono WAV with ffmpeg,
transcribe with faster-whisper, persist the note, extract the intent, execute the
action, return `{note, intent, action}`. If there is no transcript, no note is created.
If the LLM or task action fails after transcription, the note remains.

**Text:** `POST /api/notes` joins the same pipeline after note creation with
`source=text`. Voice and text share validation, extraction, and task behavior.

**Live stream:** the browser sends 16 kHz mono `int16` PCM over
`WS /api/voice/stream`. The server buffers it, emits provisional partials from rolling
10-second chunks, and on `stop` transcribes the complete recording before running the
normal pipeline. `cancel` or disconnect discards the buffer.

## LLM prompt and validation

The client uses only the common OpenAI-compatible contract:
`POST {LLM_BASE_URL}/chat/completions`, reading `choices[0].message.content`. It does
not require tools, streaming, or provider-specific structured output.

The system prompt includes:

- current UTC datetime plus tomorrow and the current week bounds;
- definitions of `CREATE_TASK`, `UPDATE_TASK_STATUS`, `QUERY_TASKS`, `GENERAL_NOTE`;
- the exact JSON shape and per-intent rules;
- "use `null` instead of guessing" instructions;
- a prompt-injection guard treating the transcript as data;
- four short few-shot examples with dynamic dates.

Output handling:

1. Strip optional markdown fences, take the first-to-last brace span, and require a
   JSON object.
2. Validate with Pydantic: enums, dates, non-blank fields, date ranges, and
   cross-field payload rules (for example, `CREATE_TASK` requires `task` and must not
   include `update`/`query`).
3. On invalid JSON or schema errors, append the bad output and error to the prompt and
   ask for corrected JSON once. Default is two attempts total.
4. Terminal validation failure returns `422 intent_extraction_failed` with the
   persisted note attached.
5. Network, timeout, HTTP, malformed-envelope, empty-content, and unconfigured LLM
   failures return `503 llm_unavailable` and are not retried.

Using one repair retry keeps latency and cost bounded while fixing the common case:
formatting mistakes. Availability failures belong to infrastructure, not prompt repair.

## Intent execution

| Intent | Behavior |
|---|---|
| `CREATE_TASK` | Creates a `PENDING` task; missing priority defaults to `MEDIUM`; links the note. |
| `UPDATE_TASK_STATUS` | Resolves exact ID first, then normalized title; updates and links the note. |
| `QUERY_TASKS` | Applies status/priority/due filters, returns up to 100 tasks plus total; note is not linked. |
| `GENERAL_NOTE` | Saves the note only. |

Task resolution lowercases and strips punctuation, removes common stop words, and
compares the reference to task titles using substring or token overlap. The best score
wins; ties return `409` with candidate IDs/titles. No match returns `404`. Cancelled
tasks are excluded from fuzzy matching but can still be found by exact ID. Guessing
would be worse than asking the client to disambiguate.

## API and errors

The API exposes health, voice upload, WebSocket streaming, text notes, paginated notes
with source/date/task filters, and paginated task reads/updates/deletes with
status/priority/due/title filters. Full request/response details are in the README.

REST errors use `{"error": {"code", "message", "details"}}`; WebSocket errors use
`{"type": "error", "error": {...}}`. Common statuses are `413` (too large), `422`
(validation/audio/intent failure), `503` (LLM unavailable), `404` (missing), `409`
(ambiguous task), and `500` (unexpected error). Intent-related failures attach the
persisted note at the top level of the response.

## STT, streaming, and runtime

- faster-whisper is lazy-loaded and cached; inference is serialized with a lock.
- Uploads use ffmpeg normalization, VAD, and the configured beam size.
- Live partials re-transcribe a rolling window with `beam_size=1`; the final pass uses
  the normal beam size. This is not word-by-word streaming, but it gives useful
  feedback without a streaming STT server.
- If `AudioWorklet` or the WebSocket is unavailable, the dashboard falls back to
  `MediaRecorder`/file upload.
- SQLite uses `create_all` at startup; there is no migration tool. All queries are in
  the repository layer, so Postgres can replace it later.
- Sessions are per request; `expire_on_commit=False` keeps response serialization
  simple. `GET /health` does not depend on the LLM, so the dashboard and docs are
  usable before configuration.

## Security

Implemented: prompt-injection guard, escaped dashboard output, SQLAlchemy parameter
binding, temporary upload files with size/time limits, and ignored `.env` secrets.

Not implemented and intentionally out of scope: authentication, per-user isolation,
rate limiting, CSRF protection (no cookie auth), moderation, and audit logs. Do not
expose this service publicly without adding auth and rate limits.

## Testing

The suite has 40 offline tests using fake STT/LLM adapters; it never downloads Whisper
or calls a network LLM. It covers voice/text pipelines, all intents, filters and
pagination, ambiguous task references, invalid LLM output and note preservation, upload
limits, deletion behavior, frontend/static serving, and WebSocket streaming. Coverage
is about 88% of `app/`; the gaps are mostly real adapters and error branches. The real
adapters were smoke-tested manually with `samples/create_task.wav`.

Run `uv run pytest`, `uv run ruff check .`, and `uv run ruff format --check .`. See the
README for the quick start and end-to-end curl.

## Trade-offs

| Decision | Benefit | Cost |
|---|---|---|
| Note committed before LLM | Transcript durability | One extra write on failure |
| Bring-your-own OpenAI-compatible LLM | No provider lock-in or bundled key | Reviewer must configure one |
| Synchronous processing | Simple and testable | Slow model holds the request |
| SQLite + `create_all` | Zero setup | Single-node, no migrations |
| Heuristic task matching | Deterministic and cheap | Paraphrases can miss |
| Rolling-window partials | Live feedback without streaming STT | Extra CPU; provisional text |
| No framework dashboard | No build step or Node | Manual DOM/state management |
| No auth or semantic search | Smaller scope | Not production-ready; no fuzzy note retrieval |

## What I would probably do with more time

1. **System App.** Making this a system app that can be activated with a wake word seems like a most obvious thing.
2. **Background processing.** Move STT/extraction to a queue with status endpoints.
3. **Better streaming STT.** Current is slow.
4. **Semantic search.** Embed `raw_transcript` into FAISS/Qdrant/pgvector; add search.
5. **Observability.** Structured logs, stage latency, request IDs, and the like.