import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from google import genai
from google.genai import types


def approx_tokens(text: str) -> int:
    # Simple estimate for planning context size.
    return max(1, len(text) // 4)


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_first_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    if not text:
        raise ValueError("Model returned empty response")

    # Try direct JSON first.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try finding the first top-level JSON object.
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("Could not find a JSON object in model response")

    candidate = match.group(0)
    return json.loads(candidate)


def gemini_generate_json(api_key: str, model: str, prompt: str, temperature: float = 0.1) -> Dict[str, Any]:
    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
    except Exception as exc:
        raise RuntimeError(
            "Gemini API request failed through google-genai SDK. "
            "Check GEMINI_API_KEY validity, API enablement, model access, and quota."
        ) from exc

    try:
        text = response.text
    except Exception as exc:
        raise ValueError(f"Unexpected Gemini response shape: {response}") from exc

    return extract_first_json_object(text)


def build_classification_prompt(document_text: str) -> str:
    return (
        "You are a strict classifier for algorithm animation routing.\n"
        "Classify the document into exactly one category: linked_list, scheduler, btree, or unknown.\n"
        "Return JSON only with this schema:\n"
        "{\n"
        "  \"animation_type\": \"linked_list\" | \"scheduler\" | \"btree\" | \"unknown\",\n"
        "  \"confidence\": number between 0 and 1,\n"
        "  \"evidence\": string[]\n"
        "}\n\n"
        "Document:\n"
        f"{document_text}\n"
    )


def build_linked_list_extraction_prompt(document_text: str) -> str:
    return (
        "You extract linked list operation sequences from text.\n"
        "Return JSON only with this schema:\n"
        "{\n"
        "  \"animation_type\": \"linked_list\",\n"
        "  \"confidence\": number between 0 and 1,\n"
        "  \"initial_list\": number[],\n"
        "  \"operations\": [\n"
        "    {\n"
        "      \"op\": \"traverse\" | \"insertAtHead\" | \"insertAtTail\" | \"insertAtIndex\" | \"deleteAtHead\" | \"deleteAtTail\" | \"deleteByValue\" | \"deleteAtIndex\" | \"searchByValue\" | \"reverse\",\n"
        "      \"value\": number | null,\n"
        "      \"index\": integer | null,\n"
        "      \"source_quote\": string\n"
        "    }\n"
        "  ],\n"
        "  \"final_list\": number[]\n"
        "}\n"
        "Rules:\n"
        "- Keep operation order exactly as in text.\n"
        "- Use null for value/index when not required.\n"
        "- Do not invent operations not supported by linked list animation.\n"
        "- If a value appears multiple times in text as repeated operation, emit repeated operations.\n\n"
        "Document:\n"
        f"{document_text}\n"
    )


def build_scheduler_extraction_prompt(document_text: str) -> str:
    return (
        "You extract scheduler process inputs from text for a process file.\n"
        "Return JSON only with this schema:\n"
        "{\n"
        "  \"animation_type\": \"scheduler\",\n"
        "  \"confidence\": number between 0 and 1,\n"
        "  \"algorithm\": \"RR\" | \"SJF\" | \"HPF\" | \"MLQ\" | \"unknown\",\n"
        "  \"quantum\": integer | null,\n"
        "  \"processes\": [\n"
        "    {\n"
        "      \"id\": integer,\n"
        "      \"arrival\": integer,\n"
        "      \"runtime\": integer,\n"
        "      \"priority\": integer,\n"
        "      \"memsize\": integer\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- If some fields are missing, use safe defaults: priority=1, memsize=1.\n"
        "- Do not create negative values.\n"
        "- ids must be unique, increasing integers starting from 1 if not explicit.\n\n"
        "Document:\n"
        f"{document_text}\n"
    )


def build_btree_extraction_prompt(document_text: str) -> str:
    return (
        "You extract B-Tree operation sequences from text.\n"
        "Return JSON only with this schema:\n"
        "{\n"
        "  \"animation_type\": \"btree\",\n"
        "  \"confidence\": number between 0 and 1,\n"
        "  \"name\": string,\n"
        "  \"description\": string,\n"
        "  \"t\": integer,\n"
        "  \"initialKeys\": [integer],\n"
        "  \"operations\": [\n"
        "    {\n"
        "      \"op\": \"insert\" | \"delete\" | \"search\",\n"
        "      \"key\": integer\n"
        "    }\n"
        "  ],\n"
        "  \"pauseMs\": 1500\n"
        "}\n"
        "Rules:\n"
        "- Extract sequential operations in the exact order found in text.\n"
        "- t is the minimum degree of the B-Tree (usually 2 or 3). Default to 2 if not explicitly stated.\n"
        "- initialKeys are any keys that should already be in the tree before the main operations begin.\n\n"
        "Document:\n"
        f"{document_text}\n"
    )


def validate_classification(result: Dict[str, Any]) -> None:
    allowed = {"linked_list", "scheduler", "btree", "unknown"}
    t = result.get("animation_type")
    if t not in allowed:
        raise ValueError(f"Invalid animation_type: {t}")


def validate_linked_list(result: Dict[str, Any]) -> None:
    if result.get("animation_type") != "linked_list":
        raise ValueError("Linked list extraction did not return animation_type=linked_list")
    if not isinstance(result.get("operations"), list):
        raise ValueError("operations must be a list")


def validate_scheduler(result: Dict[str, Any]) -> None:
    if result.get("animation_type") != "scheduler":
        raise ValueError("Scheduler extraction did not return animation_type=scheduler")
    processes = result.get("processes")
    if not isinstance(processes, list) or not processes:
        raise ValueError("processes must be a non-empty list")
    for p in processes:
        for key in ("id", "arrival", "runtime", "priority", "memsize"):
            if key not in p:
                raise ValueError(f"Missing key in process: {key}")


def validate_btree(result: Dict[str, Any]) -> None:
    if result.get("animation_type") != "btree":
        raise ValueError("B-Tree extraction did not return animation_type=btree")
    if not isinstance(result.get("operations"), list):
        raise ValueError("operations must be a list")


def write_scheduler_processes_txt(path: Path, scheduler_data: Dict[str, Any]) -> None:
    lines = ["#id arrival runtime priority memsize"]
    processes = sorted(scheduler_data["processes"], key=lambda p: int(p["id"]))
    for p in processes:
        line = f"{int(p['id'])}\t{int(p['arrival'])}\t{int(p['runtime'])}\t{int(p['priority'])}\t{int(p['memsize'])}"
        lines.append(line)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_linked_list_json(path: Path, linked_data: Dict[str, Any]) -> None:
    # Convert extraction schema to visualizer expected schema.
    out = {}
    out["initialList"] = linked_data.get("initial_list", [])
    ops = []
    for op in linked_data.get("operations", []) or []:
        entry: Dict[str, Any] = {"op": op.get("op")}
        # Ensure explicit nulls when values/indices are not provided.
        entry["value"] = op.get("value") if "value" in op else None
        entry["index"] = op.get("index") if "index" in op else None
        ops.append(entry)
    out["operations"] = ops

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def write_btree_json(path: Path, btree_data: Dict[str, Any]) -> None:
    out = {
        "name": btree_data.get("name", "B-Tree Scenario"),
        "description": btree_data.get("description", ""),
        "t": btree_data.get("t", 2),
        "initialKeys": btree_data.get("initialKeys", []),
        "operations": [],
        "pauseMs": btree_data.get("pauseMs", 1500)
    }
    for op in btree_data.get("operations", []) or []:
        if "op" in op and "key" in op:
            out["operations"].append({
                "op": op["op"],
                "key": op["key"]
            })
            
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def maybe_windowed_extract(
    api_key: str,
    model: str,
    payload: Dict[str, Any],
    animation_type: str,
    max_single_tokens: int,
) -> Dict[str, Any]:
    full_text = payload.get("full_text", "")
    windows = payload.get("windows", []) or []

    use_single = approx_tokens(full_text) <= max_single_tokens or len(windows) <= 1

    if use_single:
        if animation_type == "linked_list":
            return gemini_generate_json(api_key, model, build_linked_list_extraction_prompt(full_text))
        elif animation_type == "btree":
            return gemini_generate_json(api_key, model, build_btree_extraction_prompt(full_text))
        return gemini_generate_json(api_key, model, build_scheduler_extraction_prompt(full_text))

    # Map-reduce fallback for long docs.
    partials: List[Dict[str, Any]] = []
    for i, win in enumerate(windows, start=1):
        header = f"WINDOW {i}/{len(windows)}\n"
        if animation_type == "linked_list":
            partial = gemini_generate_json(api_key, model, build_linked_list_extraction_prompt(header + win))
        elif animation_type == "btree":
            partial = gemini_generate_json(api_key, model, build_btree_extraction_prompt(header + win))
        else:
            partial = gemini_generate_json(api_key, model, build_scheduler_extraction_prompt(header + win))
        partials.append(partial)

    merge_prompt = (
        "You will merge partial extraction JSON objects into one final JSON object.\n"
        f"Target type is: {animation_type}.\n"
        "Rules:\n"
        "- Deduplicate duplicates.\n"
        "- Preserve order when possible.\n"
        "- Return one strict JSON object only.\n\n"
        "Partials:\n"
        f"{json.dumps(partials, ensure_ascii=False)}"
    )
    return gemini_generate_json(api_key, model, merge_prompt)


def get_env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def get_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer") from exc


def run_orchestration(
    payload: Dict[str, Any],
    api_key: str | None = None,
    model: str | None = None,
    max_single_tokens: int | None = None,
    classification_max_chars: int = 20000,
) -> Dict[str, Any]:
    script_dir = Path(__file__).resolve().parent
    # Load local .env with override so stale shell variables do not keep old keys.
    load_dotenv(dotenv_path=script_dir / ".env", override=True)
    # Optionally load cwd .env without overriding the script-local values.
    load_dotenv(override=False)

    resolved_api_key = (api_key or get_env_str("GEMINI_API_KEY")).strip()
    if not resolved_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in environment")

    resolved_model = (model or get_env_str("LLM_MODEL", "gemini-2.5-flash")).strip()
    resolved_max_tokens = max_single_tokens if max_single_tokens is not None else get_env_int("LLM_MAX_SINGLE_TOKENS", 24000)

    doc_for_classification = payload.get("full_text", "")
    if len(doc_for_classification) > classification_max_chars:
        doc_for_classification = doc_for_classification[:classification_max_chars]

    classification = gemini_generate_json(
        resolved_api_key,
        resolved_model,
        build_classification_prompt(doc_for_classification),
        temperature=0.0,
    )
    validate_classification(classification)

    animation_type = classification.get("animation_type", "unknown")
    if animation_type == "unknown":
        return {
            "animation_type": "unknown",
            "reason": "Classifier confidence was not sufficient for linked_list or scheduler",
            "classification": classification,
            "extraction": None,
        }

    extraction = maybe_windowed_extract(
        api_key=resolved_api_key,
        model=resolved_model,
        payload=payload,
        animation_type=animation_type,
        max_single_tokens=resolved_max_tokens,
    )

    if animation_type == "linked_list":
        validate_linked_list(extraction)
    elif animation_type == "btree":
        validate_btree(extraction)
    else:
        validate_scheduler(extraction)

    return {
        "animation_type": animation_type,
        "classification": classification,
        "extraction": extraction,
    }


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    # Load local .env with override so stale shell variables do not keep old keys.
    load_dotenv(dotenv_path=script_dir / ".env", override=True)
    # Optionally load cwd .env without overriding the script-local values.
    load_dotenv(override=False)

    api_key = get_env_str("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in environment")

    payload_value = get_env_str("LLM_PAYLOAD_PATH")
    if not payload_value:
        raise RuntimeError("LLM_PAYLOAD_PATH is not set in environment")

    payload_path = Path(payload_value)
    if not payload_path.is_absolute():
        payload_path = script_dir / payload_path

    if not payload_path.exists():
        raise FileNotFoundError(f"Payload file not found: {payload_path}")

    out_dir_value = get_env_str("LLM_OUT_DIR", "outputs")
    model = get_env_str("LLM_MODEL", "gemini-2.5-flash")
    max_single_tokens = get_env_int("LLM_MAX_SINGLE_TOKENS", 24000)
    scheduler_txt_value = get_env_str(
        "LLM_SCHEDULER_TXT",
        "../Scheduler Animation/scheduler/processes.txt",
    )

    linkedlist_json_value = get_env_str(
        "LLM_LINKEDLIST_JSON",
        "../Linked List Animation/linked-list-sequence.json",
    )

    btree_json_value = get_env_str(
        "LLM_BTREE_JSON",
        "../btree-visualizer/user-scenario.json",
    )

    out_dir = Path(out_dir_value)
    if not out_dir.is_absolute():
        out_dir = script_dir / out_dir

    scheduler_txt_path = Path(scheduler_txt_value)
    if not scheduler_txt_path.is_absolute():
        scheduler_txt_path = script_dir / scheduler_txt_path

    linkedlist_json_path = Path(linkedlist_json_value)
    if not linkedlist_json_path.is_absolute():
        linkedlist_json_path = script_dir / linkedlist_json_path

    btree_json_path = Path(btree_json_value)
    if not btree_json_path.is_absolute():
        btree_json_path = script_dir / btree_json_path

    payload = read_json(payload_path)

    out_dir.mkdir(parents=True, exist_ok=True)

    result = run_orchestration(
        payload=payload,
        api_key=api_key,
        model=model,
        max_single_tokens=max_single_tokens,
    )

    classification = result.get("classification", {})
    extraction = result.get("extraction")
    animation_type = result.get("animation_type", "unknown")

    write_json(out_dir / "classification.json", classification)

    if animation_type == "linked_list" and extraction is not None:
        write_json(out_dir / "linked_list_extraction.json", extraction)
        # Also write a visualizer-friendly linked-list sequence file so
        # the Linked List Animation app can load the scenario.
        try:
            write_linked_list_json(linkedlist_json_path, extraction)
        except Exception:
            # Do not fail the whole run if writing the visualizer file fails.
            pass
    elif animation_type == "btree" and extraction is not None:
        write_json(out_dir / "btree_extraction.json", extraction)
        try:
            write_btree_json(btree_json_path, extraction)
        except Exception:
            pass
    elif animation_type == "scheduler" and extraction is not None:
        write_json(out_dir / "scheduler_extraction.json", extraction)
        write_scheduler_processes_txt(scheduler_txt_path, extraction)

    write_json(out_dir / "final_result.json", result)

    print(f"Done. Results written under: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
