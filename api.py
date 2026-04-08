from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import json
import time
import os
from level2_solver import level_2_solver, _extract_graphable_functions

load_dotenv()
app = FastAPI(title ="Baylearn Equation Solver API")

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

class SolveRequest(BaseModel):
    query:str

class GraphableFunction(BaseModel):
    name: str
    expression: str
    var: str
    type: str
    
class SolveResponse(BaseModel):
    success: bool
    operation: str
    steps: list
    final_result: str
    graphable_functions: list
    ai_translation: dict
    metadata: dict

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Welcome to the Baylearn Equation Solver API!", "endpoints":["/init","/run","/health"]}
  
@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": time.time()}
  
@app.get("/init")
@app.post("/init")
async def init():
    """Return embedded frontend HTML"""
    try:
        from fastapi.responses import HTMLResponse
        with open("frontend.html", "r", encoding="utf-8") as f:
            html = f.read()
        return HTMLResponse(content=html)
        
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="frontend.html not found")

@app.post("/run", response_model=SolveResponse)
async def run(request: SolveRequest):
    """Run the equation solver on the provided query"""
    try:
        start_time = time.time()
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
            graphable_functions = _extract_graphable_functions(
              operation,
              ai_data,
              solver_output
            )
        elif ai_data:
            try:
                ai_translation = json.loads(str(ai_data)) if isinstance(ai_data, str) else {}
                operation = ai_translation.get("operation", "unknown") if isinstance(ai_translation, dict) else "unknown"
            except:
                ai_translation = {}
        
        
        steps = _parse_steps_from_output(solver_output)
        
        final_result = _extract_final_result(solver_output)
        
        
        execution_time = (time.time() - start_time)*1000 #ms
        return SolveResponse(
            success=True,
            operation=operation,
            steps=steps,
            final_result=final_result,
            graphable_functions=graphable_functions,
            ai_translation=ai_translation,
            metadata={"execution_time_ms": round(execution_time,2)}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
      
      
def _parse_steps_from_output(output: str) -> list:
    """Extract step-by-step text from solver output"""
    if not output:
        return []
    
    # Split by "Step" pattern
    lines = output.split("\n")
    steps = []
    current_step = ""
    
    for line in lines:
        if "Step" in line and ":" in line:
            if current_step:
                steps.append(current_step.strip())
            current_step = line
        else:
            current_step += "\n" + line
    
    if current_step:
        steps.append(current_step.strip())
        
    return [s for s in steps if s]

def _extract_final_result(output: str) -> str:
    """Extract final result from solver output"""
    if "Final Result:" in output:
        parts = output.split("Final Result:")
        if len(parts) > 1:
            result = parts[-1].split("\n")[0].strip()
            return result
    return "No result"