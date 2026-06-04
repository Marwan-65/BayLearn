import json
import time
from typing import List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import re

# Import refactored solver targets and new helper positions safely
from src.core.solver import level_2_solver
from .helpers import extract_api_graphable_functions
from .models import SolveRequest, SolveResponse
from src.core.formatting.latex import sanitize_latex_artifacts


app = FastAPI(
    title="Baylearn Equation Solver API",
    description="Neuro-symbolic math solver for RAG pipeline integration",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "message": "Welcome to the Baylearn Equation Solver API!",
        "endpoints": ["/init", "/run", "/health"],
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": time.time()}


@app.get("/init")
@app.post("/init")
async def init():
    try:
        with open("frontend.html", "r", encoding="utf-8") as f:
            html = f.read()
        return HTMLResponse(content=html)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="frontend.html not found")


@app.post("/run", response_model=SolveResponse)
async def run(request: SolveRequest):
    try:
        start_time = time.time()
        
        # Pull responses directly from the orchestrator core file
        solver_output, ai_data = level_2_solver(
            request.query,
            show_translation=False,
            return_translation=True
        )

        operation = "unknown"
        ai_translation = {}
        graphable_functions = []

        if isinstance(ai_data, dict):
            operation = ai_data.get("operation", "unknown")
            ai_translation = ai_data
            graphable_functions = extract_api_graphable_functions(
                operation,
                ai_data,
                solver_output
            )
        elif ai_data:
            try:
                ai_translation = json.loads(str(ai_data)) if isinstance(ai_data, str) else {}
                operation = ai_translation.get("operation", "unknown") if isinstance(ai_translation, dict) else "unknown"
            except Exception:
                ai_translation = {}

        steps = _parse_steps_from_output(solver_output)
        final_result = _extract_final_result(solver_output)
        execution_time = (time.time() - start_time) * 1000

        return SolveResponse(
            success=True,
            operation=operation,
            steps=steps,
            final_result=final_result,
            graphable_functions=graphable_functions,
            ai_translation=ai_translation,
            metadata={"execution_time_ms": round(execution_time, 2)},
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _parse_steps_from_output(output: str) -> List[str]:
    if not output:
        return []
    lines = output.split("\n")
    steps = []
    current_step = ""
    for line in lines:
        if "Step" in line and ":" in line:
            if current_step:
                steps.append(sanitize_latex_artifacts(current_step.strip()))
            current_step = line
        else:
            current_step += "\n" + line
    if current_step:
        steps.append(sanitize_latex_artifacts(current_step.strip()))
    return [s for s in steps if s]


def _extract_final_result(output: str) -> str:
    if "Final Result:" in output:
        parts = output.split("Final Result:")
        if len(parts) > 1:
            after_result_lines = parts[-1].split("\n")
            for line in after_result_lines:
                cleaned_line = line.strip()
                if cleaned_line and not cleaned_line.startswith("Graphable"):
                    return sanitize_latex_artifacts(cleaned_line)
    return "No result"