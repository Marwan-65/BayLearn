"""
NLP route handlers and batch helpers
=====================================

Extracted from routes/nlp.py to keep the router file focused on
endpoint definitions. This module owns:

  - _build_controller      : wire an NLPController with all clients
  - _run_rag               : retrieve + generate with ablation overrides
  - _sources_payload       : response-shape helper for sources block
  - _retrieval_metadata    : response-shape helper for retrieval metadata
  - _handle_rag_only       : intent handler for rag_only
  - _handle_equation_from_context : intent handler + equation module call
  - _run_batch             : evaluate a batch of test cases under a config
  - _avg_latency           : average timings across a batch
"""

import logging
import os
import time
from typing import Optional

import httpx
from fastapi import Request

from controllers import NLPController
from helpers.config import get_settings

logger = logging.getLogger("uvicorn.error")


# ---------------------------------------------------------
# Build an NLPController with all wired clients
# ---------------------------------------------------------
def _build_controller(request: Request) -> NLPController:
    return NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        chunk_repository=request.app.chunk_repository,
        reranker_client=getattr(request.app, "reranker_client", None),
        bm25_client=getattr(request.app, "bm25_client", None),
        contextual_cache=getattr(request.app, "contextual_cache", None),
    )


# =====================================================================
# Shared: run retrieve + generate with ablation flags
# =====================================================================

def _run_rag(
    controller: NLPController,
    project_id: str,
    question: str,
    limit: int = 5,
    *,
    intent: str = "rag_only",
    enable_multi_query: Optional[bool] = None,
    enable_hybrid: Optional[bool] = None,
    enable_reranker: Optional[bool] = None,
    enable_compression: Optional[bool] = None,
    chat_history: list = None,
) -> dict:
    retrieval = controller.retrieve_sources(
        project_id=project_id,
        question=question,
        limit=limit,
        intent=intent,
        enable_multi_query=enable_multi_query,
        enable_hybrid=enable_hybrid,
        enable_reranker=enable_reranker,
        enable_compression=enable_compression,
    )

    if "error" in retrieval:
        try:
            system_prompt = (
                "You are BayLearn, a friendly engineering tutor. The student's "
                "uploaded materials do not cover this question (or they haven't "
                "uploaded anything yet). Answer their question naturally and briefly "
                "from your own knowledge. Do NOT mention that their materials don't "
                "cover it — just answer the question directly. Keep answers concise."
            )
            prior = []
            if chat_history:
                for msg in chat_history[-6:]:
                    role = msg.get("role", "")
                    content = (msg.get("content") or "")[:800]
                    if role in ("user", "assistant") and content:
                        prior.append({"role": role, "content": content})
            answer = controller.generation_client.generate_text(
                prompt=question,
                chat_history=[{"role": "system", "content": system_prompt}] + prior,
            )
        except Exception:
            answer = (
                "I couldn't find this in your uploaded materials. "
                "Try uploading a relevant PDF or ask me something else."
            )
        return {
            "query": question,
            "answer": answer,
            "sources": [],
            "scores": [],
            "rerank_scores": [],
            "num_sources": 0,
            **_retrieval_metadata(retrieval),
        }

    filtered_results = retrieval["filtered_results"]
    timings = retrieval["timings"]

    answer = controller.generate_answer_from_sources(
        question=question,
        filtered_results=filtered_results,
        timings=timings,
        chat_history=chat_history,
    )
    timings["total_ms"] = sum(
        v for v in timings.values() if isinstance(v, (int, float))
    )

    return {
        "query": question,
        "answer": answer,
        **_sources_payload(filtered_results, controller),
        **_retrieval_metadata(retrieval),
    }


def _image_url(raw_path: Optional[str]) -> Optional[str]:
    """Convert a local image_path (e.g. 'extracted_images/page1_1.png')
    to a full URL served by the Input Parsing Module's /images/ endpoint."""
    if not raw_path:
        return None
    if raw_path.startswith("http"):
        return raw_path
    settings = get_settings()
    base = getattr(settings, "INPUT_PARSING_MODULE_URL", None)
    if not base:
        return None
    filename = os.path.basename(raw_path)
    return f"{base.rstrip('/')}/images/{filename}"


