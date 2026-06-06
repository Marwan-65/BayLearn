import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from preprocess_json import prepare_llm_payload
from llm_orchestrator import (
    run_orchestration,
    write_scheduler_processes_txt,
    write_btree_json,
    write_linked_list_json,
)

app = FastAPI(title="Visualizer Transform API", version="1.0.0")

# el cors policy motasam7a 3shan t5aly el 7agat te3raf tetsht8l mn ay origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(BASE_DIR.parent / ".env")

#el class da 3shan y7aded el shape beta3 el data elly hayegi mn el client w y5aly el code aktar nazafa w sahel feh el debugging w el maintenance ba3d kda
class TransformRequest(BaseModel):
    parsed_content: Dict[str, Any] = Field(..., description="Parsed JSON from Input Parsing Module /upload endpoint")
    max_chars_per_window: int = Field(12000, ge=1000, le=100000)
    max_single_tokens: Optional[int] = Field(None, ge=1000, le=200000)

#el class da 3shan y7aded el shape beta3 el data elly hayro7 lel client ba3d ma yet3ml processing 3aleh w kda kda hayb2a nazef w sahel feh el debugging w el maintenance ba3d kda
class TransformResponse(BaseModel):
    animation_type: str
    classification: Dict[str, Any]
    extraction: Optional[Dict[str, Any]]
    llm_payload_meta: Dict[str, Any]


class FileLaunchRequest(BaseModel):
    file_id: str = Field(..., description="ID of an already-parsed file in the Input Parsing Module database")


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

#el function di 3shan t7aded el url elly hayro7 3aleh el client 3ashan yshoof el animation
def _build_viewer_url(animation_type: str, run_id: str) -> str:
    linked_base = _get_env("LINKED_LIST_VIEWER_URL", "http://localhost:8081")
    scheduler_base = _get_env("SCHEDULER_VIEWER_URL", "http://localhost:8082")
    btree_base = _get_env("BTREE_VIEWER_URL", "http://localhost:3000")

    if animation_type == "linked_list":
        return f"{linked_base}?run_id={run_id}"
    if animation_type == "scheduler":
        return f"{scheduler_base}?run_id={run_id}"
    if animation_type == "btree":
        return f"{btree_base}?run_id={run_id}"
    return f"http://localhost:8010/unknown?run_id={run_id}"


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}

# el endpoint el byestelem el data elly gayya mn el input parsing module w by3ml 3aleha processing 3ashan y7awelha le format elly el visualizer 3ayezha
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

# el endpoint da byestelem file upload mn ay client (browser-based aw postman aw gpt function calling) w by3ml forward lel file di lel input parsing module 3ashan y7awelha le parsed json w ba3d kda byro7 lel transform function 3ashan y7awelha le llm payload w extraction w classification w kda w ba3d kda byro7 lel launch function 3ashan y7mlha fe el visualizer
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
        user_id = _get_env("BAYLEARN_USER_ID", "7885bb36-4a00-40a5-88f2-fb7a405f5021")
        params = {
            "user_id": user_id
        }
        parsing_resp = requests.post(upload_url, files=files, params=params, timeout=300)
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

