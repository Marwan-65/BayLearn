# Visualizer Parser Service

This module is the bridge between:

1. Parsed document JSON (from Input Parsing Module on port 8000)
2. LLM routing/extraction logic
3. Visualizer launch flow

It exposes FastAPI endpoints to transform parsed content into animation-ready payloads and create run sessions for visualizers.

## What This Service Does

- Reconstructs full text + windows from parsed JSON
- Calls Gemini to classify document type (`linked_list`, `scheduler`, or `unknown`)
- Extracts animation-specific structured payload
- Stores run records and serves run payloads for visualizer clients
- Can bridge directly to Input Parsing Module by accepting raw PDF upload

## Prerequisites

- Python 3.10+
- Running Input Parsing Module (for bridge endpoints):
  - `http://localhost:8000/upload`
- Valid Gemini API key with generation access

## Setup

Use the same requirements and virtual environment of the Input-Parsing-Module

Create env file:

```powershell
copy .env.example .env
```

Edit `.env` and fill values (especially `GEMINI_API_KEY`).

## Run API

From `Visualizer/Parser`:

```powershell
uvicorn transform_api:app --reload --host 0.0.0.0 --port 8010
```

Swagger docs:

- `http://localhost:8010/docs`

Health check:

- `GET http://localhost:8010/health`

## Endpoints

### 1) Transform Parsed Content

`POST /v1/transform`

Input: parsed JSON from Input Parsing Module `/upload`.

Example body:

```json
{
  "parsed_content": {
    "source_type": "pdf",
    "title": "",
    "sections": [],
    "total_chunks": 0
  },
  "max_chars_per_window": 12000,
  "max_single_tokens": 24000
}
```

Returns:

- `animation_type`
- `classification`
- `extraction`
- `llm_payload_meta`

### 2) Bridge Upload -> Transform

`POST /v1/ingest-transform`

Form-data:

- `file` = PDF/image/audio/video supported by Input Parsing Module

This endpoint uploads file to Input Parsing Module (`INPUT_PARSING_UPLOAD_URL`) then transforms result.

### 3) Create Launch Session (Phase 2)

`POST /v1/launch`

Input: output payload from `/v1/transform`.

Returns:

- `run_id`
- `animation_type`
- `viewer_url`

### 4) One-call Upload -> Transform -> Launch

`POST /v1/ingest-launch`

Form-data:

- `file`

Returns launch response directly.

### 5) Get Run Record

`GET /v1/runs/{run_id}`

Returns saved run metadata + extraction.

### 6) Get Run Payload Only

`GET /v1/runs/{run_id}/payload`

Returns compact payload for visualizer consumption.

## Quick Test Commands

Run these after both services are up:

1. Input Parsing Module on `:8000`
2. Parser API on `:8010`

```powershell
curl.exe -X POST "http://localhost:8010/v1/ingest-launch" `
  -F "file=@your-test-file-path.pdf"
```

Get run details:

```powershell
curl.exe "http://localhost:8010/v1/runs/RUN_ID"
```

## Files and Persistence

- Run records are saved under:
  - `Visualizer/Parser/runs/`
- LLM outputs from script mode can still be written under:
  - `Visualizer/Parser/outputs/`

## Notes

- Keep visualizer servers running independently; launch endpoints do not start/stop servers. (eg. type "python -m http.server 8081" in the same directory of the index.html in the required animation to be able to use the launch api correctly)
