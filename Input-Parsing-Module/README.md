
# BayLearn - Input Parsing Module

This repository contains the Input Parsing API used to parse uploaded files into structured content for downstream RAG/LLM workflows.

## Project Layout

- `Input-Parsing-Module/`: FastAPI service and parsers
- `Input-Parsing-Module/app/parsers/pdf_parser.py`: PDF parser with hybrid OCR routing (PaddleOCR + Gemini + Groq)
- `Input-Parsing-Module/app/models/unified_content_schema.py`: Structured output schema

## Requirements

The dependency list is maintained in `Input-Parsing-Module/requirements.txt` and includes:

- API framework: FastAPI, Uvicorn
- OCR/vision: PyMuPDF, PaddleOCR, OpenCV, Pillow, img2table
- LLM OCR providers: google-genai, groq
- Audio/video parsing: openai-whisper, ffmpeg-python

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

3. Install dependencies:

```powershell
pip install -r requirements.txt
```

4. Create your local env file from the template:

```powershell
copy .env.example .env
```

5. Set at least:

- `GEMINI_API_KEY`
- `GROQ_API_KEY` (optional but recommended as fallback)

## Run The API

From `Input-Parsing-Module`:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open:

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## API Schema

### Endpoint

- Method: `POST`
- Path: `/upload`
- Content type: `multipart/form-data`
- Field: `file` (binary)

### Response Shape (PDF / image uploads)

For PDF and handwritten/image parsing, the API returns `ParsedContent` from `app/models/unified_content_schema.py`.
The current PDF parser emits chunk metadata with `page`, `section_heading`, `chunk_type`, and optional `image_path`.

```json
{
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

### Current Video Response Shape

For video uploads, the current parser returns a legacy structure:

```json
{
	"source_type": "video",
	"title": "Video Transcript",
	"sections": [
		{
			"heading": "Transcript",
			"content": "...",
			"page": null
		}
	]
}
```

## Quick Test

```bash
curl -X POST "http://localhost:8000/upload" \
	-F "file=@sample.pdf"
```

