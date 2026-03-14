# Multi-Agent SLM Pipeline — Design Spec

**Date**: 2026-03-14
**Talk**: Small Models, Big Impact — PyConf Hyderabad 2026
**Status**: Draft

---

## Context

The individual model demos (Demos 1–5) show SLMs in isolation. The pipeline is the talk's climax — three SLMs orchestrated by a supervisor, communicating via A2A protocol, using MCP for browser automation, running entirely on a laptop with WiFi off.

This is built as a separate page (`/pipeline`) in the existing `demo_runner` FastAPI server — same `python app.py` command, new URL, distinct visual identity.

---

## What It Does

**Input**: A PDF invoice (e.g. `invoice-3-0.pdf` — one of the existing assets)
**Output**: A local HTML form filled with the extracted invoice data

**Three steps**:
1. **OCR Worker** — PaddleOCR-VL-1.5 (0.9B, MLX-VLM) reads the PDF page image, outputs Markdown
2. **JSON Worker** — NuExtract-2.0 (2B, Ollama) structures the Markdown into validated JSON
3. **Browser Worker** — Qwen3.5:4b (Ollama) + Playwright MCP navigates to `/form`, fills fields, submits

**Orchestrator**: LangGraph supervisor (Qwen3.5:4b) dispatches A2A tasks to each worker sequentially, validates results, and re-dispatches on failure.

---

## Architecture

```
demo_runner/
├── app.py                        ← add /pipeline, /form, A2A routes, pipeline run/stream
├── pipeline/
│   ├── __init__.py
│   ├── a2a.py                    ← AgentCard, Task, TaskState, TaskStore
│   ├── workers.py                ← OCR / JSON / Browser worker task handlers
│   └── supervisor.py             ← LangGraph graph (PipelineState + 3 nodes)
├── templates/
│   ├── pipeline.html             ← standalone pipeline dashboard
│   └── form.html                 ← local invoice form (Playwright target)
```

---

## A2A Protocol (`pipeline/a2a.py`)

Minimal spec-compliant implementation. No external SDK.

**Types**:
```python
TaskState = Literal["submitted", "working", "completed", "failed"]

@dataclass
class Task:
    id: str
    state: TaskState
    input: dict
    output: dict | None = None
    error: str | None = None

@dataclass
class AgentCard:
    name: str
    description: str
    url: str          # base URL of the worker
    capabilities: list[str]
```

**In-memory TaskStore**: `dict[task_id, Task]` — one per worker, cleared between pipeline runs.

**Routes added to `app.py`** (one set per worker):
```
GET  /workers/{name}/agent.json         → AgentCard
POST /workers/{name}/tasks              → create Task, return {task_id}
GET  /workers/{name}/tasks/{task_id}    → Task (state + output)
```

---

## Queue Architecture

**Separate queues for pipeline vs demo runs**:

- `run_queues: dict[str, asyncio.Queue]` — existing, used by demos 1–5, not touched
- `pipeline_queues: dict[str, asyncio.Queue]` — new, used exclusively by pipeline runs

`pipeline_queues[run_id]` is created in `POST /pipeline/run` with `maxsize=1024` (more producers than demo runs). It is **not** deleted on SSE disconnect — only deleted after the SSE generator sends the terminal `done` event to the client. This allows the browser tab to reconnect mid-run and resume the stream.

```python
pipeline_queues: dict[str, asyncio.Queue] = {}
```

**A single module-level `httpx.AsyncClient`** is used for all supervisor polling and self-calls:
```python
http_client = httpx.AsyncClient(timeout=30.0)
```
Not a per-call context manager — avoids creating/destroying up to 720 connections per pipeline run.

---

## Workers (`pipeline/workers.py`)

Each worker is a Python async function triggered by `POST /workers/{name}/tasks`. Runs as `asyncio.create_task()`. Updates its Task state in TaskStore as it progresses.

