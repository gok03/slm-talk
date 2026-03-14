"""Pipeline worker functions for OCR, JSON extraction, and browser automation."""
from __future__ import annotations

import asyncio
import json
import time


def _app():
    import sys
    # When run as 'python app.py' the module is '__main__', not 'app'.
    return sys.modules.get("app") or sys.modules["__main__"]


async def run_ocr_worker(task_id: str, run_id: str, filename: str) -> None:
    """OCR worker: PDF → Markdown via PaddleOCR-VL-1.5."""
    from pipeline.a2a import get_task
    a = _app()

    task = get_task("ocr", task_id)
    if not task:
        return

    task.state = "working"
    t_start = time.perf_counter()
    dest_q = a.pipeline_queues[run_id]

    await dest_q.put({"type": "token", "step": "ocr", "text": "← task received (A2A)\n"})
    await dest_q.put({"type": "token", "step": "ocr", "text": "   state: submitted→working\n"})

    # Resolve file, convert PDF → run_id-scoped PNG
    import base64
    assets_dir = a.ASSETS_DIR
    file_path = assets_dir / filename
    image_path: str | None = None

    if file_path.exists():
        if file_path.suffix.lower() == ".pdf":
            loop = asyncio.get_running_loop()
            png_b64 = await loop.run_in_executor(None, a._pdf_to_base64, file_path)
            tmp = assets_dir / f"_tmp_{run_id}_{file_path.stem}.png"
            tmp.write_bytes(base64.b64decode(png_b64))
            image_path = str(tmp)
            await dest_q.put({"type": "token", "step": "ocr", "text": "   pdf→png · 2× zoom\n"})
        else:
            image_path = str(file_path)

    if not image_path:
        task.state = "failed"
        task.error = "File not found"
        await dest_q.put({"type": "token", "step": "ocr", "text": "   ERROR: file not found\n"})
        return

    # Sub-queue: _run_mlx_vlm pushes plain tokens here; we re-emit with step="ocr"
    sub_run_id = f"_ocr_{run_id}"
    sub_q: asyncio.Queue = asyncio.Queue(maxsize=1024)
    a.pipeline_queues[sub_run_id] = sub_q

    collected: list[str] = []

    async def relay_tokens():
        while True:
            item = await sub_q.get()
            if item["type"] == "token":
                collected.append(item.get("text", ""))
                await dest_q.put({"type": "token", "step": "ocr", "text": item.get("text", "")})
            elif item["type"] in ("done", "error"):
                break

    relay_task = asyncio.create_task(relay_tokens())

    try:
        model_name = "mlx-community/PaddleOCR-VL-1.5-4bit"
        await a._load_mlx_vlm_model(model_name)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            a._mlx_vlm_stream_blocking,
            sub_run_id,
            model_name,
            "OCR:",
            image_path,
            loop,
            a.pipeline_queues,  # queue_store = pipeline_queues, keyed by sub_run_id
        )
        await asyncio.wait_for(relay_task, timeout=300)
    except asyncio.TimeoutError:
        relay_task.cancel()
        try:
            await relay_task
        except asyncio.CancelledError:
            pass
        task.state = "failed"
        task.error = "relay timed out"
        await dest_q.put({"type": "token", "step": "ocr", "text": "   ERROR: relay timed out\n"})
        return
    except Exception as exc:
        task.state = "failed"
        task.error = str(exc)
        relay_task.cancel()
        try:
            await relay_task
        except asyncio.CancelledError:
            pass
        await dest_q.put({"type": "token", "step": "ocr", "text": f"   ERROR: {exc}\n"})
        return
    finally:
        a.pipeline_queues.pop(sub_run_id, None)

    markdown = "".join(collected)
    task.output = {"markdown": markdown}
    task.state = "completed"

    duration = round(time.perf_counter() - t_start, 1)
    await dest_q.put({"type": "token", "step": "ocr", "text": "   state: working→completed\n"})
    await dest_q.put({"type": "token", "step": "ocr", "text": "→ result sent (A2A) ✓\n"})
    await dest_q.put({"type": "step_done", "step": "ocr", "duration_s": duration})


