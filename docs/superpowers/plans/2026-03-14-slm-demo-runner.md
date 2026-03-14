# SLM Demo Runner Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local FastAPI + plain HTML/JS web dashboard that runs 4 SLM demos live during PyConf Hyderabad 2026, streaming model output via SSE with real-time metrics.

**Architecture:** FastAPI backend handles two runtimes — MLX (via Python API) for Demos 1, 3, 4 and Ollama HTTP API for Demo 2 (vision). Each run gets a UUID-keyed async queue; a background task fills it with SSE token events; the stream endpoint drains it to the client. Model cache prevents repeated loading.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, mlx-lm, httpx, psutil, python-multipart; pure HTML/CSS/JS frontend (no build step, no CDN dependencies)

---

## File Map

```
demo_runner/
  requirements.txt          # all Python deps
  app.py                    # FastAPI app + all backend logic
  templates/
    index.html              # complete dashboard UI
  assets/
    sample_invoice.png      # default image for Demo 2 (user must supply)
```

---

## Chunk 1: Project Skeleton

### Task 1: requirements.txt

**Files:**
- Create: `demo_runner/requirements.txt`

- [ ] **Step 1: Write requirements.txt**

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
httpx>=0.27.0
python-multipart>=0.0.9
psutil>=5.9.0
mlx-lm>=0.16.0
jinja2>=3.1.0
```

- [ ] **Step 2: Verify install**

```bash
cd demo_runner && pip install -r requirements.txt
```
Expected: all packages install without error.

---

### Task 2: FastAPI skeleton + demo metadata

**Files:**
- Create: `demo_runner/app.py`

- [ ] **Step 1: Write the skeleton**

```python
import asyncio
import base64
import json
import subprocess
import time
import uuid
import webbrowser
from pathlib import Path
from typing import Optional

import httpx
import psutil
from fastapi import BackgroundTasks, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
ASSETS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="SLM Demo Runner")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ── In-memory state ──────────────────────────────────────────────────────────
run_queues: dict[str, asyncio.Queue] = {}
run_metrics: dict[str, dict] = {}
mlx_model_cache: dict[str, tuple] = {}   # model_name -> (model, tokenizer)
_mlx_load_lock = {}  # model_name -> asyncio.Lock (created on demand)

# ── Demo configuration ────────────────────────────────────────────────────────
DEMOS = {
    "1": {
        "title": "JSON Extraction",
        "subtitle": "Osmosis-Structure-0.6B",
        "runtime": "MLX",
        "params": "0.6B",
        "model": "mlx-community/Osmosis-Structure-0.6B-4bit",
        "cloud_cost": "GPT-4o: ~$0.02/call",
        "prompt": (
            'Extract the following fields as JSON from this text:\n\n'
            '"Invoice #INV-2024-0847 dated March 12, 2026. Bill to: Acme Corp,\n'
            '42 Innovation Drive, Bangalore 560001. Items: 3x GPU Server Rack\n'
            '($12,500 each), 1x Network Switch ($3,200), Setup fee $500.\n'
            'Payment terms: Net 30. Tax: 18% GST."\n\n'
            'Fields needed: invoice_number, date, company, address, '
            'line_items (array with name, quantity, unit_price), subtotal, tax_rate, total'
        ),
    },
    "2": {
        "title": "PDF / Document Extraction",
        "subtitle": "OCRFlux-3B",
        "runtime": "Ollama",
        "params": "3B",
        "model": "myaniu/OCRFlux-3B",
        "cloud_cost": "GPT-4V: ~$0.05/call",
        "prompt": (
            "Convert this document to clean Markdown. "
            "Preserve all table structures, headers, and formatting."
        ),
    },
    "3": {
        "title": "Reasoning + Thinking Mode",
        "subtitle": "SmolLM3-3B",
        "runtime": "MLX",
        "params": "3B",
        "model": "mlx-community/SmolLM3-3B-Instruct-4bit",
        "cloud_cost": "GPT-4o: ~$0.01/call",
        "prompt": (
            "A store offers a 20% discount on a jacket that originally costs $150.\n"
            "Then they apply an additional 15% discount on the already discounted price.\n"
            "A customer also has a $10 coupon.\n"
            "What is the final price? Is this better or worse than a single 35% discount?"
        ),
    },
    "4": {
        "title": "Code Generation",
        "subtitle": "Qwen2.5-Coder-7B",
        "runtime": "MLX",
        "params": "7B",
        "model": "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
        "cloud_cost": "GitHub Copilot: ~$10/month",
        "prompt": (
            'Write a Python FastAPI endpoint that:\n'
            '1. Accepts a POST request with a JSON body containing "text" and "language" fields\n'
            '2. Uses a simple rule-based approach to count sentences, words, and characters\n'
            '3. Returns a JSON response with the analysis results\n'
            '4. Includes proper error handling and type hints\n'
            '5. Add a health check endpoint\n\n'
            'Include the complete runnable file with imports.'
        ),
    },
}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "demos": DEMOS})