**Queue access**: Workers do **not** call `_run_mlx_vlm()` or `_run_ollama()` unchanged, because those functions do `queue = run_queues[run_id]` directly. Both the async wrapper functions (`_run_mlx_vlm`, `_run_ollama`) and the blocking helper (`_mlx_vlm_stream_blocking`) are modified to accept an optional `queue_store` parameter (defaults to `run_queues` for backward compat):

```python
# _mlx_vlm_stream_blocking (blocking helper called in executor)
def _mlx_vlm_stream_blocking(run_id: str, ..., queue_store=None):
    queue_store = queue_store or run_queues
    queue = queue_store[run_id]
    ...

# _run_mlx_vlm (async wrapper)
async def _run_mlx_vlm(run_id: str, ..., queue_store=None):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _mlx_vlm_stream_blocking, run_id, ..., queue_store)

# _run_ollama (async)
async def _run_ollama(run_id: str, ..., queue_store=None):
    queue_store = queue_store or run_queues
    queue = queue_store[run_id]
    ...
```

**OCR Worker**
- Calls `_run_mlx_vlm()` with `queue_store=pipeline_queues` and the step-tagged events
- Input: `{file: filename, run_id: str}`
- Output: `{markdown: str}`
- Temp PNG path: `ASSETS_DIR / f"_tmp_{run_id}_{file_path.stem}.png"` (run_id-scoped to prevent race with concurrent Demo 2)

**JSON Worker**
- Calls `_run_ollama()` with `queue_store=pipeline_queues`
- Model: NuExtract-2.0, with `raw=True`
- Prompt construction wraps OCR Markdown in NuExtract-2.0 template format (matches existing Demo 1 format in `app.py`):
  ```
  <|input|>
  ### Template:
  {"invoice_number": "", "date": "", "vendor": {"name": "", "address": ""},
   "line_items": [{"description": "", "quantity": 0, "unit_price": 0}],
   "tax_rate": "", "total": ""}

  ### Text:
  {ocr_markdown}
  <|output|>
  ```
- Input: `{text: str, run_id: str}`
- Output: `{json: dict}` — parsed from model response, validated as JSON before marking completed

**Browser Worker** (new — see detail below)
- Input: `{invoice_json: dict, form_url: str, run_id: str}`
- Output: `{submitted: bool}`

---

## Browser Worker Detail

The Browser Worker orchestrates Playwright MCP via stdio and Qwen3.5:4b via Ollama's `/api/chat` endpoint (not `/api/generate`) in a tool-calling loop.

### Playwright MCP subprocess

```python
PLAYWRIGHT_MCP_VERSION = "0.0.29"  # pinned for offline use

proc = await asyncio.create_subprocess_exec(
    "npx", f"@playwright/mcp@{PLAYWRIGHT_MCP_VERSION}", "--headless",
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
)
```

Always wrap in `try/finally` to terminate the subprocess:
```python
try:
    # ... tool-calling loop ...
finally:
    proc.terminate()
    await proc.wait()
```

### MCP stdio initialization (JSON-RPC 2.0)

`mcp_call()` reads lines in a loop until it finds a line that parses as JSON with a matching `id` — this handles stdout noise (log lines, warnings) emitted by the Node.js process:

```python
_mcp_id = 0

async def mcp_call(proc, method, params=None):
    global _mcp_id
    _mcp_id += 1
    req_id = _mcp_id
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    proc.stdin.write((json.dumps(msg) + "\n").encode())
    await proc.stdin.drain()
    while True:
        line = await proc.stdout.readline()
        if not line:
            raise EOFError("MCP process closed")
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue  # skip log lines, warnings, etc.
        if data.get("id") == req_id:
            if "error" in data:
                raise RuntimeError(f"MCP error: {data['error']}")
            return data.get("result")
```

