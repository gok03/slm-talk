"""LLM Supervisor: Qwen3.5:9b decides which A2A workers to call and in what order."""
from __future__ import annotations

import asyncio
import json
import time

import os
from pathlib import Path

# Load .env from demo_runner directory
_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

SUPERVISOR_LOCAL_MODEL = "qwen3.5:9b"
SUPERVISOR_CLOUD_MODEL = "qwen/qwen3.5-35b-a3b"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_active_queues: dict[str, asyncio.Queue] = {}


def _app():
    import sys
    return sys.modules.get("app") or sys.modules["__main__"]


def _q(run_id: str) -> asyncio.Queue | None:
    return _active_queues.get(run_id)


async def _post_task(worker: str, input_data: dict) -> str:
    a = _app()
    resp = await a.http_client.post(
        f"http://localhost:8000/workers/{worker}/tasks",
        json=input_data,
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()["task_id"]


async def _poll_task(worker: str, task_id: str, timeout_s: float = 300.0) -> dict:
    a = _app()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = await a.http_client.get(
            f"http://localhost:8000/workers/{worker}/tasks/{task_id}",
            timeout=5.0,
        )
        resp.raise_for_status()
        task_data = resp.json()
        state = task_data.get("state")
        if state == "completed":
            return task_data.get("output") or {}
        if state == "failed":
            raise RuntimeError(task_data.get("error", "worker failed"))
        await asyncio.sleep(0.5)
    raise TimeoutError(f"{worker} timed out after {timeout_s}s")


# ── A2A tool implementations ──────────────────────────────────────────────────

async def _call_ocr(run_id: str, file: str) -> dict:
    q = _q(run_id)
    if q:
        await q.put({"type": "step_start", "step": "ocr", "label": "OCR Worker — PaddleOCR-VL"})
        await q.put({"type": "token", "step": "supervisor", "text": "  → POST /workers/ocr/tasks\n"})
    t = time.perf_counter()
    task_id = await _post_task("ocr", {"file": file, "run_id": run_id})
    output = await _poll_task("ocr", task_id)
    dur = round(time.perf_counter() - t, 1)
    if q:
        await q.put({"type": "token", "step": "supervisor", "text": f"  ✓ ocr done ({dur}s)\n"})
    return {"markdown": output.get("markdown", "")}


async def _call_json(run_id: str, text: str) -> dict:
    q = _q(run_id)
    if q:
        await q.put({"type": "step_start", "step": "json", "label": "JSON Worker — NuExtract-2.0"})
        await q.put({"type": "token", "step": "supervisor", "text": "  → POST /workers/json/tasks\n"})
    t = time.perf_counter()
    task_id = await _post_task("json", {"text": text, "run_id": run_id})
    output = await _poll_task("json", task_id)
    dur = round(time.perf_counter() - t, 1)
    if q:
        await q.put({"type": "token", "step": "supervisor", "text": f"  ✓ json done ({dur}s)\n"})
    return {"invoice_json": output.get("json", {})}


async def _call_browser(run_id: str, invoice_json: dict, use_cloud: bool = False) -> dict:
    q = _q(run_id)
    model_label = SUPERVISOR_CLOUD_MODEL if use_cloud else SUPERVISOR_LOCAL_MODEL
    if q:
        await q.put({"type": "step_start", "step": "browser", "label": f"Browser Worker — {model_label} + Playwright MCP"})
        await q.put({"type": "token", "step": "supervisor", "text": "  → POST /workers/browser/tasks\n"})
    t = time.perf_counter()
    task_id = await _post_task("browser", {
        "invoice_json": invoice_json,
        "form_url": "http://localhost:8000/form",
        "run_id": run_id,
        "use_cloud": use_cloud,
    })
    output = await _poll_task("browser", task_id, timeout_s=300.0)
    dur = round(time.perf_counter() - t, 1)
    if q:
        await q.put({"type": "token", "step": "supervisor", "text": f"  ✓ browser done ({dur}s)\n"})
    return {"submitted": output.get("submitted", False)}


# ── Supervisor tool schema exposed to the LLM ─────────────────────────────────

SUPERVISOR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ocr_worker",
            "description": "Extract text from a PDF or image file using OCR. Returns markdown text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Filename in the assets directory"},
                },
                "required": ["file"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "json_worker",
            "description": "Extract structured invoice fields (invoice_number, date, total) from OCR text. Returns JSON.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "OCR markdown text to extract from"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_worker",
            "description": "Fill and submit the invoice form using the extracted invoice data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_json": {
                        "type": "object",
                        "description": "Invoice data with invoice_number, date, total",
                    },
                },
                "required": ["invoice_json"],
            },
        },
    },
]