def _sources_payload(filtered_results: list, controller: NLPController) -> dict:
    source_meta = [
        {
            "chunk_type": r["payload"].get("chunk_type", "text"),
            "image_url": _image_url(r["payload"].get("image_path")),
            "page": r["payload"].get("page"),
            "source": r["payload"].get("source"),
            "section_heading": r["payload"].get("section_heading"),
        }
        for r in filtered_results
    ]
    return {
        "sources": [r["payload"].get("text", "") for r in filtered_results],
        "source_meta": source_meta,
        "scores": [r["score"] for r in filtered_results],
        "rerank_scores": (
            [r.get("rerank_score") for r in filtered_results]
            if controller.reranker_client is not None else []
        ),
        "num_sources": len(filtered_results),
    }


def _retrieval_metadata(retrieval: dict) -> dict:
    return {
        "multi_query_used": retrieval.get("multi_query_used", False),
        "query_variants": retrieval.get("query_variants", []),
        "reranker_used": retrieval.get("reranker_used", False),
        "hybrid_used": retrieval.get("hybrid_used", False),
        "bm25_count": retrieval.get("bm25_count", 0),
        "fusion_sources": retrieval.get("fuse_labels", []),
        "compression_used": retrieval.get("compression_used", False),
        "compression_ratios": retrieval.get("compression_ratios", []),
        "timings": retrieval.get("timings", {}),
    }


# =====================================================================
# Intent-first handlers
# =====================================================================

async def _handle_rag_only(controller, project_id, question, limit, chat_history=None):
    return _run_rag(
        controller=controller,
        project_id=project_id,
        question=question,
        limit=limit,
        intent="rag_only",
        chat_history=chat_history,
    )


async def _handle_equation_from_context(
    controller, project_id, question, limit, extracted_params, confidence
):
    from helpers.config import get_settings
    settings = get_settings()

    retrieval = controller.retrieve_sources(
        project_id=project_id,
        question=question,
        limit=limit,
        intent="equation_from_context",
    )
    # If retrieval returned ANY error (no sources, empty collection,
    # mid-upload, etc.), still solve the equation from the raw question
    # using the equation module. The user's intent was clearly to solve
    # an equation — don't block on retrieval.
    if "error" in retrieval:
        equation_result = None
        eq_error = None
        base_url = getattr(settings, "EQUATION_MODULE_URL", None)
        if base_url:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{base_url.rstrip('/')}/run",
                        json={"query": question},
                    )
                    if resp.status_code == 200:
                        equation_result = resp.json()
                    else:
                        eq_error = f"status {resp.status_code}"
                        logger.warning(
                            f"Equation module returned {resp.status_code}: "
                            f"{resp.text[:200]}"
                        )
            except httpx.ConnectError:
                eq_error = "not running"
                logger.warning(f"Equation module not reachable at {base_url}")
            except Exception as e:
                eq_error = str(e)
                logger.warning(f"Equation module call failed: {e}")
        else:
            eq_error = "not configured"
        if equation_result:
            answer = (
                "Here's the solution from the equation module. See the "
                "extracted equation and solver output below."
            )
        elif eq_error == "not running":
            answer = (
                "The equation module is not running on port 9001. "
                "Start it in tab 2 and try again."
            )
        else:
            answer = (
                "The equation module couldn't process this query "
                f"({eq_error}). Try rephrasing — e.g. "
                '"Find the derivative of sin(x)*x^2" (no trailing period).'
            )
        return {
            "intent": "equation_from_context",
            "intent_confidence": confidence,
            "query": question,
            "answer": answer,
            "equation_text_sent": question,
            "equation_result": equation_result,
            "sources": [],
            "scores": [],
            "num_sources": 0,
            **_retrieval_metadata(retrieval),
        }

    filtered_results = retrieval["filtered_results"]
    timings = retrieval["timings"]

    # If the user's question already contains the equation / directive
    # (e.g. "Solve 2x+y=10", "Find the derivative of sin(x)*x^2",
    # "graph sin(x)"), send the question itself — extracting from PDF
    # chunks only makes sense for prompts like "solve the equation from
    # page 3" that reference the material.
    q_lower = question.lower()
    self_contained = any(
        kw in q_lower for kw in (
            "solve", "derivative", "derive", "integrate", "integral",
            "limit", "eigenvalue", "eigenvector", "determinant", "inverse",
            "matrix", "simplify", "factor", "expand", "graph", "plot",
        )
    ) or any(op in question for op in ("=", "+", "-", "*", "/", "^"))

    t0 = time.time()
    if self_contained:
        equation_text = question
    else:
        equation_text = controller.extract_equation_from_sources(
            filtered_results=filtered_results,
            question=question,
        )
    timings["equation_extraction_ms"] = round((time.time() - t0) * 1000)

    equation_result = None
    base_url = getattr(settings, "EQUATION_MODULE_URL", None)
    if base_url:
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{base_url.rstrip('/')}/run",
                    json={"query": equation_text},
                )
                if resp.status_code == 200:
                    equation_result = resp.json()
                else:
                    logger.warning(
                        f"Equation module returned {resp.status_code}: "
                        f"{resp.text[:200]}"
                    )
        except httpx.ConnectError:
            logger.warning(f"Equation module not running at {base_url}")
        except Exception as e:
            logger.warning(f"Equation module call failed: {e}")
        timings["equation_module_ms"] = round((time.time() - t0) * 1000)
    else:
        logger.warning("EQUATION_MODULE_URL not configured")

    # If the equation module already returned a solution, prefer a
    # concise summary over the strict source-grounded answer (which
    # would say "not covered" because the chunks are about theory,
    # not numeric solutions).
    if equation_result:
        answer = (
            "Here's the solution from the equation module. See the "
            "extracted equation and solver output below."
        )
    else:
        answer = controller.generate_answer_from_sources(
            question=question,
            filtered_results=filtered_results,
            timings=timings,
        )
    timings["total_ms"] = sum(
        v for v in timings.values() if isinstance(v, (int, float))
    )

    return {
        "intent": "equation_from_context",
        "intent_confidence": confidence,
        "query": question,
        "answer": answer,
        "equation_text_sent": equation_text,
        "equation_result": equation_result,
        **_sources_payload(filtered_results, controller),
        **_retrieval_metadata(retrieval),
    }



