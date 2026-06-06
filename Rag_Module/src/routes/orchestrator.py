import httpx
import logging
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from routes.schemes.orchestrator import (
    ModuleInitRequest,
    EquationRunRequest
)
from helpers.config import get_settings
from core.limiter import limiter
logger = logging.getLogger("uvicorn.error")

orchestrator_router = APIRouter(
    prefix="/api/v1",
)

PROXY_TIMEOUT = 30.0
MAX_PROXY_PAYLOAD_SIZE = 50_000  


async def _proxy_post(base_url: str, path: str, payload: dict) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=PROXY_TIMEOUT) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


def _check_module_url(module_name: str, base_url: str):
    if not base_url:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"signal": f"{module_name} module URL not configured"},
        )
    return None


def _handle_proxy_error(module_name: str, base_url: str, error: Exception):
    if isinstance(error, httpx.ConnectError):
        logger.error(f"Cannot connect to {module_name} module at {base_url}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"signal": f"{module_name} module is not running"},)
    elif isinstance(error, httpx.TimeoutException):
        logger.error(f"{module_name} module timed out at {base_url}")
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={"signal": f"{module_name} module timed out"},)
    else:
        logger.error(f"{module_name} error: {error}")
        return JSONResponse( status_code=status.HTTP_502_BAD_GATEWAY,
            content={"signal": f"{module_name} module error: {str(error)}"},)


@orchestrator_router.get("/modules/health")
async def modules_health(request: Request):
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
                    "status": "not_configured",}
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
                    "status": "unreachable",}
            except Exception as e:
                health_results[name] = {
                    "available": False,
                    "url": url,
                    "status": f"error: {str(e)[:100]}",}
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"modules": health_results},
    )


@orchestrator_router.post("/equation/init")
@limiter.limit("10/minute")
async def equation_init(request: Request, init_request: ModuleInitRequest):
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
async def equation_run(request: Request,run_request: EquationRunRequest):
    settings = get_settings()
    base_url = getattr(settings, "EQUATION_MODULE_URL", None)

    url_error = _check_module_url("Equation", base_url)
    if url_error:
        return url_error

    try:
        payload = {"query": run_request.query}
        result = await _proxy_post(base_url, "/run", payload)
        return JSONResponse(status_code=status.HTTP_200_OK, content=result)
    except Exception as e:
        return _handle_proxy_error("Equation", base_url, e)