@app.get("/api/demos")
async def list_demos():
    return DEMOS


if __name__ == "__main__":
    import uvicorn
    webbrowser.open("http://localhost:8000", new=2)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
```

- [ ] **Step 2: Smoke test**

```bash
cd demo_runner && python app.py
```
Expected: Server starts, browser opens at http://localhost:8000 (shows error or empty page — templates not built yet, that's fine). Ctrl+C to stop.

- [ ] **Step 3: Commit**

```bash
git add demo_runner/requirements.txt demo_runner/app.py
git commit -m "feat: add demo runner skeleton with demo metadata"
```

---

## Chunk 2: MLX Backend

### Task 3: MLX model loading + streaming

**Files:**
- Modify: `demo_runner/app.py` (add MLX functions + routes)

- [ ] **Step 1: Add MLX helper functions to app.py**

Add after the `DEMOS` dict:

```python
# ── MLX helpers ──────────────────────────────────────────────────────────────

def _get_mlx_lock(model_name: str) -> asyncio.Lock:
    if model_name not in _mlx_load_lock:
        _mlx_load_lock[model_name] = asyncio.Lock()
    return _mlx_load_lock[model_name]


async def _load_mlx_model(model_name: str) -> tuple:
    """Load and cache an MLX model. Thread-safe."""
    if model_name in mlx_model_cache:
        return mlx_model_cache[model_name]
    async with _get_mlx_lock(model_name):
        if model_name in mlx_model_cache:  # double-check
            return mlx_model_cache[model_name]
        loop = asyncio.get_event_loop()
        model, tokenizer = await loop.run_in_executor(
            None, _load_mlx_blocking, model_name
        )
        mlx_model_cache[model_name] = (model, tokenizer)
        return model, tokenizer


def _load_mlx_blocking(model_name: str) -> tuple:
    from mlx_lm import load
    return load(model_name)


def _mlx_format_prompt(tokenizer, prompt: str) -> str:
    """Apply chat template if available."""
    if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template:
        messages = [{"role": "user", "content": prompt}]
        return tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    return prompt


def _mlx_stream_blocking(run_id: str, model_name: str, prompt: str, loop: asyncio.AbstractEventLoop) -> None:
    """Generate with MLX in a worker thread, pushing SSE events to the run queue."""
    try:
        from mlx_lm import stream_generate
    except ImportError:
        from mlx_lm.utils import stream_generate

    queue = run_queues[run_id]

    def _push(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    try:
        model, tokenizer = mlx_model_cache[model_name]
        formatted = _mlx_format_prompt(tokenizer, prompt)

        t_start = time.perf_counter()
        first_token_at: Optional[float] = None
        token_count = 0

        for response in stream_generate(model, tokenizer, formatted, max_tokens=2048):
            token_text = response.text
            if not token_text:
                continue
            if first_token_at is None:
                first_token_at = time.perf_counter() - t_start
            token_count += 1
            _push({"type": "token", "text": token_text})

        t_total = time.perf_counter() - t_start
        gen_duration = t_total - (first_token_at or 0)
        gen_tps = round(token_count / gen_duration) if gen_duration > 0 else 0
        ram_mb = round(psutil.Process().memory_info().rss / (1024 * 1024))

        metrics = {
            "ttft_ms": round((first_token_at or 0) * 1000),
            "total_s": round(t_total, 1),
            "gen_tps": gen_tps,
            "ram_mb": ram_mb,
            "token_count": token_count,
        }
        run_metrics[run_id] = metrics
        _push({"type": "done", "metrics": metrics})

    except Exception as exc:
        _push({"type": "error", "message": str(exc)})


async def _run_mlx(run_id: str, model_name: str, prompt: str) -> None:
    """Background task: loads model then streams."""
    try:
        await _load_mlx_model(model_name)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, _mlx_stream_blocking, run_id, model_name, prompt, loop
        )
    except Exception as exc:
        queue = run_queues.get(run_id)
        if queue:
            await queue.put({"type": "error", "message": str(exc)})
```

- [ ] **Step 2: Add the /api/run and /api/stream routes**

```python
# ── API routes ────────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    prompt: str
    think_mode: Optional[str] = None   # "think" | "no_think" | None
    image_b64: Optional[str] = None