# =====================================================================
# Batch evaluation helpers (used by /evaluate and /evaluate/ablation)
# =====================================================================

def _run_batch(
    controller: NLPController,
    project_id: str,
    cases: list,
    *,
    enable_multi_query: Optional[bool],
    enable_hybrid: Optional[bool],
    enable_reranker: Optional[bool],
    enable_compression: Optional[bool],
):
    test_cases = []
    test_details = []

    for case in cases:
        rag_response = _run_rag(
            controller=controller,
            project_id=project_id,
            question=case["question"],
            limit=5,
            intent="rag_only",
            enable_multi_query=enable_multi_query,
            enable_hybrid=enable_hybrid,
            enable_reranker=enable_reranker,
            enable_compression=enable_compression,
        )

        sources = rag_response.get("sources", [])
        if isinstance(sources, str):
            sources = [sources]
        elif not isinstance(sources, list):
            sources = []

        test_cases.append({
            "question": case["question"],
            "answer": rag_response.get("answer", ""),
            "contexts": sources,
            "ground_truth": case["ground_truth"],
        })
        test_details.append({
            "question": case["question"],
            "level": case.get("level"),
            "answer": rag_response.get("answer", "")[:200],
            "num_contexts": len(sources),
            "timings": rag_response.get("timings", {}),
            "rerank_scores": rag_response.get("rerank_scores", []),
            "compression_ratios": rag_response.get("compression_ratios", []),
        })

    return test_cases, test_details


def _avg_latency(test_details: list) -> dict:
    all_timings = [d["timings"] for d in test_details if d["timings"]]
    if not all_timings:
        return {}
    avg = {}
    for key in all_timings[0]:
        values = [
            t.get(key, 0) for t in all_timings
            if isinstance(t.get(key), (int, float))
        ]
        if values:
            avg[key] = round(sum(values) / len(values))
    return avg