# ── Main supervisor loop ───────────────────────────────────────────────────────

async def run_pipeline(run_id: str, pdf_file: str | None = None, invoice_json: dict | None = None, use_cloud: bool = False) -> None:
    """LLM supervisor: decides which workers to call via A2A tool-calling."""
    import sys
    model_label = SUPERVISOR_CLOUD_MODEL if use_cloud else SUPERVISOR_LOCAL_MODEL
    print(f"[supervisor] started run_id={run_id} file={pdf_file} has_json={bool(invoice_json)} model={model_label}", flush=True)

    a = _app()
    q = a.pipeline_queues.get(run_id)
    if q is None:
        print(f"[supervisor] ERROR: queue not found for {run_id}", file=sys.stderr, flush=True)
        return

    _active_queues[run_id] = q
    t_start = time.perf_counter()

    try:
        from pipeline.a2a import clear_all
        clear_all()

        # Build initial user message based on input type
        if invoice_json:
            user_content = (
                f"You have invoice data already extracted: {json.dumps(invoice_json)}. "
                "Submit it using the browser worker."
            )
        else:
            user_content = (
                f"Process the invoice file '{pdf_file}': "
                "first extract text with ocr_worker, then extract structured fields with json_worker, "
                "then submit the form with browser_worker."
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "/no_think\n"
                    "You are an invoice processing supervisor. "
                    "You have three workers available as tools: ocr_worker, json_worker, browser_worker. "
                    "Call them in the correct sequence to complete the task. "
                    "Pass outputs from one worker as inputs to the next."
                ),
            },
            {"role": "user", "content": user_content},
        ]

        await q.put({"type": "token", "step": "supervisor", "text": f"supervisor ({model_label}) started\n"})
        await q.put({"type": "token", "step": "supervisor", "text": f"task: {user_content[:80]}…\n"})

        max_iterations = 10
        for iteration in range(max_iterations):
            if use_cloud:
                resp = await a.http_client.post(
                    OPENROUTER_URL,
                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                    json={
                        "model": SUPERVISOR_CLOUD_MODEL,
                        "messages": messages,
                        "tools": SUPERVISOR_TOOLS,
                        "stream": False,
                    },
                    timeout=300.0,
                )
                resp.raise_for_status()
                choice = resp.json()["choices"][0]["message"]
                msg = {
                    "role": choice.get("role", "assistant"),
                    "content": choice.get("content") or "",
                    "tool_calls": choice.get("tool_calls"),
                }
            else:
                resp = await a.http_client.post(
                    "http://localhost:11434/api/chat",
                    json={
                        "model": SUPERVISOR_LOCAL_MODEL,
                        "messages": messages,
                        "tools": SUPERVISOR_TOOLS,
                        "stream": False,
                    },
                    timeout=300.0,
                )
                resp.raise_for_status()
                msg = resp.json()["message"]
            messages.append(msg)

            # Show supervisor reasoning if any
            content = msg.get("content", "").strip()
            if content:
                await q.put({"type": "token", "step": "supervisor", "text": f"{content}\n"})

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                break  # supervisor decided it's done

            for call in tool_calls:
                fn = call.get("function", {})
                tool_name = fn.get("name", "")
                tool_args = fn.get("arguments", {})
                if isinstance(tool_args, str):
                    try:
                        tool_args = json.loads(tool_args)
                    except json.JSONDecodeError:
                        tool_args = {}

                await q.put({"type": "token", "step": "supervisor", "text": f"→ {tool_name}()\n"})

                # Dispatch A2A tool call
                try:
                    if tool_name == "ocr_worker":
                        result = await _call_ocr(run_id, tool_args.get("file", ""))
                    elif tool_name == "json_worker":
                        result = await _call_json(run_id, tool_args.get("text", ""))
                    elif tool_name == "browser_worker":
                        result = await _call_browser(run_id, tool_args.get("invoice_json", {}), use_cloud)
                    else:
                        result = {"error": f"unknown tool: {tool_name}"}
                except Exception as exc:
                    result = {"error": str(exc)}
                    await q.put({"type": "token", "step": "supervisor", "text": f"  FAILED: {exc}\n"})

                messages.append({
                    "role": "tool",
                    "content": json.dumps(result),
                    "name": tool_name,
                })

        total_s = round(time.perf_counter() - t_start, 1)
        await q.put({"type": "token", "step": "supervisor", "text": "supervisor done\n"})
        await q.put({"type": "done", "metrics": {"total_s": total_s, "error": None}})
        print(f"[supervisor] done total_s={total_s}", flush=True)

    except Exception as exc:
        import traceback
        traceback.print_exc()
        try:
            await q.put({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        _active_queues.pop(run_id, None)
