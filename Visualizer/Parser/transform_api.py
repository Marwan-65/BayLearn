import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from preprocess_json import prepare_llm_payload
from llm_orchestrator import run_orchestration


app = FastAPI(title="Visualizer Transform API", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)


class TransformRequest(BaseModel):
    parsed_content: Dict[str, Any] = Field(..., description="Parsed JSON from Input Parsing Module /upload endpoint")
    max_chars_per_window: int = Field(12000, ge=1000, le=100000)
    max_single_tokens: Optional[int] = Field(None, ge=1000, le=200000)


class TransformResponse(BaseModel):
    animation_type: str
    classification: Dict[str, Any]
    extraction: Optional[Dict[str, Any]]
    llm_payload_meta: Dict[str, Any]


class LaunchRequest(BaseModel):
    animation_type: str
    classification: Dict[str, Any] = Field(default_factory=dict)
    extraction: Optional[Dict[str, Any]] = None
    llm_payload_meta: Dict[str, Any] = Field(default_factory=dict)


class LaunchResponse(BaseModel):
    run_id: str
    animation_type: str
    viewer_url: str


class RunRecord(BaseModel):
    run_id: str
    status: str
    created_at: str
    animation_type: str
    viewer_url: str
    classification: Dict[str, Any] = Field(default_factory=dict)
    extraction: Optional[Dict[str, Any]] = None
    llm_payload_meta: Dict[str, Any] = Field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _run_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def _write_run(record: RunRecord) -> None:
    _run_path(record.run_id).write_text(record.model_dump_json(indent=2), encoding="utf-8")


def _read_run(run_id: str) -> RunRecord:
    path = _run_path(run_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"run_id not found: {run_id}")
    return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))


def _build_viewer_url(animation_type: str, run_id: str) -> str:
    linked_base = _get_env("LINKED_LIST_VIEWER_URL", "http://localhost:8081")
    scheduler_base = _get_env("SCHEDULER_VIEWER_URL", "http://localhost:8082")

    if animation_type == "linked_list":
        return f"{linked_base}?run_id={run_id}"
    if animation_type == "scheduler":
        return f"{scheduler_base}?run_id={run_id}"
    return f"http://localhost:8010/unknown?run_id={run_id}"


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/transform", response_model=TransformResponse)
def transform(req: TransformRequest) -> TransformResponse:
    try:
        llm_payload = prepare_llm_payload(
            parsed=req.parsed_content,
            max_chars_per_window=req.max_chars_per_window,
        )

        result = run_orchestration(
            payload=llm_payload,
            max_single_tokens=req.max_single_tokens,
        )

        return TransformResponse(
            animation_type=result.get("animation_type", "unknown"),
            classification=result.get("classification", {}),
            extraction=result.get("extraction"),
            llm_payload_meta={
                "document_id": llm_payload.get("document_id"),
                "window_count": llm_payload.get("window_count"),
                "full_text_chars": len(llm_payload.get("full_text", "")),
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/v1/ingest-transform", response_model=TransformResponse)
async def ingest_transform(
    file: UploadFile = File(...),
    max_chars_per_window: int = 12000,
    max_single_tokens: Optional[int] = None,
) -> TransformResponse:
    upload_url = _get_env("INPUT_PARSING_UPLOAD_URL", "http://localhost:8000/upload")

    try:
        file_bytes = await file.read()
        files = {
            "file": (file.filename or "document.bin", file_bytes, file.content_type or "application/octet-stream")
        }
        parsing_resp = requests.post(upload_url, files=files, timeout=300)
        parsing_resp.raise_for_status()
        parsed_content = parsing_resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed calling input parsing module: {exc}") from exc

    return transform(
        TransformRequest(
            parsed_content=parsed_content,
            max_chars_per_window=max_chars_per_window,
            max_single_tokens=max_single_tokens,
        )
    )


@app.post("/v1/launch", response_model=LaunchResponse)
def launch(req: LaunchRequest) -> LaunchResponse:
    if req.extraction is None:
        raise HTTPException(status_code=400, detail="Cannot launch without extraction payload")

    run_id = uuid.uuid4().hex
    viewer_url = _build_viewer_url(req.animation_type, run_id)

    record = RunRecord(
        run_id=run_id,
        status="ready",
        created_at=_now_iso(),
        animation_type=req.animation_type,
        viewer_url=viewer_url,
        classification=req.classification,
        extraction=req.extraction,
        llm_payload_meta=req.llm_payload_meta,
    )
    _write_run(record)

    return LaunchResponse(run_id=run_id, animation_type=req.animation_type, viewer_url=viewer_url)


@app.post("/v1/ingest-launch", response_model=LaunchResponse)
async def ingest_launch(
    file: UploadFile = File(...),
    max_chars_per_window: int = 12000,
    max_single_tokens: Optional[int] = None,
) -> LaunchResponse:
    transformed = await ingest_transform(
        file=file,
        max_chars_per_window=max_chars_per_window,
        max_single_tokens=max_single_tokens,
    )
    return launch(
        LaunchRequest(
            animation_type=transformed.animation_type,
            classification=transformed.classification,
            extraction=transformed.extraction,
            llm_payload_meta=transformed.llm_payload_meta,
        )
    )


@app.get("/v1/runs/{run_id}", response_model=RunRecord)
def get_run(run_id: str) -> RunRecord:
    return _read_run(run_id)


@app.get("/v1/runs/{run_id}/payload")
def get_run_payload(run_id: str) -> Dict[str, Any]:
    record = _read_run(run_id)
    return {
        "run_id": record.run_id,
        "animation_type": record.animation_type,
        "extraction": record.extraction,
    }
