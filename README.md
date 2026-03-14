# Small Models, Big Impact

Talk slides and live demo runner for **PyConf Hyderabad 2026**.

## Setup

### 1. Pull Ollama models

```bash
# Demo 1 — JSON Parsing
ollama pull hf.co/numind/NuExtract-2.0-2B-GGUF

# Demo 3 — General Reasoning
ollama pull qwen3.5:2b

# Demo 4 — Code Generation
ollama pull qwen3.5:4b

# Demo 5 — Multilingual
ollama pull tiny-aya-fire

# Pipeline supervisor (local mode)
ollama pull qwen3.5:9b

# Pipeline JSON worker
ollama pull nuextract   # or hf.co/numind/NuExtract-2.0-2B-GGUF
```

### 2. Download MLX models (auto on first run)

Demo 2 and the pipeline OCR worker use MLX-VLM — models are downloaded from HuggingFace automatically on first use:

- `mlx-community/PaddleOCR-VL-1.5-4bit` — Demo 2 + pipeline OCR worker

To pre-download:

```bash
python -c "from mlx_vlm import load; load('mlx-community/PaddleOCR-VL-1.5-4bit')"
```

### 3. Start Ollama

```bash
ollama serve
```

### 4. Install Python dependencies

```bash
cd demo_runner
pip install -r requirements.txt
playwright install chromium
```

### 5. Start the demo server

```bash
python app.py
# → http://localhost:8000
```

---

## Demos

| # | Title | Model | Size | Runtime |
|---|-------|-------|------|---------|
| 1 | JSON Parsing | NuExtract-2.0 | 2B | Ollama |
| 2 | PDF Extraction | PaddleOCR-VL-1.5 | 0.9B | MLX-VLM |
| 3 | General Reasoning | Qwen3.5 (think/no_think) | 2B | Ollama |
| 4 | Code Generation | Qwen3.5 | 4B | Ollama |
| 5 | Multilingual | Tiny Aya Fire | 3B | Ollama |

### Multi-Agent Pipeline (`/pipeline`)

| Role | Model | Size | Runtime |
|------|-------|------|---------|
| Supervisor (local) | Qwen3.5 | 9B | Ollama |
| Supervisor (cloud) | Qwen3.5-35B-A3B | 35B | OpenRouter |
| OCR Worker | PaddleOCR-VL-1.5 | 0.9B | MLX-VLM |
| JSON Worker | NuExtract-2.0 | 2B | Ollama |
| Browser Worker | Playwright (Python) | — | — |

Add your OpenRouter API key to `demo_runner/.env` for the cloud supervisor toggle:

```
OPENROUTER_API_KEY=sk-or-...
```

All models run locally by default — no internet required during demos.

---

## Features

- Live token streaming via SSE
- Side-by-side thinking vs direct mode (Demo 3)
- Real-time metrics: tokens/sec, TTFT, RAM, cost vs cloud
- Stop button cancels generation mid-stream
- Keyboard shortcuts: `1–5` switch demo, `R` run, `D` clear
- Multi-agent pipeline with A2A protocol + Playwright browser automation

---

## Slides

Built with [Slidev](https://sli.dev).

```bash
pnpm install
pnpm dev
```