# el launch endpoint da byestelem el data elly gayya mn el transform function w by7awelha le format mo3ayan 3ashan el visualizer y2dar yefhamha w y3mlha animate
@app.post("/v1/launch", response_model=LaunchResponse)
def launch(req: LaunchRequest) -> LaunchResponse:
    if req.extraction is None:
        raise HTTPException(status_code=400, detail="Cannot launch without extraction payload")

    # Write the LLM extractions to the local file system for the visualizers to use
    if req.animation_type == "scheduler":
        scheduler_dir = BASE_DIR.parent / "Scheduler Animation"
        scheduler_txt_path = scheduler_dir / "scheduler" / "processes.txt"
        try:
            write_scheduler_processes_txt(scheduler_txt_path, req.extraction)
        except Exception as e:
            print(f"Warning: Failed to write processes.txt: {e}")

    elif req.animation_type == "btree":
        btree_json_path = BASE_DIR.parent / "btree-visualizer" / "user-scenario.json"
        try:
            write_btree_json(btree_json_path, req.extraction)
        except Exception as e:
            print(f"Warning: Failed to write btree user-scenario.json: {e}")

    elif req.animation_type == "linked_list":
        linked_json_path = BASE_DIR.parent / "Linked List Animation" / "linked-list-sequence.json"
        try:
            write_linked_list_json(linked_json_path, req.extraction)
        except Exception as e:
            print(f"Warning: Failed to write linked-list-sequence.json: {e}")

    if req.animation_type == "scheduler":
        import subprocess
        scheduler_dir = BASE_DIR.parent / "Scheduler Animation"
        algo = req.extraction.get("algorithm", "RR") if req.extraction else "RR"
        algo_map = {"SJF": 0, "HPF": 1, "RR": 2, "MLQ": 3}
        sch_id = algo_map.get(algo, 2)
        q = req.extraction.get("quantum") if req.extraction else 3
        if q is None:
            q = 3
        
        try:
            # Automate the C-backend execution so no manual script running is needed
            subprocess.run(
                ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", "run_scheduler.ps1", "-SCH", str(sch_id), "-Q", str(q), "-ProcessFile", "processes.txt"],
                cwd=str(scheduler_dir),
                check=True
            )
        except Exception as e:
            print(f"Warning: Failed to auto-run scheduler simulation: {e}")

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

#da kan for testing el get run endpoint w el viewer url generation
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

# da el actual endpoint eli bnesta5demo fl frontend 3shanysha8al el module kol, heya eli mgama3a kol eli fo2 w sha8ala 3la el final shape bta3 el input parsing
@app.post("/v1/file-launch", response_model=LaunchResponse)
def file_launch(req: FileLaunchRequest) -> LaunchResponse:
    base_url = _get_env("INPUT_PARSING_BASE_URL", "http://localhost:8000")

    try:
        meta_resp = requests.get(f"{base_url}/files/{req.file_id}", timeout=30)
        if meta_resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"File not found in input parsing module: {req.file_id}")
        meta_resp.raise_for_status()
        file_meta = meta_resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed fetching file metadata: {exc}") from exc

    try:
        chunks_resp = requests.get(f"{base_url}/files/{req.file_id}/chunks", timeout=60)
        if chunks_resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"File has no chunks: {req.file_id}")
        chunks_resp.raise_for_status()
        raw_chunks = chunks_resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed fetching file chunks: {exc}") from exc

    parsed_content = {
        "source_type": raw_chunks.get("source_type") or file_meta.get("source_type", "unknown"),
        "title": raw_chunks.get("title") or file_meta.get("title") or file_meta.get("file_name") or req.file_id,
        "sections": raw_chunks.get("sections", []),
        "total_chunks": raw_chunks.get("total_chunks") or file_meta.get("total_chunks", 0),
    }

    transformed = transform(
        TransformRequest(
            parsed_content=parsed_content,
        )
    )
    return launch(
        LaunchRequest(
            animation_type=transformed.animation_type,
            classification=transformed.classification,
            extraction=transformed.extraction,
            llm_payload_meta=transformed.llm_payload_meta,
        )
    )

#byget el runs 
@app.get("/v1/runs/{run_id}", response_model=RunRecord)
def get_run(run_id: str) -> RunRecord:
    return _read_run(run_id)

#byget el payload beta3 el run record 3ashan y7awelha lel client w y3ml beha animate
@app.get("/v1/runs/{run_id}/payload")
def get_run_payload(run_id: str) -> Dict[str, Any]:
    record = _read_run(run_id)
    return {
        "run_id": record.run_id,
        "animation_type": record.animation_type,
        "extraction": record.extraction,
    }