Initialization sequence:
```python
# 1. initialize
await mcp_call(proc, "initialize", {
    "protocolVersion": "2024-11-05",
    "clientInfo": {"name": "browser-worker", "version": "1.0"},
    "capabilities": {}
})

# 2. REQUIRED: send notifications/initialized (fire-and-forget, no id, no response)
notif = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
proc.stdin.write(notif.encode())
await proc.stdin.drain()

# 3. list available tools
tools_result = await mcp_call(proc, "tools/list")
playwright_tools = tools_result["tools"]  # list of {name, description, inputSchema}
```

### Ollama tool-calling loop

```python
ollama_tools = [
    {"type": "function", "function": {
        "name": t["name"],
        "description": t["description"],
        "parameters": t["inputSchema"]
    }} for t in playwright_tools
]

messages = [
    {"role": "system", "content": "You are a browser automation agent. Fill out the invoice form and submit it."},
    {"role": "user", "content": f"Fill the form at {form_url} with this data: {json.dumps(invoice_json)}. Submit when all fields are filled."}
]

while True:
    resp = await http_client.post(
        "http://localhost:11434/api/chat",
        json={"model": "qwen3.5:4b", "messages": messages, "tools": ollama_tools, "stream": False},
        timeout=60.0
    )
    msg = resp.json()["message"]
    messages.append(msg)

    if not msg.get("tool_calls"):
        break  # model has no more tool calls

    for call in msg["tool_calls"]:
        tool_name = call["function"]["name"]
        tool_args = call["function"]["arguments"]

        # emit log event
        await pipeline_queues[run_id].put(
            {"type": "token", "step": "browser", "text": f"{tool_name} ✓\n"}
        )

        # execute via MCP
        result = await mcp_call(proc, "tools/call", {"name": tool_name, "arguments": tool_args})
        messages.append({"role": "tool", "content": json.dumps(result), "name": tool_name})

# After loop: check for submission success via final snapshot
snapshot = await mcp_call(proc, "tools/call", {"name": "browser_snapshot", "arguments": {}})
submitted = "submit-banner" in str(snapshot) or "Submitted" in str(snapshot)
return {"submitted": submitted}
```

---

## Supervisor (`pipeline/supervisor.py`)

```python
class PipelineState(TypedDict):
    pdf_file: str
    run_id: str
    raw_text: str
    invoice_json: dict
    form_submitted: bool
    error: str | None
```

**Graph**: `START → ocr_node → json_node → browser_node → END`

Each node:
1. Posts A2A task: `await http_client.post("http://localhost:8000/workers/{name}/tasks", json=input)`
2. Pushes SSE event directly into `pipeline_queues[run_id]`: `{type: "step_start", step: "ocr", label: "..."}`
3. Polls task status via `GET /workers/{name}/tasks/{task_id}` (0.5s interval, 120s timeout)
4. On failure: sets `state["error"]`, routes to END

**Note on self-calls**: Worker POST routes return immediately (`asyncio.create_task()` fires and returns). Polling uses `await asyncio.sleep(0.5)` which yields the event loop. No deadlock risk in a single-process asyncio server.

**New SSE event types** (extend existing protocol):
```json
{"type": "step_start",  "step": "ocr",  "label": "OCR Worker — PaddleOCR-VL"}
{"type": "token",       "step": "ocr",  "text": "# Invoice…"}
{"type": "step_done",   "step": "ocr",  "duration_s": 8.2}
{"type": "step_error",  "step": "json", "message": "validation failed"}
{"type": "done",        "metrics": {"total_s": 42.1, "steps": {...}}}
```

The frontend routes each event to the correct column by the `step` field value (`"supervisor"`, `"ocr"`, `"json"`, `"browser"`).

**New routes in `app.py`**:
```
POST /pipeline/run              → {run_id} (starts supervisor as asyncio task)
GET  /pipeline/stream/{run_id}  → SSE (reads from pipeline_queues[run_id])
GET  /pipeline                  → pipeline.html
GET  /form                      → form.html
POST /form/submit               → stores submitted data in memory, returns {ok: true}
```

