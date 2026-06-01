"""
Orchestrator routes — proxy endpoints for other modules.

Rate-limited, validated proxy with health checks.

Each module exposes POST /init and POST /run.
These routes forward requests to the correct module and return the response.

The module URLs are configured via environment variables:
  EQUATION_MODULE_URL=http://localhost:8001
  ANIMATION_MODULE_URL=http://localhost:8002
"""

import httpx
import logging
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from routes.schemes.orchestrator import (
    ModuleInitRequest,
    ModuleRunRequest,
    EquationRunRequest,
    AnimationRunRequest,
)
from helpers.config import get_settings
from core.limiter import limiter

logger = logging.getLogger("uvicorn.error")

orchestrator_router = APIRouter(
    prefix="/api/v1",
)

# Timeout for proxied requests (seconds)
PROXY_TIMEOUT = 30.0

# Maximum payload size for proxied requests (bytes)
MAX_PROXY_PAYLOAD_SIZE = 50_000  # 50KB


async def _proxy_post(base_url: str, path: str, payload: dict) -> dict:
    """Forward a POST request to another module and return its JSON response."""
    url = f"{base_url.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=PROXY_TIMEOUT) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


def _check_module_url(module_name: str, base_url: str):
    """Return error response if module URL is not configured."""
    if not base_url:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"signal": f"{module_name} module URL not configured"},
        )
    return None


def _handle_proxy_error(module_name: str, base_url: str, error: Exception):
    """Return appropriate error response for proxy failures."""
    if isinstance(error, httpx.ConnectError):
        logger.error(f"Cannot connect to {module_name} module at {base_url}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"signal": f"{module_name} module is not running"},
        )
    elif isinstance(error, httpx.TimeoutException):
        logger.error(f"{module_name} module timed out at {base_url}")
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={"signal": f"{module_name} module timed out"},
        )
    else:
        logger.error(f"{module_name} error: {error}")
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"signal": f"{module_name} module error: {str(error)}"},
        )


# ---------------------------------------------------------
# HEALTH CHECKS — frontend needs to know which modules are up
# Check module availability without calling /run
# ---------------------------------------------------------

@orchestrator_router.get("/modules/health")
async def modules_health(request: Request):
    """
    Check which other modules are reachable.
    Returns a dict of module_name -> {available: bool, url: str, status: str}.
    Frontend uses this to show/hide module tabs.
    """
    settings = get_settings()
    modules = {
        "equation": getattr(settings, "EQUATION_MODULE_URL", None),
        "animation": getattr(settings, "ANIMATION_MODULE_URL", None),
        "input_parsing": getattr(settings, "INPUT_PARSING_MODULE_URL", None),
    }

    health_results = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in modules.items():
            if not url:
                health_results[name] = {
                    "available": False,
                    "url": None,
                    "status": "not_configured",
                }
                continue
            try:
                resp = await client.get(f"{url.rstrip('/')}/health")
                health_results[name] = {
                    "available": resp.status_code == 200,
                    "url": url,
                    "status": "healthy" if resp.status_code == 200 else f"unhealthy_{resp.status_code}",
                }
            except httpx.ConnectError:
                health_results[name] = {
                    "available": False,
                    "url": url,
                    "status": "unreachable",
                }
            except Exception as e:
                health_results[name] = {
                    "available": False,
                    "url": url,
                    "status": f"error: {str(e)[:100]}",
                }

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"modules": health_results},
    )


# ---------------------------------------------------------
# EQUATION MODULE
# Rate limited + validated input
# ---------------------------------------------------------

@orchestrator_router.post("/equation/init")
@limiter.limit("10/minute")
async def equation_init(request: Request, init_request: ModuleInitRequest):
    """Initialize the equation module (load models, set config)."""
    settings = get_settings()
    base_url = getattr(settings, "EQUATION_MODULE_URL", None)

    url_error = _check_module_url("Equation", base_url)
    if url_error:
        return url_error

    try:
        result = await _proxy_post(base_url, "/init", init_request.config)
        return JSONResponse(status_code=status.HTTP_200_OK, content=result)
    except Exception as e:
        return _handle_proxy_error("Equation", base_url, e)


@orchestrator_router.post("/equation/run")
@limiter.limit("30/minute")
async def equation_run(request: Request, run_request: EquationRunRequest):
    """
    Forward a solve request to the equation module.
    Uses typed EquationRunRequest for validation.
    Equation module expects: {"query": "..."}
    """
    settings = get_settings()
    base_url = getattr(settings, "EQUATION_MODULE_URL", None)

    url_error = _check_module_url("Equation", base_url)
    if url_error:
        return url_error

    try:
        # Build payload matching equation module's SolveRequest schema
        payload = {"query": run_request.query}
        result = await _proxy_post(base_url, "/run", payload)
        return JSONResponse(status_code=status.HTTP_200_OK, content=result)
    except Exception as e:
        return _handle_proxy_error("Equation", base_url, e)


# ---------------------------------------------------------
# ANIMATION MODULE
# Rate limited + validated input
# ---------------------------------------------------------

@orchestrator_router.post("/animation/init")
@limiter.limit("10/minute")
async def animation_init(request: Request, init_request: ModuleInitRequest):
    """Initialize the animation module."""
    settings = get_settings()
    base_url = getattr(settings, "ANIMATION_MODULE_URL", None)

    url_error = _check_module_url("Animation", base_url)
    if url_error:
        return url_error

    try:
        result = await _proxy_post(base_url, "/init", init_request.config)
        return JSONResponse(status_code=status.HTTP_200_OK, content=result)
    except Exception as e:
        return _handle_proxy_error("Animation", base_url, e)


@orchestrator_router.post("/animation/run")
@limiter.limit("30/minute")
async def animation_run(request: Request, run_request: AnimationRunRequest):
    """
    Forward an animation request to the animation module.
    Phase 4: Uses typed AnimationRunRequest for validation.
    """
    settings = get_settings()
    base_url = getattr(settings, "ANIMATION_MODULE_URL", None)

    url_error = _check_module_url("Animation", base_url)
    if url_error:
        return url_error

    try:
        payload = run_request.model_dump(exclude_none=True)
        result = await _proxy_post(base_url, "/run", payload)
        return JSONResponse(status_code=status.HTTP_200_OK, content=result)
    except Exception as e:
        return _handle_proxy_error("Animation", base_url, e)