@app.post("/api/run/{demo_id}")
async def start_run(
    demo_id: str,
    body: RunRequest,
    background_tasks: BackgroundTasks,
):
    demo = DEMOS.get(demo_id)
    if not demo:
        return JSONResponse({"error": "unknown demo"}, status_code=404)

    run_id = str(uuid.uuid4())
    run_queues[run_id] = asyncio.Queue()

    prompt = body.prompt
    if demo_id == "3" and body.think_mode:
        prefix = f"/{body.think_mode}\n"
        prompt = prefix + prompt

    if demo["runtime"] == "MLX":
        background_tasks.add_task(_run_mlx, run_id, demo["model"], prompt)
    else:
        background_tasks.add_task(_run_ollama, run_id, demo["model"], prompt, body.image_b64)

    return {"run_id": run_id}


@app.get("/api/stream/{run_id}")
async def stream_run(run_id: str):
    queue = run_queues.get(run_id)
    if not queue:
        return JSONResponse({"error": "run not found"}, status_code=404)

    async def event_gen():
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=120)
                except asyncio.TimeoutError:
                    yield "data: " + json.dumps({"type": "error", "message": "timeout"}) + "\n\n"
                    break
                yield "data: " + json.dumps(item) + "\n\n"
                if item["type"] in ("done", "error"):
                    break
        finally:
            run_queues.pop(run_id, None)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

Also add `from pydantic import BaseModel` to the imports at the top.

- [ ] **Step 3: Quick manual test**

Start the server. POST to `/api/run/1` with `{"prompt": "Say hi"}`. GET `/api/stream/<run_id>` and verify tokens stream in. (Demo 1 model must be downloaded first.)

- [ ] **Step 4: Commit**

```bash
git add demo_runner/app.py
git commit -m "feat: add MLX streaming backend for demos 1, 3, 4"
```

---

## Chunk 3: Ollama Backend (Demo 2)

### Task 4: Ollama streaming + file upload + health check

**Files:**
- Modify: `demo_runner/app.py`

- [ ] **Step 1: Add Ollama helper functions**

```python
# ── Ollama helpers ────────────────────────────────────────────────────────────

_uploaded_image_path: Optional[Path] = None  # set by /api/upload


async def _run_ollama(
    run_id: str,
    model_name: str,
    prompt: str,
    image_b64: Optional[str],
) -> None:
    queue = run_queues[run_id]
    t_start = time.perf_counter()
    first_token_at: Optional[float] = None
    token_count = 0

    # Use default image if none provided
    if not image_b64:
        default = ASSETS_DIR / "sample_invoice.png"
        if default.exists():
            image_b64 = base64.b64encode(default.read_bytes()).decode()

    payload: dict = {"model": model_name, "prompt": prompt, "stream": True}
    if image_b64:
        payload["images"] = [image_b64]

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST", "http://localhost:11434/api/generate", json=payload
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    token = data.get("response", "")
                    if token:
                        if first_token_at is None:
                            first_token_at = time.perf_counter() - t_start
                        token_count += 1
                        await queue.put({"type": "token", "text": token})
                    if data.get("done"):
                        break

        t_total = time.perf_counter() - t_start
        vram_mb = _get_ollama_vram_mb()
        metrics = {
            "ttft_ms": round((first_token_at or 0) * 1000),
            "total_s": round(t_total, 1),
            "token_count": token_count,
            "vram_mb": vram_mb,
        }
        run_metrics[run_id] = metrics
        await queue.put({"type": "done", "metrics": metrics})

    except Exception as exc:
        await queue.put({"type": "error", "message": str(exc)})


def _get_ollama_vram_mb() -> Optional[int]:
    """Parse `ollama ps` output for VRAM usage."""
    try:
        out = subprocess.check_output(["ollama", "ps"], text=True, timeout=5)
        for line in out.splitlines()[1:]:  # skip header
            parts = line.split()
            if len(parts) >= 4:
                size_str = parts[3]  # e.g. "3.2 GB"
                # ollama ps prints size and unit as adjacent fields sometimes
                # parse conservatively
                for i, p in enumerate(parts):
                    if p in ("GB", "GiB") and i > 0:
                        try:
                            return round(float(parts[i - 1]) * 1024)
                        except ValueError:
                            pass
                    if p in ("MB", "MiB") and i > 0:
                        try:
                            return round(float(parts[i - 1]))
                        except ValueError:
                            pass
    except Exception:
        pass
    return None
```

- [ ] **Step 2: Add file upload + health endpoints**

```python
@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    global _uploaded_image_path
    suffix = Path(file.filename).suffix or ".png"
    dest = ASSETS_DIR / f"upload{suffix}"
    dest.write_bytes(await file.read())
    _uploaded_image_path = dest
    return {"path": str(dest)}


@app.get("/api/health")
async def health():
    status: dict[str, dict] = {}
    for demo_id, demo in DEMOS.items():
        if demo["runtime"] == "MLX":
            ok = _check_mlx_cached(demo["model"])
        else:
            ok = await _check_ollama_model(demo["model"])
        status[demo_id] = {"ok": ok, "runtime": demo["runtime"], "model": demo["model"]}
    return status


def _check_mlx_cached(model_name: str) -> bool:
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    dir_name = "models--" + model_name.replace("/", "--")
    return (hf_cache / dir_name).exists()


async def _check_ollama_model(model_name: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            names = [m["name"] for m in resp.json().get("models", [])]
            return any(n.startswith(model_name.split(":")[0]) for n in names)
    except Exception:
        return False
```