**Queue cleanup**: The SSE generator owns queue deletion — not the supervisor. After the generator yields the `done` event to the client, it calls `pipeline_queues.pop(run_id, None)`. The supervisor only puts events; it never deletes. This matches the existing `run_queues` cleanup pattern in `app.py`.

---

## Frontend (`templates/pipeline.html`)

Standalone dark page, separate from `index.html`. Accessed at `localhost:8000/pipeline`.

**Layout**: 4-column grid (Supervisor · OCR Worker · JSON Worker · Browser Worker)

**Each column**:
- Header: worker name, model badge, status dot + label (waiting/running/done/error)
- Log area: interleaved A2A protocol messages (dim `#8b949e`) + model tokens (bright `#c9d1d9`)
- Footer: model name, runtime, tokens/sec (when done)

**Browser Worker column extras**:
- Log area (top ~40%)
- `<iframe src="/form" id="form-frame">` (bottom ~60%)

**Iframe live update**: Playwright runs in a separate headless Chrome — it does not share the dashboard's browser context. The iframe does not reflect Playwright's actions in real time. Instead:
- The log area shows structured token events (`fill: vendor_name ✓`) as progress
- After `POST /form/submit` completes, the pipeline emits a `step_done` event for `browser`; the frontend calls `document.getElementById("form-frame").contentWindow.location.reload()` to show the confirmation banner

**Controls**: `[▶ Run Pipeline]` button, file picker (reuses `/api/files`), `[Stop]` button

**Metrics bar** (bottom): `OCR 8.2s · JSON 6.4s · Browser 27.5s · Total 42.1s · $0.00`

**Keyboard shortcuts**: `R` run, `D` clear, `S` stop

---

## Local Form (`templates/form.html`)

Simple HTML form served at `/form`. Fields match invoice JSON schema:
- Invoice number, date
- Vendor name, address
- Line items table (dynamic rows)
- Tax rate, total

On submit: `POST /form/submit` stores data in memory, returns `{ok: true}`, and the page shows a confirmation banner with `id="submit-banner"`. Playwright checks for `#submit-banner` in the snapshot to confirm success.

---

## New Dependencies

```
langgraph>=0.2.0,<0.3.0    # supervisor graph (pin minor to avoid breaking API changes)
httpx>=0.27.0               # already present; module-level client added for pipeline
```

Playwright MCP server: `npx @playwright/mcp@0.0.29` (pinned, no Python install needed).

**Pre-talk setup**: Run `npx @playwright/mcp@0.0.29 --version` once while online to cache in `~/.npm`. After that, runs offline. Version constant: `PLAYWRIGHT_MCP_VERSION = "0.0.29"` in `pipeline/workers.py`.

---

## Modifications to existing `app.py`

| What | Change |
|------|--------|
| `_run_mlx_vlm()` | Add `queue_store=None` parameter; default to `run_queues` |
| `_run_ollama()` | Add `queue_store=None` parameter; default to `run_queues` |
| Module level | Add `pipeline_queues: dict[str, asyncio.Queue] = {}` |
| Module level | Add `http_client = httpx.AsyncClient(timeout=30.0)` |
| `/api/stream/{run_id}` | Unchanged (reads `run_queues`) |
| `/pipeline/stream/{run_id}` | New; reads `pipeline_queues`; SSE generator pops queue after forwarding `done` |

---

## Verification

1. `python app.py` → `localhost:8000/pipeline` loads the 4-column dashboard
2. `localhost:8000/form` shows the blank invoice form
3. Select `invoice-3-0.pdf`, click Run Pipeline
4. Supervisor column streams LangGraph steps
5. OCR column: dim A2A messages interleaved with Markdown tokens streaming in
6. JSON column: activates after OCR done, NuExtract JSON streams in
7. Browser column: tool-call log streams (`fill: vendor ✓`, etc.), iframe reloads showing submitted form
8. Metrics bar shows total time, $0.00
9. Stop button cancels mid-run cleanly
10. WiFi OFF — entire run completes (Playwright MCP pre-cached, all models local)
