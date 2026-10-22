# Voice Notes

A voice-first notes and task manager. Record from the browser (or upload an audio
file, or type), transcribe with a self-hosted Whisper model, classify the intent with
an LLM, save the transcript as a note, and execute the resulting task action.

The backend is FastAPI + SQLite. Speech-to-text is `faster-whisper` (open source and
self-hosted). Intent extraction uses **your own OpenAI-compatible
`/v1/chat/completions` endpoint**; no provider, model, or API key is bundled. The
dashboard is plain HTML/CSS/JavaScript served by FastAPI, so there is no Node build
step and no second process.

## Contents

- [What it does](#what-it-does)
- [Requirement coverage](#requirement-coverage)
- [Prerequisites](#prerequisites)
- [Quick start (under 10 minutes)](#quick-start-under-10-minutes)
- [Configuration](#configuration)
- [STT model download notes](#stt-model-download-notes)
- [Using the dashboard](#using-the-dashboard)
- [API reference](#api-reference)
- [Intent behavior](#intent-behavior)
- [Data model](#data-model)
- [Tests and quality checks](#tests-and-quality-checks)
- [Troubleshooting](#troubleshooting)
- [Known limitations and gotchas](#known-limitations-and-gotchas)
- [Project layout](#project-layout)
- [Design note](#design-note)
- [What is intentionally out of scope](#what-is-intentionally-out-of-scope)

## What it does

```text
Audio upload (webm/wav/mp3/m4a) --ffmpeg--> 16 kHz mono WAV --+
                                                              |
Live recording (16 kHz int16 PCM) --wrap as WAV -------------+--> faster-whisper --> transcript
                                                              |
Typed note (POST /api/notes) ---------------------------------+--> transcript
                                                                       |
                                                                       v
                                     Note is saved and committed BEFORE the LLM is called
                                                                       |
                                                                       v
                          OpenAI-compatible LLM --> Pydantic validation (one repair retry)
                                                                       |
                                                                       v
                             Task action: create, update status, query, or save note only
                                                                       |
                                                                       v
                                             Structured response: {note, intent, action}
```

The important invariant: a successful transcription becomes a durable note even if
the LLM is unavailable, returns invalid JSON, or the task action fails. The response
and the note record explain what happened.

Implemented behavior:

| Area | Behavior |
|---|---|
| Voice input | `POST /api/voice/transcribe` accepts an uploaded audio blob. ffmpeg converts any decodable format to 16 kHz mono WAV. |
| Live input | `WS /api/voice/stream` accepts 16 kHz mono `int16` PCM and emits provisional partial text while recording. |
| Text input | `POST /api/notes` runs the same intent pipeline with `source=text`. |
| Notes | Every successful transcription is stored with `id`, `raw_transcript`, `created_at`, `source`, and an optional `task_id`. |
| Intents | `CREATE_TASK`, `UPDATE_TASK_STATUS`, `QUERY_TASKS`, `GENERAL_NOTE`. |
| Task statuses | `PENDING`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`. |
| Validation | All LLM output is parsed and validated with Pydantic. Invalid output gets one repair retry; terminal failure returns a clear `422` with the persisted note. |
| Task resolution | Exact task ID first, then normalized title matching. Ambiguity returns `409` with candidates instead of guessing. |
| List APIs | Paginated and filterable notes and tasks. |
| Errors | One JSON envelope: `{"error": {"code", "message", "details"}}`. |
| Docs | FastAPI-generated OpenAPI documentation at `/docs`. |
| Dashboard | Responsive single-page UI with voice capture, live transcript, typed notes, task filters, inline status updates, and a notes timeline. |
| Tests | 40 offline tests using fake STT/LLM adapters; no model download or network required. |

## Requirement coverage

| Assignment requirement | Implementation |
|---|---|
| Self-hosted, open-source STT (hosted STT APIs are not acceptable) | `faster-whisper` in `app/services/stt.py`; ffmpeg normalization in `app/services/audio.py`. |
| Accept uploaded audio (webm, wav, mp3, m4a, ...) | `POST /api/voice/transcribe`; ffmpeg decodes the input, so any format ffmpeg understands works. |
| Every successful transcription stored as a Note | `NotePipeline.process()` persists the note before extraction (`app/services/pipeline.py`). |
| Required note fields | `app/models.py`: `id`, `raw_transcript`, `created_at`, `source`, `task_id`, plus `intent` and `processing_error`. |
| Four intents and extracted entities | System prompt and Pydantic contract in `app/services/intent.py` and `app/schemas/intents.py`. |
| Validated structured LLM output | Pydantic models, cross-field rules, one repair retry, explicit `422`/`503` behavior. |
| All required REST endpoints | See [API reference](#api-reference). |
| Pagination and filters | Notes filter by source/date/task; tasks filter by status/priority/due range/text; all lists use `limit`/`offset`. |
| README a new engineer can run in under 10 minutes | This file, plus `.env.example`, sample audio, and copy-paste commands. |
| Design note | [DESIGN.md](DESIGN.md). |
| Bonus: dashboard | `app/static/`, served at `/` by the API. |
| Bonus: streaming transcription | `WS /api/voice/stream` plus `AudioWorklet` capture. |
| Bonus: tests | 40 tests in `tests/`. |
| Bonus: OpenAPI docs | `/docs` and `/openapi.json`. |
| Optional bonuses not included | Hosted deployment, Docker, semantic search, and demo video. See [What is intentionally out of scope](#what-is-intentionally-out-of-scope). |

## Prerequisites

| Dependency | Version / notes |
|---|---|
| Python | **3.11** (pinned in `.python-version`; `uv` installs it if needed) |
| `uv` | Latest; manages the virtual environment and dependencies |
| `ffmpeg` | Any recent build, available on `PATH` (or set `FFMPEG_BIN`) |
| LLM endpoint | Your own OpenAI-compatible `POST {LLM_BASE_URL}/chat/completions` endpoint |
| Browser | A modern browser for the dashboard; live capture uses `AudioWorklet` and falls back to `MediaRecorder`/file upload |

### Install prerequisites

macOS:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
brew install ffmpeg
ffmpeg -version
```

Ubuntu/Debian:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo apt-get update && sudo apt-get install -y ffmpeg
ffmpeg -version
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
winget install Gyan.FFmpeg
ffmpeg -version
```

If `ffmpeg -version` fails, install ffmpeg before starting the API; otherwise audio
uploads will fail with a clear `422 audio_processing_failed` response.

## Quick start (under 10 minutes)

Run all commands from the repository root (the directory that contains
`pyproject.toml`, `app/`, and `samples/`).

### 1. Install dependencies

```bash
uv sync
```

`uv` reads `.python-version`, installs Python 3.11 if necessary, creates `.venv`, and
installs every dependency from `uv.lock`. You do **not** need to run
`python -m venv` separately. If you prefer to create the environment explicitly,
`uv venv --python 3.11` does the same thing; `uv sync` then installs into it.

For the fastest first run, after copying `.env` in step 2, set
`WHISPER_MODEL=tiny.en` before the end-to-end check. The default `small.en` downloads
about 460 MB on first use; `tiny.en` is much smaller and faster to start, with lower
accuracy.

### 2. Configure your LLM

The app is bring-your-own-LLM. Copy the example environment file and fill in the three
LLM values:

macOS/Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Minimal `.env` for a hosted provider:

```dotenv
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-your-key
LLM_MODEL=gpt-4o-mini
```

Any endpoint that accepts `POST {LLM_BASE_URL}/chat/completions` and returns
`choices[0].message.content` works. The model ID must be one that your provider
actually serves. Use the base URL **without** `/chat/completions`; the app appends
that path.

For an unauthenticated local server, leave `LLM_API_KEY` empty. For example, with
`llama.cpp`:

```bash
llama-server -m /path/to/model.gguf --host 127.0.0.1 --port 8080 --alias my-model
```

```dotenv
LLM_BASE_URL=http://127.0.0.1:8080/v1
LLM_API_KEY=
LLM_MODEL=my-model
```

Application was initially made with local LLM in-mind because I'm interested in that more 
and already had a nice setup. The application starts even if the LLM is unconfigured, so
you can open the dashboard and check `/health`; audio/text processing then returns a
clear `503 llm_unavailable` with the persisted note.

### 3. Start the app

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The app binds to **`127.0.0.1:8000`**:

- Dashboard: <http://127.0.0.1:8000/>
- OpenAPI docs: <http://127.0.0.1:8000/docs>
- Health: <http://127.0.0.1:8000/health>

**Database initialization:** there is no separate migration or init command. On
startup, SQLAlchemy creates `data/app.db` and the `notes`/`tasks` tables if they do not
exist (`create_all`). The `data/` directory is created automatically and is ignored by
git.

**Dashboard setup:** there is no separate frontend setup or start command. The
dashboard is served by the same FastAPI process at `/`.

### 4. Verify liveness

```bash
curl -sS http://127.0.0.1:8000/health
```

Expected:

```json
{"status":"ok","service":"Voice Notes API","version":"0.1.0"}
```

On Windows PowerShell, use `curl.exe` instead of `curl` (`curl` is an alias for
`Invoke-WebRequest` in PowerShell).

### 5. Run the end-to-end voice check

The committed sample at `samples/create_task.wav` says:
*"Remind me to send a deployment summary to the team tomorrow."*

```bash
curl -sS -X POST http://127.0.0.1:8000/api/voice/transcribe \
  -F "file=@samples/create_task.wav;type=audio/wav"
```

Windows PowerShell (one line):

```powershell
curl.exe -sS -X POST http://127.0.0.1:8000/api/voice/transcribe -F "file=@samples/create_task.wav;type=audio/wav"
```

Expected shape (`201 Created`; IDs, timestamps, and the resolved date vary):

```json
{
  "note": {
    "id": "note_...",
    "raw_transcript": "Remind me to send a deployment summary to the team tomorrow.",
    "created_at": "2026-...Z",
    "source": "voice",
    "task_id": "task_...",
    "processing_error": null
  },
  "intent": "CREATE_TASK",
  "action": {
    "type": "task_created",
    "task": {
      "id": "task_...",
      "title": "Send deployment summary to the team",
      "description": null,
      "status": "PENDING",
      "priority": "MEDIUM",
      "due_date": "...",
      "created_at": "2026-...Z",
      "updated_at": "2026-...Z"
    },
    "tasks": null,
    "total": null
  }
}
```

The top-level `intent` is authoritative for the operation; the embedded note omits its
persisted `intent` field so the same value is not returned twice. `GET /api/notes`
still includes `intent` on every note.

The **first STT call is slow**: `faster-whisper` downloads and loads the model on first
use. Subsequent calls are much faster. See
[STT model download notes](#stt-model-download-notes).

### 6. Open the dashboard

Open <http://127.0.0.1:8000/> and use the microphone button, upload an audio file, or
type a note. Microphone access requires a secure context; `localhost` and `127.0.0.1`
work in modern browsers. If you access the app from another device over plain HTTP,
use the upload button instead.

Recording is capped at 120 seconds. The microphone path streams 16 kHz PCM over
`WS /api/voice/stream`; the live transcript is provisional and is replaced by the
final transcription before intent extraction. If the WebSocket or `AudioWorklet` is
unavailable, the browser falls back to uploading the recording. WAV/MP3/M4A uploads
also work.

### 7. Try the text path and task APIs

```bash
# Create a note/task without audio
curl -sS -X POST http://127.0.0.1:8000/api/notes \
  -H 'Content-Type: application/json' \
  -d '{"text":"Remind me to review the PR tomorrow, high priority"}'

# List notes (paginated and filterable)
curl -sS "http://127.0.0.1:8000/api/notes?limit=10&offset=0&source=text"

# List tasks
curl -sS "http://127.0.0.1:8000/api/tasks?status=PENDING&limit=20&offset=0"

# Update a task
curl -sS -X PATCH http://127.0.0.1:8000/api/tasks/<task_id> \
  -H 'Content-Type: application/json' \
  -d '{"status":"COMPLETED"}'

# Delete a task
curl -sS -X DELETE http://127.0.0.1:8000/api/tasks/<task_id>
```

## Configuration

`.env` is loaded automatically from the repository root. The LLM settings are
required for intent extraction; every other setting is optional and has a default.
`LLM_API_KEY` is required for hosted providers and may be empty only for an
unauthenticated local server.

| Variable | Default | Required | Purpose |
|---|---|---|---|
| `APP_NAME` | `Voice Notes API` | No | Service name in `/health` and OpenAPI. |
| `APP_VERSION` | `0.1.0` | No | Version in `/health`. |
| `ENVIRONMENT` | `development` | No | Deployment label; included in the startup log. |
| `LOG_LEVEL` | `INFO` | No | Python log level. |
| `DATABASE_URL` | `sqlite:///./data/app.db` | No | SQLAlchemy database URL. The SQLite file is created automatically. |
| `MAX_AUDIO_MB` | `25` | No | Maximum uploaded audio size. |
| `MAX_STREAM_SECONDS` | `120` | No | Maximum live recording length. |
| `FFMPEG_BIN` | `ffmpeg` | No | ffmpeg executable name or absolute path. |
| `FFMPEG_TIMEOUT_SECONDS` | `60` | No | Per-file ffmpeg timeout. |
| `WHISPER_MODEL` | `small.en` | No | Whisper model name or local CTranslate2 model path. `.en` models are English-only. |
| `WHISPER_DEVICE` | `cpu` | No | `cpu` or `cuda`. |
| `WHISPER_COMPUTE_TYPE` | `int8` | No | CTranslate2 compute type. `int8` works on CPU; use `float16` for GPU. |
| `WHISPER_LANGUAGE` | `en` | No | Language code, or `auto` for detection. Pair `auto` with a multilingual model. |
| `WHISPER_BEAM_SIZE` | `5` | No | Decoding beam size for final transcriptions. |
| `LLM_BASE_URL` | _(empty)_ | Yes (extraction) | OpenAI-compatible base URL, without `/chat/completions`. |
| `LLM_API_KEY` | _(empty)_ | Hosted: yes | API key. Leave empty only for an unauthenticated local server. |
| `LLM_MODEL` | _(empty)_ | Yes (extraction) | Model name/alias sent to the endpoint. |
| `LLM_TIMEOUT_SECONDS` | `60` | No | LLM HTTP timeout. |
| `LLM_TEMPERATURE` | `0` | No | Extraction temperature. Keep at 0 for deterministic behavior. |
| `LLM_MAX_TOKENS` | `512` | No | Maximum completion tokens. |
| `LLM_MAX_ATTEMPTS` | `2` | No | Total extraction attempts: initial call plus one repair retry. |

## STT model download notes

`faster-whisper` downloads models from Hugging Face on first use. The default is
`small.en` (`Systran/faster-whisper-small.en`, about 460 MB), cached under
`~/.cache/huggingface/hub` on macOS/Linux or
`%USERPROFILE%\.cache\huggingface\hub` on Windows. No manual download command is
required. The first transcription waits on the download and model load.

Useful settings:

- `WHISPER_MODEL=tiny.en` for the fastest first run and lowest memory use.
- `WHISPER_MODEL=base.en` for a small download with decent accuracy.
- `WHISPER_MODEL=small.en` (default) balances accuracy and CPU latency.
- For non-English audio, use a multilingual model (for example `WHISPER_MODEL=small`,
  without the `.en` suffix) and set `WHISPER_LANGUAGE=auto` or a language code.
- `WHISPER_MODEL=distil-small.en` runs faster with slightly lower accuracy.
- `WHISPER_MODEL=medium.en` or `large-v3-turbo` for higher accuracy; use a GPU
  (`WHISPER_DEVICE=cuda`) for live partials at those sizes.
- A local CTranslate2 model directory can also be passed as `WHISPER_MODEL`.
- The default is CPU `int8`, which works without CUDA libraries:
  `WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8`.
- GPU is optional. `WHISPER_DEVICE=cuda` with `WHISPER_COMPUTE_TYPE=float16`
  requires a CTranslate2-compatible CUDA/cuDNN setup.

On Windows you may see a Hugging Face warning about symlinks; it is harmless. The
model still downloads and runs.

## Using the dashboard

The dashboard is the primary interface and covers the full product flow:

- **Overview** — record, upload, or type a capture; see open/due/completed counts, the
  current focus list, and recent notes.
- **Tasks** — filter by status, search by title, change status inline, or delete.
- **Notes** — browse every transcript, filter by source, and open details including the
  linked task and any processing error.

Recording features:

- Live provisional transcript while speaking.
- Timer, cancel button, and input-level meter.
- Upload fallback via `MediaRecorder`/file picker when live capture is unavailable.
- Automatic final transcription before intent extraction.
- Query results (for `QUERY_TASKS`) and task actions are shown as dialogs/toasts.

All UI assets live in `app/static/` and are served by the API. There is no frontend
build, package manager, or separate dev server. When live capture is unavailable, the
fallback uploads the browser's WebM/Opus recording (or a file chosen from the picker).

## API reference

Every endpoint is also documented interactively at `/docs` (Swagger UI) and
`/openapi.json`.

| Method | Path | Success | Purpose |
|---|---|---|---|
| `GET` | `/health` | `200` | Liveness check. |
| `POST` | `/api/voice/transcribe` | `201` | `multipart/form-data` field `file`: transcribe audio, save a note, extract intent, execute the action. |
| `WS` | `/api/voice/stream` | `101` | Live 16 kHz mono `int16` PCM; partial transcripts, final extraction. |
| `POST` | `/api/notes` | `201` | JSON `{"text": "..."}`: save a text note and run the same intent pipeline. |
| `GET` | `/api/notes` | `200` | Paginated notes; filters: `source`, `created_from`, `created_to`, `task_id`. |
| `GET` | `/api/notes/{id}` | `200` | A single note, including its linked `task` when present. |
| `GET` | `/api/tasks` | `200` | Paginated tasks; filters: `status`, `priority`, `due_from`, `due_to`, `q`. |
| `GET` | `/api/tasks/{id}` | `200` | A single task. |
| `PATCH` | `/api/tasks/{id}` | `200` | Partial update; at least one field is required. |
| `DELETE` | `/api/tasks/{id}` | `204` | Delete a task. Linked notes survive with `task_id: null`. |

### Notes

`POST /api/notes` request:

```json
{"text": "Remind me to review the PR tomorrow, high priority"}
```

`GET /api/notes` query parameters:

| Parameter | Type | Notes |
|---|---|---|
| `source` | `voice` or `text` | Optional. |
| `created_from` | ISO datetime | Optional lower bound (inclusive). |
| `created_to` | ISO datetime | Optional upper bound (inclusive). |
| `task_id` | string | Optional; notes linked to a task. |
| `limit` | integer | 1–100, default 20. |
| `offset` | integer | Default 0. |

`GET /api/notes/{id}` returns the note plus its linked task, for example:

```json
{
  "id": "note_...",
  "raw_transcript": "Mark the login bug as done.",
  "created_at": "2026-...Z",
  "source": "voice",
  "task_id": "task_...",
  "processing_error": null,
  "intent": "UPDATE_TASK_STATUS",
  "task": {
    "id": "task_...",
    "title": "Fix login bug",
    "status": "COMPLETED",
    "priority": "HIGH",
    "due_date": null,
    "created_at": "2026-...Z",
    "updated_at": "2026-...Z"
  }
}
```

### Tasks

`GET /api/tasks` query parameters:

| Parameter | Type | Notes |
|---|---|---|
| `status` | `PENDING`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED` | Optional. |
| `priority` | `LOW`, `MEDIUM`, `HIGH`, `URGENT` | Optional. |
| `due_from` | date (`YYYY-MM-DD`) | Optional lower bound. |
| `due_to` | date (`YYYY-MM-DD`) | Optional upper bound. |
| `q` | string | Optional title search. |
| `limit` | integer | 1–100, default 20. |
| `offset` | integer | Default 0. |

`PATCH /api/tasks/{id}` accepts any subset of:

```json
{
  "title": "New title",
  "description": "New description",
  "status": "IN_PROGRESS",
  "priority": "HIGH",
  "due_date": "2026-12-31"
}
```

At least one field must be present. `title` and `status` cannot be `null`. Optional
fields can be cleared with `null`. Deleting a task does not delete its notes; the
foreign key uses `ON DELETE SET NULL`.

List responses use the same envelope:

```json
{"items": [], "total": 0, "limit": 20, "offset": 0}
```

### WebSocket live stream

`WS /api/voice/stream` protocol:

1. Connect; the server sends
   `{"type":"ready","sample_rate":16000,"max_seconds":120}`.
2. Send `{"type":"start","sample_rate":16000}`.
3. Send binary little-endian mono `int16` PCM at 16 kHz.
4. The server sends `{"type":"partial","text":"...","seconds":...}` events and
   `{"type":"status","stage":"...","message":"..."}` updates.
5. Send `{"type":"stop"}`. The server sends `final_transcript`, then `result` with the
   same payload shape as `POST /api/voice/transcribe`.
6. Send `{"type":"cancel"}` to discard the recording without creating a note.

Errors are sent as `{"type":"error","error":{"code":"...","message":"..."}}`. The
final full-audio transcription is authoritative; partial text is provisional and may
change while speaking.

### Errors

All API errors use one envelope:

```json
{"error": {"code": "not_found", "message": "Task 'task_x' not found"}}
```

HTTP status codes apply to REST requests. A WebSocket uses an `error` event with the
same `code` and `message` fields.

| Status | Code | When |
|---|---|---|
| `413` | `payload_too_large` | Upload exceeds `MAX_AUDIO_MB`; the stream exceeds `MAX_STREAM_SECONDS` (sent as a WS error event). |
| `422` | `validation_error` | Invalid request body or query parameters. |
| `422` | `audio_processing_failed` | ffmpeg/STT failure, no speech, or undecodable audio. |
| `422` | `intent_extraction_failed` | LLM output was still invalid after the repair retry. |
| `503` | `llm_unavailable` | LLM not configured, unreachable, timed out, or returned an unexpected response shape. |
| `404` | `not_found` | Note or task does not exist, or no task matched a status update. |
| `409` | `conflict` | A status update matched more than one task. The payload includes candidate IDs/titles. |
| `500` | `internal_error` | Unexpected server error (logged). |

Intent-processing failures include the persisted note so the client can still show the
transcript:

```json
{
  "error": {"code": "intent_extraction_failed", "message": "..."},
  "note": {
    "id": "note_...",
    "raw_transcript": "Remind me to send a deployment summary to the team tomorrow.",
    "created_at": "2026-...Z",
    "source": "voice",
    "task_id": null,
    "processing_error": "..."
  }
}
```

## Intent behavior

| Intent | Example | Action |
|---|---|---|
| `CREATE_TASK` | "Remind me to review the PR by Friday, it's high priority." | Creates a `PENDING` task with title, description, due date, priority; links the note. |
| `UPDATE_TASK_STATUS` | "Mark the login bug as done." | Resolves the task, updates the status, links the note. `404` if not found; `409` with candidates if ambiguous. |
| `QUERY_TASKS` | "What tasks are pending for this week?" | Applies status/priority/due-date filters and returns up to 100 tasks plus a total (`tasks_listed`). The note is not linked. |
| `GENERAL_NOTE` | "Interesting idea: use Qdrant for semantic search." | Saves the note only (`note_saved`). |

If the LLM omits a priority for a new task, the pipeline defaults it to `MEDIUM`.
Relative dates are resolved by the LLM against the current UTC datetime; the app
stores date-only `due_date` values.

## Data model

**Note**

- `id` (`note_<uuid>`)
- `raw_transcript`
- `created_at` (UTC)
- `source` (`voice` or `text`)
- `task_id` (nullable FK to `tasks.id`, `ON DELETE SET NULL`)
- `intent` (nullable; filled after successful processing)
- `processing_error` (nullable; filled when extraction/execution fails)

**Task**

- `id` (`task_<uuid>`)
- `title`
- `description` (nullable)
- `status` (`PENDING`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`)
- `priority` (`LOW`, `MEDIUM`, `HIGH`, `URGENT`; nullable, defaults to `MEDIUM` on create)
- `due_date` (date-only, nullable)
- `created_at`, `updated_at` (UTC)

Notes are committed before LLM extraction, so they remain available even when the
LLM or task action fails. Deleting a task does not delete its notes.

## Tests and quality checks

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .

# Optional: line coverage for app/
uv run pytest --cov=app --cov-report=term-missing
```

The 40-test suite uses `FakeTranscriber` and `FakeIntentExtractor`; it never loads
Whisper or calls an LLM. It covers:

- text and voice pipelines
- task creation, status updates, query filters, pagination
- ambiguous task references and unknown tasks
- invalid LLM output and note preservation on failure
- upload limits, empty uploads, undecodable audio
- task deletion with linked notes
- frontend asset serving and `/docs`
- WebSocket streaming, partial events, and sample-rate validation

Real STT and a hosted OpenAI-compatible endpoint are covered by the manual smoke
checks in [Quick start](#quick-start-under-10-minutes). The current suite has about 88%
line coverage on `app/`; the remaining lines are primarily the real STT/LLM adapters
and some error branches.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ffmpeg is not installed or not on PATH` | ffmpeg missing | Install it and verify `ffmpeg -version`; or set `FFMPEG_BIN` to the absolute path. |
| `503 llm_unavailable` / "LLM is not configured" | Missing `LLM_BASE_URL` or `LLM_MODEL` | Fill in `.env`, restart the app. |
| LLM returns `401`/`403` | Bad or missing API key | Set `LLM_API_KEY` for hosted providers. |
| `422 audio_processing_failed` | Corrupt/unsupported audio, or no speech | Try the sample WAV; check the ffmpeg conversion. |
| First transcription is very slow | Model download/load | Wait for the Hugging Face download; use `WHISPER_MODEL=tiny.en` for a smaller test. |
| Microphone does not start | Insecure context or denied permission | Use `localhost`/`127.0.0.1` (or HTTPS), allow microphone access, or upload a file. |
| Live transcript unavailable | No `AudioWorklet` or WebSocket blocked | The app falls back to upload; typed notes still work. |
| `Address already in use` | Port 8000 is occupied | Stop the other process or run uvicorn with `--port 8001`. |
| `No module named app` | Wrong working directory | Run commands from the repository root. |
| `curl` behaves strangely on Windows | PowerShell aliases `curl` to `Invoke-WebRequest` | Use `curl.exe`. |
| Non-English audio transcribes poorly | `small.en` is English-only | Use a multilingual model (e.g. `WHISPER_MODEL=small`) and `WHISPER_LANGUAGE=auto`. |
| `database is locked` under parallel writes | SQLite concurrency | Retry, or use Postgres for heavier multi-user use. |

## Known limitations and gotchas

- Processing is synchronous. A slow model blocks the request, though FastAPI runs
  sync endpoints in a threadpool. Live streaming uses a WebSocket, but final
  transcription and extraction are still one request.
- No authentication; do not expose this service publicly as-is.
- SQLite is used directly with `create_all`, not migrations.
- Task references are resolved by exact ID or normalized title matching. Ambiguous
  matches return `409` with candidates instead of guessing.
- Live partial text comes from re-transcribing a rolling window, so it can change
  before the final transcript; it is not word-by-word streaming.
- Relative dates resolve against the current UTC datetime. Around midnight, a user's
  local "tomorrow" can differ from the resolved date. The app stores date-only
  `due_date` values.
- The dashboard is intentionally framework-free and refetches after mutations; it has
  no offline queue or real-time multi-client sync.
- The app requires you to configure an LLM before intent extraction can run. Without
  it, the note is still persisted (and voice transcription still succeeds), but the
  API returns `503` with the note attached.
- Smaller self-hosted models are usable but less reliable than larger hosted models.
  The validation/repair layer is the safety net.
- Docker, hosted deployment, semantic search, and a demo video are not included. See
  the next section.

## Project layout

```text
app/
  api/            FastAPI routers and dependency aliases
  schemas/        Pydantic request/response and LLM contract models
  services/       STT, audio conversion, LLM client, intent extraction, pipeline,
                  task resolution, and live WebSocket streaming
  static/         Dashboard HTML/CSS/JS, served directly by FastAPI
  repositories.py All SQLAlchemy queries
  models.py       notes and tasks tables
  db.py           Engine/session setup and UTC datetime handling
  factory.py      Application factory, routers, exception handlers, static mount
  main.py         Uvicorn entrypoint
samples/
  create_task.wav Audio for the end-to-end curl
tests/
  test_*.py       API, unit, frontend, and WebSocket tests
  fakes.py        Fake STT/LLM adapters
```

## Design note

See [DESIGN.md](DESIGN.md) for the architecture, LLM prompt strategy, validation and
repair behavior, failure modes, data model, security considerations, trade-offs, and
what I would do with more time.

## What is intentionally out of scope

These are optional assignment bonuses or explicit scope decisions, not accidental
omissions:

- **Docker / docker-compose** — not provided for this submission; the app runs with
  `uv`, Python 3.11, and ffmpeg as documented above.
- **Hosted deployment** — deferred; the README focuses on a reliable local run.
- **Semantic search over notes** — noted as a next step; the stored raw transcripts
  are enough to generate embeddings when a vector store is added.
- **Demo video** — optional bonus, not included.
- **Postman/Insomnia collection** — not included; the assignment accepts OpenAPI
  documentation, which FastAPI serves at `/docs` and `/openapi.json`.

## Acknowledgements

Speech-to-text uses [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper)
(CTranslate2) with OpenAI Whisper models. The API uses
[FastAPI](https://fastapi.tiangolo.com/) and SQLAlchemy.
