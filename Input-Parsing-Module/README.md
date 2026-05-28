
# BayLearn - Input Parsing Module

This repository contains the Input Parsing API used to parse uploaded files into structured content for downstream RAG/LLM workflows.

## Project Layout

- `Input-Parsing-Module/`: FastAPI service and parsers
- `Input-Parsing-Module/app/parsers/pdf_parser.py`: PDF parser with hybrid OCR routing (PaddleOCR + Gemini + Groq)
- `Input-Parsing-Module/app/models/unified_content_schema.py`: Structured output schema

## Requirements

The dependency list is maintained in `Input-Parsing-Module/requirements.txt` and includes:

- API framework: FastAPI, Uvicorn
- Database/runtime: SQLAlchemy, psycopg2-binary, Alembic, python-dotenv
- OCR/vision: PyMuPDF, PaddleOCR, OpenCV, Pillow, img2table
- LLM OCR providers: google-genai, groq
- Audio/video parsing: openai-whisper, ffmpeg-python
- Runtime binary: ffmpeg must be installed and available on `PATH`

## Environment Setup

1. Go to the service directory:

```powershell
cd Input-Parsing-Module
```

2. Create and activate a virtual environment:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

3. Install the Python dependencies:

```powershell
pip install -r requirements.txt
```

4. Set up your database environment variables in `.env` if they are not already configured.

5. Run Alembic migrations if your database schema needs to be created or updated:

```powershell
alembic upgrade head
```

6. Install ffmpeg if it is not already available on your machine.

	On Windows, one option is:

```powershell
winget install Gyan.FFmpeg
```

7. Verify ffmpeg is available:

```powershell
ffmpeg -version
```

8. Create your local env file from the template:

```powershell
copy .env.example .env
```

9. Set at least:

- `GEMINI_API_KEY`
- `GROQ_API_KEY` (optional but recommended as fallback)
- `DATABASE_URL` or the equivalent SQLAlchemy connection settings used by the app

## Run The API

From `Input-Parsing-Module`:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open:

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## API Schema

### Endpoints

- Method: `POST`
- Path: `/upload`
- Content type: `multipart/form-data`
- Field: `file` (binary)

- Method: `GET`
- Path: `/files/{user_id}`
- Purpose: List all uploaded files for a user

- Method: `GET`
- Path: `/files/{file_id}/chunks`
- Purpose: Return all chunks for a specific file in chunk order

- Method: `GET`
- Path: `/files/{file_id}`
- Purpose: Return metadata for a single uploaded file

- Method: `DELETE`
- Path: `/files/{file_id}`
- Purpose: Delete a file and all of its sections/chunks

### Upload Response

The `POST /upload` endpoint returns a unified `ParsedContent` payload for PDF, image, audio, and video uploads.

### Health Response

`GET /health`

```json
{
	"status": "healthy",
	"module": "input-parsing"
}
```

### User Files Response

`GET /files/{user_id}`

```json
[
	{
		"file_id": "3f2c5c72-7b7f-4e77-8a3d-3d0c8e5e9a11",
		"title": "Lecture 1",
		"source_type": "video",
		"file_name": "lecture1.mp4",
		"total_chunks": 12,
		"uploaded_at": "2026-05-28T10:15:30.000000"
	}
]
```

### File Chunks Response

`GET /files/{file_id}/chunks`

```json
[
	{
		"chunk_id": "0f2dd7e7-0f53-4b0f-9d73-6f2a0f2a4bb3",
		"content": "Welcome to the course...",
		"chunk_index": 0,
		"chunk_type": "transcript_segment",
		"chunk_metadata": {
			"chunk_type": "transcript_segment",
			"start_seconds": 0,
			"end_seconds": 18.42,
			"language": "en"
		}
	}
]
```

### File Metadata Response

`GET /files/{file_id}`

```json
{
	"file_id": "3f2c5c72-7b7f-4e77-8a3d-3d0c8e5e9a11",
	"title": "Lecture 1",
	"source_type": "video",
	"file_name": "lecture1.mp4",
	"file_path": "uploads/lecture1.mp4",
	"total_chunks": 12,
	"uploaded_at": "2026-05-28T10:15:30.000000"
}
```

### Delete Response

`DELETE /files/{file_id}`

```json
{
	"message": "File deleted successfully"
}
```

### Response Shape (PDF / image uploads)

For PDF and handwritten/image parsing, the API returns `ParsedContent` from `app/models/unified_content_schema.py`.
The current PDF parser emits chunk metadata with `page`, `section_heading`, `chunk_type`, and optional `image_path`.

```json
{
	"file_id": "3f2c5c72-7b7f-4e77-8a3d-3d0c8e5e9a11",
	"source_type": "pdf",
	"title": "PDF Document",
	"sections": [
		{
			"id": "2f7f14a4-2a2a-4ea4-9ef6-17cd7f9e06d4",
			"heading": "Page 1",
			"page": 1,
			"chunks": [
				{
					"id": "1be43347-2de6-46a6-9f02-cf35afb4117a",
					"content": "Introduction to reinforcement learning...",
					"chunk_index": 0,
					"metadata": {
						"page": 1,
						"section_heading": "Page 1",
						"chunk_type": "text"
					}
				},
				{
					"id": "ecef2a06-a657-48e6-a68c-cc70171ee891",
					"content": "Flowchart showing policy iteration...",
					"chunk_index": 1,
					"metadata": {
						"page": 1,
						"section_heading": "Page 1",
						"chunk_type": "image",
						"image_path": "extracted_images/page1_0.png"
					}
				}
			]
		}
	],
	"total_chunks": 2
}
```

### Response Shape (audio / video uploads)

Audio and video uploads now return the same `ParsedContent` structure as PDF/image parsing. The parser groups transcript segments into chunks, adds timestamp metadata, and sets `source_type` to `audio` or `video`.

```json
{
	"file_id": "3f2c5c72-7b7f-4e77-8a3d-3d0c8e5e9a11",
	"source_type": "video",
	"title": "Lecture 1",
	"sections": [
		{
			"id": "7b9a2c41-7d3d-4c4b-81a5-3ec4d2a45f41",
			"heading": "Lecture 1",
			"page": null,
			"chunks": [
				{
					"id": "0f2dd7e7-0f53-4b0f-9d73-6f2a0f2a4bb3",
					"content": "Welcome to the course...",
					"chunk_index": 0,
					"metadata": {
						"chunk_type": "transcript_segment",
						"start_seconds": 0.0,
						"end_seconds": 18.42,
						"language": "en"
					}
				}
			]
		}
	],
	"total_chunks": 1
}
```

### Schema Definitions

- `ParsedContent`
	- `source_type: string`
	- `title: string | null`
	- `sections: Section[]`
	- `total_chunks: number`

- `Section`
	- `id: string`
	- `heading: string | null`
	- `page: number | null`
	- `chunks: Chunk[]`

- `Chunk`
	- `id: string`
	- `content: string`
	- `chunk_index: number`
	- `metadata: object`

### Chunk Metadata (current PDF parser)

- `page: number`
- `section_heading: string | null`
- `chunk_type: "text" | "image" | "table"`
- `image_path?: string` (present for image chunks)

### Chunk Metadata (audio/video parsers)

- `chunk_type: "transcript_segment" | "transcript_full"`
- `start_seconds?: number` (present on transcript segment chunks)
- `end_seconds?: number` (present on transcript segment chunks)
- `language?: string`
- `source_type: "audio" | "video"`

## Quick Test

```bash
curl -X POST "http://localhost:8000/upload" \
	-F "file=@sample.pdf"
```