async def run_json_worker(task_id: str, run_id: str, text: str) -> None:
    """JSON worker: OCR Markdown → structured JSON via NuExtract-2.0."""
    from pipeline.a2a import get_task
    a = _app()

    task = get_task("json", task_id)
    if not task:
        return

    task.state = "working"
    t_start = time.perf_counter()
    dest_q = a.pipeline_queues[run_id]

    await dest_q.put({"type": "token", "step": "json", "text": "← task received (A2A)\n"})
    await dest_q.put({"type": "token", "step": "json", "text": "   state: submitted→working\n"})

    # NuExtract-2.0 prompt format — extract only the 3 key fields
    prompt = (
        "<|input|>\n"
        "### Template:\n"
        '{"invoice_number": "", "date": "", "total": ""}\n\n'
        "### Text:\n"
        f"{text}\n"
        "<|output|>\n"
    )

    # Sub-queue pattern (same as OCR worker)
    sub_run_id = f"_json_{run_id}"
    sub_q: asyncio.Queue = asyncio.Queue(maxsize=1024)
    a.pipeline_queues[sub_run_id] = sub_q

    collected: list[str] = []

    async def relay_tokens():
        depth = 0
        started = False
        while True:
            item = await sub_q.get()
            if item["type"] == "token":
                tok = item.get("text", "")
                collected.append(tok)
                await dest_q.put({"type": "token", "step": "json", "text": tok})
                # Stop after first complete top-level JSON object
                for ch in tok:
                    if ch == "{":
                        depth += 1
                        started = True
                    elif ch == "}":
                        depth -= 1
                if started and depth == 0:
                    break  # first complete JSON object received
            elif item["type"] in ("done", "error"):
                break

    relay_task = asyncio.create_task(relay_tokens())

    try:
        model_name = "hf.co/numind/NuExtract-2.0-2B-GGUF"
        await a._run_ollama(
            sub_run_id,
            model_name,
            prompt,
            image_b64=None,
            raw=True,
            queue_store=a.pipeline_queues,
            extra_options={"num_predict": 512, "stop": ["<|input|>", "\n\n\n"]},
        )
        await asyncio.wait_for(relay_task, timeout=300)
    except asyncio.TimeoutError:
        relay_task.cancel()
        try:
            await relay_task
        except asyncio.CancelledError:
            pass
        task.state = "failed"
        task.error = "relay timed out"
        await dest_q.put({"type": "token", "step": "json", "text": "   ERROR: relay timed out\n"})
        return
    except Exception as exc:
        task.state = "failed"
        task.error = str(exc)
        relay_task.cancel()
        try:
            await relay_task
        except asyncio.CancelledError:
            pass
        await dest_q.put({"type": "token", "step": "json", "text": f"   ERROR: {exc}\n"})
        return
    finally:
        a.pipeline_queues.pop(sub_run_id, None)

    raw_json = "".join(collected).strip()

    # Extract first valid JSON object (NuExtract sometimes outputs multiple)
    invoice_dict = {}
    start = raw_json.find("{")
    while start >= 0:
        depth = 0
        for i, ch in enumerate(raw_json[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw_json[start:i + 1]
                    try:
                        parsed = json.loads(candidate)
                        # Accept the first object that has at least one non-null value
                        if any(v is not None for v in parsed.values()):
                            invoice_dict = parsed
                            break
                    except json.JSONDecodeError:
                        pass
                    break
        if invoice_dict:
            break
        start = raw_json.find("{", start + 1)

    task.output = {"json": invoice_dict}
    task.state = "completed"

    duration = round(time.perf_counter() - t_start, 1)
    await dest_q.put({"type": "token", "step": "json", "text": "   validated ✓\n"})
    await dest_q.put({"type": "token", "step": "json", "text": "→ result sent (A2A) ✓\n"})
    await dest_q.put({"type": "step_done", "step": "json", "duration_s": duration})



async def run_browser_worker(task_id: str, run_id: str, invoice_json: dict, form_url: str, use_cloud: bool = False) -> None:
    """Browser worker: fills /form using Python Playwright."""
    from pipeline.a2a import get_task
    from playwright.async_api import async_playwright
    import base64
    a = _app()

    task = get_task("browser", task_id)
    if not task:
        return

    task.state = "working"
    t_start = time.perf_counter()
    dest_q = a.pipeline_queues[run_id]

    await dest_q.put({"type": "token", "step": "browser", "text": "← task received (A2A)\n"})
    await dest_q.put({"type": "token", "step": "browser", "text": "   state: submitted→working\n"})
    await dest_q.put({"type": "token", "step": "browser", "text": "   launching Playwright (headed Chrome)\n"})

    submitted = False

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=False)
            page = await browser.new_page()

            async def screenshot():
                try:
                    png = await page.screenshot()
                    await dest_q.put({"type": "browser_screenshot", "step": "browser", "data": base64.b64encode(png).decode()})
                except Exception:
                    pass

            # Navigate
            await dest_q.put({"type": "token", "step": "browser", "text": f"   → {form_url}\n"})
            await page.goto(form_url)
            await screenshot()

            # Fill fields by input id
            for key in ("invoice_number", "date", "total"):
                value = str(invoice_json.get(key, ""))
                if not value:
                    continue
                await page.locator(f"#{key}").fill(value)
                await dest_q.put({"type": "token", "step": "browser", "text": f"   fill #{key} = {value!r} ✓\n"})

            await screenshot()

            # Submit
            await page.locator("button[type=submit]").click()
            await dest_q.put({"type": "token", "step": "browser", "text": "   submit ✓\n"})
            await page.wait_for_timeout(500)
            await screenshot()

            submitted = True
            await browser.close()

    except Exception as exc:
        import traceback
        traceback.print_exc()
        task.state = "failed"
        task.error = repr(exc)
        await dest_q.put({"type": "token", "step": "browser", "text": f"   ERROR: {exc!r}\n"})
        return

    task.output = {"submitted": submitted}
    task.state = "completed"

    duration = round(time.perf_counter() - t_start, 1)
    status = "→ form submitted (A2A) ✓" if submitted else "→ form not submitted"
    await dest_q.put({"type": "token", "step": "browser", "text": f"{status}\n"})
    await dest_q.put({"type": "step_done", "step": "browser", "duration_s": duration})
