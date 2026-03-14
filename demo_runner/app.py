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
from pydantic import BaseModel

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
ASSETS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="SLM Demo Runner")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ── In-memory state ──────────────────────────────────────────────────────────
run_queues: dict[str, asyncio.Queue] = {}
run_metrics: dict[str, dict] = {}
run_cancelled: set[str] = set()
run_tasks: dict[str, asyncio.Task] = {}   # run_id -> asyncio Task (for cancellation)
mlx_model_cache: dict[str, tuple] = {}     # model_name -> (model, tokenizer)
mlx_vlm_cache: dict[str, tuple] = {}      # model_name -> (model, processor, config)
hf_model_cache: dict[str, tuple] = {}     # model_name -> (model, processor)
_mlx_load_locks: dict[str, asyncio.Lock] = {}
_mlx_vlm_load_locks: dict[str, asyncio.Lock] = {}
_hf_load_locks: dict[str, asyncio.Lock] = {}
_uploaded_image_path: Optional[Path] = None

# ── Demo configuration ────────────────────────────────────────────────────────
DEMOS: dict[str, dict] = {
    "1": {
        "title": "JSON Parsing",
        "subtitle": "NuExtract-2.0-2B",
        "runtime": "Ollama",
        "params": "2B",
        "model": "hf.co/numind/NuExtract-2.0-2B-GGUF",
        "cloud_cost": "GPT-4o: ~$0.02/call",
        "system": None,
        "raw": True,
        "prompt": (
            '<|input|>\n'
            '### Template:\n'
            '{\n'
            '  "invoice_number": "",\n'
            '  "date": "",\n'
            '  "company": "",\n'
            '  "address": "",\n'
            '  "line_items": [{"name": "", "quantity": 0, "unit_price": 0}],\n'
            '  "tax_rate": 0\n'
            '}\n\n'
            '### Text:\n'
            'Invoice #INV-2026-042 dated March 14, 2026. Bill to: NovaTech Solutions,\n'
            '88 MG Road, Bangalore 560001. Items: 2x Developer Laptop M4 Pro\n'
            '(95,000 each), 1x 4K Monitor (35,000), 3x Mechanical Keyboard (8,500 each).\n'
            'Payment terms: Net 30. Tax: 18% GST.\n'
            '<|output|>\n'
        ),
    },
    "2": {
        "title": "PDF Extraction",
        "subtitle": "PaddleOCR-VL-1.5",
        "runtime": "MLX-VLM",
        "params": "0.9B",
        "model": "mlx-community/PaddleOCR-VL-1.5-4bit",
        "cloud_cost": "GPT-4V: ~$0.05/call",
        "vision": True,
        "prompt": "OCR:",
    },
    "3": {
        "title": "General Reasoning",
        "subtitle": "Qwen3.5-2B",
        "runtime": "Ollama",
        "params": "2B",
        "model": "qwen3.5:2b",
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
        "subtitle": "Qwen3.5-4B",
        "runtime": "Ollama",
        "params": "4B",
        "model": "qwen3.5:4b",
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
    "5": {
        "title": "Multilingual",
        "subtitle": "Tiny Aya Fire",
        "runtime": "Ollama",
        "params": "3B",
        "model": "tiny-aya-fire",
        "cloud_cost": "GPT-4o: ~$0.01/call",
        "prompt": (
            "Explain what a 'small language model' is in 4 languages:\n"
            "1. English\n"
            "2. Hindi (हिंदी)\n"
            "3. Tamil (தமிழ்)\n"
            "4. Telugu (తెలుగు)\n\n"
            "Keep each explanation to 2 sentences."
        ),
    },
}


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "demos": DEMOS})


@app.get("/api/demos")
async def list_demos():
    return DEMOS


# ── MLX helpers ───────────────────────────────────────────────────────────────

def _get_mlx_lock(model_name: str) -> asyncio.Lock:
    return _mlx_load_locks.setdefault(model_name, asyncio.Lock())


async def _load_mlx_model(model_name: str) -> tuple:
    """Load and cache an MLX model. Safe for concurrent calls."""
    if model_name in mlx_model_cache:
        return mlx_model_cache[model_name]
    async with _get_mlx_lock(model_name):
        if model_name in mlx_model_cache:  # double-check after acquiring lock
            return mlx_model_cache[model_name]
        loop = asyncio.get_event_loop()
        model, tokenizer = await loop.run_in_executor(None, _load_mlx_blocking, model_name)
        mlx_model_cache[model_name] = (model, tokenizer)
        return model, tokenizer