- [ ] **Step 3: Commit**

```bash
git add demo_runner/app.py
git commit -m "feat: add Ollama backend, file upload, and health check"
```

---

## Chunk 4: Frontend

### Task 5: index.html — full dashboard

**Files:**
- Create: `demo_runner/templates/index.html`

- [ ] **Step 1: Write the complete HTML file**

See full file content in implementation section. Key structure:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>SLM Demo Runner — PyConf Hyderabad 2026</title>
  <style>/* dark theme, layout, panels */</style>
</head>
<body>
  <header>SLM Demo Runner | PyConf Hyderabad 2026</header>
  <div class="layout">
    <nav class="sidebar">
      <!-- Demo nav items with health dots -->
    </nav>
    <main>
      <!-- Demo 1, 2, 4: standard panel -->
      <!-- Demo 3: split panel -->
    </main>
  </div>
  <script>/* SSE client, keyboard shortcuts, health polling */</script>
</body>
</html>
```

Panels included:
- **Demo 1, 2, 4**: model badge, editable textarea, Run button, output div, metrics strip
- **Demo 2 extra**: file drop zone, default-file indicator
- **Demo 3**: two columns (no_think / think), each with own Run button + output + metrics; shared "Run Both" button

JS responsibilities:
- `switchDemo(id)` — show/hide panels, update sidebar active state
- `runDemo(demoId, thinkMode?)` — POST to `/api/run`, then `EventSource` on `/api/stream`
- `renderToken(el, text)` — append to output, style `<think>` tags as dim/italic
- `renderMetrics(el, metrics, runtime)` — format and show metrics strip
- `pollHealth()` — GET `/api/health` on load, set sidebar dots
- Keyboard: `1`–`4` switch, `R` run, `C` clear

- [ ] **Step 2: Verify in browser**

Start server and open http://localhost:8000. Check:
- Sidebar shows all 4 demos, health dots populated after 1s
- Clicking a demo switches the panel
- Keyboard `1`–`4`, `R`, `C` work
- Run a demo (if models downloaded) and verify streaming output + metrics

- [ ] **Step 3: Test Demo 3 split view specifically**

- Click Demo 3
- Click "Run Direct" — left panel streams
- Click "Run with Think" — right panel streams with dim `<think>` text
- Metrics rows appear in the bottom strip

- [ ] **Step 4: Test Demo 2 file upload**

- Default image indicator shows
- Upload a PNG — thumbnail previews, indicator updates
- Run — model receives image (check server logs)

- [ ] **Step 5: Commit**

```bash
git add demo_runner/templates/index.html
git commit -m "feat: add web dashboard frontend"
```

---

## Chunk 5: Polish + Startup

### Task 6: Final polish

**Files:**
- Modify: `demo_runner/app.py` (startup message)
- Create: `demo_runner/README.md`

- [ ] **Step 1: Add startup log to app.py**

In `__main__` block:
```python
print("─" * 50)
print("  SLM Demo Runner — PyConf Hyderabad 2026")
print("─" * 50)
print("  URL: http://localhost:8000")
print()
print("  Models (auto-download from HuggingFace on first run):")
for d in DEMOS.values():
    print(f"    [{d['runtime']}] {d['subtitle']} — {d['model']}")
print()
print("  Tip: WiFi can be OFF — all calls are local")
print("─" * 50)
```

- [ ] **Step 2: End-to-end verification**

Run full verification from the plan:
1. `python app.py` starts, browser opens
2. Health dots — green for available models
3. Demo 1 → JSON output streams, >200 tok/s shown
4. Demo 2 → Markdown output streams (requires `ollama pull myaniu/OCRFlux-3B`)
5. Demo 3 → both panels stream; think panel shows dim `<think>` text
6. Demo 4 → FastAPI code streams
7. Keys `1-4`, `R`, `C` all work
8. Disable network → all demos still work

- [ ] **Step 3: Final commit**

```bash
git add demo_runner/
git commit -m "feat: complete SLM demo runner for PyConf Hyderabad 2026"
```

---

## Quick-Start for Day of Talk

```bash
cd demo_runner
pip install -r requirements.txt
ollama pull myaniu/OCRFlux-3B      # only Ollama model needed
python app.py                       # MLX models download on first run
```

Open http://localhost:8000. Run each demo once the night before to warm the model cache. Turn off WiFi. Good luck!