def _load_mlx_blocking(model_name: str) -> tuple:
    from mlx_lm import load
    return load(model_name)


def _mlx_format_prompt(tokenizer, prompt: str) -> str:
    """Apply chat template if available, otherwise return raw prompt."""
    if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template:
        messages = [{"role": "user", "content": prompt}]
        return tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    return prompt


def _mlx_stream_blocking(
    run_id: str,
    model_name: str,
    prompt: str,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Run MLX generation in a worker thread. Pushes SSE events to the run queue."""
    try:
        from mlx_lm import stream_generate
    except ImportError:
        from mlx_lm.utils import stream_generate  # older versions

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
            if run_id in run_cancelled:
                break
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
        _push({"type": "done", "metrics": metrics, "runtime": "MLX"})

    except Exception as exc:
        _push({"type": "error", "message": str(exc)})


async def _run_mlx(run_id: str, model_name: str, prompt: str) -> None:
    """Background task: loads model then streams generation."""
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


# ── MLX-VLM helpers (vision models) ──────────────────────────────────────────

def _load_mlx_vlm_blocking(model_name: str) -> tuple:
    from mlx_vlm import load
    from mlx_vlm.utils import load_config
    model, processor = load(model_name)
    config = load_config(model_name)
    return model, processor, config


async def _load_mlx_vlm_model(model_name: str) -> tuple:
    if model_name in mlx_vlm_cache:
        return mlx_vlm_cache[model_name]
    lock = _mlx_vlm_load_locks.setdefault(model_name, asyncio.Lock())
    async with lock:
        if model_name in mlx_vlm_cache:
            return mlx_vlm_cache[model_name]
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _load_mlx_vlm_blocking, model_name)
        mlx_vlm_cache[model_name] = result
        return result


def _mlx_vlm_stream_blocking(
    run_id: str,
    model_name: str,
    prompt: str,
    image_path: str,
    loop: asyncio.AbstractEventLoop,
) -> None:
    from mlx_vlm import stream_generate
    from mlx_vlm.prompt_utils import apply_chat_template

    queue = run_queues[run_id]

    def _push(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    try:
        model, processor, config = mlx_vlm_cache[model_name]
        formatted = apply_chat_template(processor, config, prompt, num_images=1)

        t_start = time.perf_counter()
        first_token_at: Optional[float] = None
        token_count = 0

        for result in stream_generate(model, processor, formatted, image=image_path, max_tokens=2048):
            if run_id in run_cancelled:
                break
            token_text = result.text
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
        _push({"type": "done", "metrics": metrics, "runtime": "MLX-VLM"})

    except Exception as exc:
        _push({"type": "error", "message": str(exc)})


async def _run_mlx_vlm(
    run_id: str,
    model_name: str,
    prompt: str,
    selected_file: Optional[str],
) -> None:
    queue = run_queues[run_id]
    loop = asyncio.get_event_loop()

    # Resolve image: convert PDF to PNG temp file, or use image directly
    image_path: Optional[str] = None
    file_path: Optional[Path] = None
    if selected_file:
        file_path = ASSETS_DIR / selected_file
    else:
        for ext in (".pdf", ".png", ".jpg", ".jpeg"):
            candidates = list(ASSETS_DIR.glob(f"*{ext}"))
            if candidates:
                file_path = candidates[0]
                break

    if file_path and file_path.exists():
        if file_path.suffix.lower() == ".pdf":
            # Save rendered PNG to a file-specific temp name to avoid stale overwrites
            png_b64 = await loop.run_in_executor(None, _pdf_to_base64, file_path)
            tmp = ASSETS_DIR / f"_tmp_{file_path.stem}.png"
            tmp.write_bytes(base64.b64decode(png_b64))
            image_path = str(tmp)
        else:
            image_path = str(file_path)

    if not image_path:
        await queue.put({"type": "error", "message": "No image file found in assets"})
        return

    try:
        await _load_mlx_vlm_model(model_name)
        await loop.run_in_executor(
            None, _mlx_vlm_stream_blocking, run_id, model_name, prompt, image_path, loop
        )
    except Exception as exc:
        await queue.put({"type": "error", "message": str(exc)})


# ── Ollama helpers ────────────────────────────────────────────────────────────

async def _run_ollama(
    run_id: str,
    model_name: str,
    prompt: str,
    image_b64: Optional[str],
    system: Optional[str] = None,
    selected_file: Optional[str] = None,
    raw: bool = False,
    vision: bool = False,
    think: Optional[bool] = None,
) -> None:
    """Stream an Ollama model response, pushing SSE events to the run queue."""
    queue = run_queues[run_id]
    t_start = time.perf_counter()
    first_token_at: Optional[float] = None
    token_count = 0

    # Load image only for vision demos (Demo 2)
    if vision and not image_b64:
        if selected_file:
            file_path = ASSETS_DIR / selected_file
            if file_path.exists():
                if file_path.suffix.lower() == ".pdf":
                    loop = asyncio.get_event_loop()
                    image_b64 = await loop.run_in_executor(None, _pdf_to_base64, file_path)
                else:
                    image_b64 = base64.b64encode(file_path.read_bytes()).decode()
        else:
            # Fall back to first available PDF/image in assets
            for ext in (".pdf", ".png", ".jpg", ".jpeg"):
                candidates = list(ASSETS_DIR.glob(f"*{ext}"))
                if candidates:
                    f = candidates[0]
                    if ext == ".pdf":
                        loop = asyncio.get_event_loop()
                        image_b64 = await loop.run_in_executor(None, _pdf_to_base64, f)
                    else:
                        image_b64 = base64.b64encode(f.read_bytes()).decode()
                    break

    payload: dict = {
        "model": model_name,
        "prompt": prompt,
        "stream": True,
        "options": {"num_predict": 2048},
    }
    if raw:
        payload["raw"] = True
    if image_b64:
        payload["images"] = [image_b64]
    if system:
        payload["system"] = system
    if think is not None:
        payload["think"] = think


    try:
        in_thinking = False  # track whether we're emitting <think> block
        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream(
                "POST", "http://localhost:11434/api/generate", json=payload
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if run_id in run_cancelled:
                        break

                    thinking_tok = data.get("thinking", "")
                    response_tok = data.get("response", "")

                    if thinking_tok:
                        if not in_thinking:
                            in_thinking = True
                            await queue.put({"type": "token", "text": "<think>"})
                        if first_token_at is None:
                            first_token_at = time.perf_counter() - t_start
                        token_count += 1
                        await queue.put({"type": "token", "text": thinking_tok})
                    elif response_tok:
                        if in_thinking:
                            in_thinking = False
                            await queue.put({"type": "token", "text": "</think>"})
                        if first_token_at is None:
                            first_token_at = time.perf_counter() - t_start
                        token_count += 1
                        await queue.put({"type": "token", "text": response_tok})

                    if data.get("done"):
                        if in_thinking:
                            await queue.put({"type": "token", "text": "</think>"})
                        break

        t_total = time.perf_counter() - t_start
        loop = asyncio.get_event_loop()
        vram_mb = await loop.run_in_executor(None, _get_ollama_vram_mb)
        metrics = {
            "ttft_ms": round((first_token_at or 0) * 1000),
            "total_s": round(t_total, 1),
            "token_count": token_count,
            "vram_mb": vram_mb,
        }
        run_metrics[run_id] = metrics
        await queue.put({"type": "done", "metrics": metrics, "runtime": "Ollama"})

    except Exception as exc:
        await queue.put({"type": "error", "message": str(exc)})


def _get_ollama_vram_mb() -> Optional[int]:
    """Parse `ollama ps` to find VRAM usage in MB."""
    try:
        out = subprocess.check_output(["ollama", "ps"], text=True, timeout=5)
        lines = out.strip().splitlines()
        for line in lines[1:]:  # skip header row
            parts = line.split()
            for i, part in enumerate(parts):
                if part in ("GB", "GiB") and i > 0:
                    try:
                        return round(float(parts[i - 1]) * 1024)
                    except ValueError:
                        pass
                if part in ("MB", "MiB") and i > 0:
                    try:
                        return round(float(parts[i - 1]))
                    except ValueError:
                        pass
    except Exception:
        pass
    return None


# ── HuggingFace VLM helpers ───────────────────────────────────────────────────

def _load_hf_blocking(model_name: str) -> tuple:
    import torch
    from transformers import AutoProcessor, AutoModelForCausalLM
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    dtype = torch.float16 if device != "cpu" else torch.float32
    processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True, use_fast=False)
    model = AutoModelForCausalLM.from_pretrained(
        model_name, dtype=dtype, trust_remote_code=True
    ).to(device)
    model.eval()
    return model, processor


def _hf_stream_blocking(
    run_id: str,
    model_name: str,
    prompt: str,
    image_b64: Optional[str],
    loop: asyncio.AbstractEventLoop,
) -> None:
    from PIL import Image
    import io
    import torch

    queue = run_queues[run_id]

    def _push(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    try:
        model, processor = hf_model_cache[model_name]

        content = []
        image = None
        if image_b64:
            img_bytes = base64.b64decode(image_b64)
            image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            content.append({"type": "image"})
        content.append({"type": "text", "text": prompt})
        messages = [{"role": "user", "content": content}]

        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], images=[image] if image else None, return_tensors="pt")
        device = next(model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}
        input_len = inputs["input_ids"].shape[-1]

        device_str = str(next(model.parameters()).device)
        print(f"[HF] generating on {device_str}, input tokens: {input_len}")
        _push({"type": "token", "text": f"[generating on {device_str}…]\n\n"})

        t_start = time.perf_counter()
        with torch.no_grad():
            output_ids = model.generate(**inputs, max_new_tokens=512)
        t_total = time.perf_counter() - t_start

        tokenizer = getattr(processor, "tokenizer", processor)
        new_ids = output_ids[0][input_len:]
        output_text = tokenizer.decode(new_ids, skip_special_tokens=True)

        # Fake-stream: push in word-sized chunks so UI animates
        first_token_at: Optional[float] = None
        words = output_text.split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            if first_token_at is None:
                first_token_at = 0.1  # near-instant after generate() returns
            _push({"type": "token", "text": chunk})

        token_count = len(new_ids)
        gen_tps = round(token_count / t_total) if t_total > 0 else 0
        ram_mb = round(psutil.Process().memory_info().rss / (1024 * 1024))

        metrics = {
            "ttft_ms": round(t_total * 1000),  # full generation time (no streaming)
            "total_s": round(t_total, 1),
            "gen_tps": gen_tps,
            "ram_mb": ram_mb,
            "token_count": token_count,
        }
        run_metrics[run_id] = metrics
        _push({"type": "done", "metrics": metrics, "runtime": "HF"})

    except Exception as exc:
        _push({"type": "error", "message": str(exc)})


async def _run_hf(run_id: str, model_name: str, prompt: str, selected_file: Optional[str]) -> None:
    queue = run_queues[run_id]
    loop = asyncio.get_event_loop()

    # Resolve image from selected file or first available asset
    image_b64: Optional[str] = None
    file_path: Optional[Path] = None
    if selected_file:
        file_path = ASSETS_DIR / selected_file
    else:
        for ext in (".pdf", ".png", ".jpg", ".jpeg"):
            candidates = list(ASSETS_DIR.glob(f"*{ext}"))
            if candidates:
                file_path = candidates[0]
                break
    if file_path and file_path.exists():
        if file_path.suffix.lower() == ".pdf":
            image_b64 = await loop.run_in_executor(None, _pdf_to_base64, file_path)
        else:
            image_b64 = base64.b64encode(file_path.read_bytes()).decode()

    try:
        if model_name not in hf_model_cache:
            lock = _hf_load_locks.setdefault(model_name, asyncio.Lock())
            async with lock:
                if model_name not in hf_model_cache:
                    model, processor = await loop.run_in_executor(None, _load_hf_blocking, model_name)
                    hf_model_cache[model_name] = (model, processor)
        await loop.run_in_executor(None, _hf_stream_blocking, run_id, model_name, prompt, image_b64, loop)
    except Exception as exc:
        if queue:
            await queue.put({"type": "error", "message": str(exc)})


# ── Run request model ─────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    prompt: str
    think_mode: Optional[str] = None      # "think" | "no_think" | None (Demo 3 only)
    image_b64: Optional[str] = None       # base64 image (uploaded)
    selected_file: Optional[str] = None   # filename from /api/files (Demo 2)


# ── Run + Stream routes ───────────────────────────────────────────────────────

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
    run_queues[run_id] = asyncio.Queue(maxsize=512)

    prompt = body.prompt
    # Demo 3: think=True/False via Ollama's native parameter (no prompt prefix needed)
    think: Optional[bool] = None
    if demo_id == "3" and body.think_mode:
        think = body.think_mode == "think"

    if demo["runtime"] == "MLX":
        background_tasks.add_task(_run_mlx, run_id, demo["model"], prompt)
    elif demo["runtime"] == "MLX-VLM":
        task = asyncio.create_task(
            _run_mlx_vlm(run_id, demo["model"], prompt, body.selected_file)
        )
        run_tasks[run_id] = task
    elif demo["runtime"] == "HF":
        background_tasks.add_task(_run_hf, run_id, demo["model"], prompt, body.selected_file)
    else:
        task = asyncio.create_task(
            _run_ollama(run_id, demo["model"], prompt, body.image_b64,
                        demo.get("system"), body.selected_file, demo.get("raw", False),
                        demo.get("vision", False), think)
        )
        run_tasks[run_id] = task

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
                if item["type"] in ("done", "error", "cancelled"):
                    break
        finally:
            run_queues.pop(run_id, None)
            run_cancelled.discard(run_id)
            run_tasks.pop(run_id, None)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/cancel/{run_id}")
async def cancel_run(run_id: str):
    # Cancel the asyncio task — this aborts the httpx stream mid-generation
    task = run_tasks.pop(run_id, None)
    if task and not task.done():
        task.cancel()
    # Also signal MLX/HF runs (they poll run_cancelled)
    run_cancelled.add(run_id)
    q = run_queues.get(run_id)
    if q:
        await q.put({"type": "cancelled"})
    return {"cancelled": run_id}


# ── Upload + Health routes ────────────────────────────────────────────────────

@app.get("/api/files")
async def list_files():
    """List available PDF/image files for Demo 2."""
    exts = {".pdf", ".png", ".jpg", ".jpeg"}
    all_files = [f for f in sorted(ASSETS_DIR.iterdir())
                 if f.suffix.lower() in exts and not f.name.startswith("_tmp_")]
    # Put simple_invoice.pdf first
    names = [f.name for f in all_files]
    if "simple_invoice.pdf" in names:
        names.remove("simple_invoice.pdf")
        names.insert(0, "simple_invoice.pdf")
    return {"files": names}


def _pdf_to_base64(pdf_path: Path, page: int = 0) -> str:
    """Convert a PDF page to base64-encoded PNG using pymupdf."""
    import fitz  # pymupdf
    doc = fitz.open(str(pdf_path))
    mat = fitz.Matrix(2.0, 2.0)  # 2× zoom for readability
    pix = doc[page].get_pixmap(matrix=mat)
    return base64.b64encode(pix.tobytes("png")).decode()


@app.get("/api/preview/{filename}")
async def preview_file(filename: str):
    """Return first page of a PDF (or image) as PNG for the preview pane."""
    from fastapi.responses import Response
    path = ASSETS_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if path.suffix.lower() == ".pdf":
        loop = asyncio.get_event_loop()
        png_b64 = await loop.run_in_executor(None, _pdf_to_base64, path)
        png_bytes = base64.b64decode(png_b64)
        return Response(content=png_bytes, media_type="image/png")
    else:
        return Response(content=path.read_bytes(), media_type="image/png")


@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    global _uploaded_image_path
    suffix = Path(file.filename or "upload.png").suffix or ".png"
    dest = ASSETS_DIR / f"uploaded{suffix}"
    dest.write_bytes(await file.read())
    _uploaded_image_path = dest
    return {"path": str(dest), "filename": file.filename}


@app.get("/api/health")
async def health():
    result: dict[str, dict] = {}
    for demo_id, demo in DEMOS.items():
        if demo["runtime"] in ("MLX", "MLX-VLM", "HF"):
            ok = _check_mlx_cached(demo["model"])
        else:
            ok = await _check_ollama_model(demo["model"])
        result[demo_id] = {
            "ok": ok,
            "runtime": demo["runtime"],
            "model": demo["model"],
        }
    return result


def _check_mlx_cached(model_name: str) -> bool:
    """Check if an MLX model has been downloaded to the HuggingFace cache."""
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    dir_name = "models--" + model_name.replace("/", "--")
    return (hf_cache / dir_name).exists()



async def _check_ollama_model(model_name: str) -> bool:
    """Check if an Ollama model is available locally."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            names = [m["name"] for m in resp.json().get("models", [])]
            base = model_name.split(":")[0]
            return any(n.startswith(base) for n in names)
    except Exception:
        return False


# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    print("─" * 52)
    print("  SLM Demo Runner — PyConf Hyderabad 2026")
    print("─" * 52)
    print("  URL: http://localhost:8000")
    print()
    print("  Models:")
    for d in DEMOS.values():
        print(f"    [{d['runtime']:6s}] {d['subtitle']} — {d['model']}")
    print()
    print("  Tip: WiFi can be OFF — all calls are local")
    print("─" * 52)

    webbrowser.open("http://localhost:8000", new=2)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
