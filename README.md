# Small Models, Big Impact

Talk slides and live demo runner for **PyConf Hyderabad 2026**.

## Demo Runner

A local web dashboard that streams output from 5 SLM demos in real time.

```bash
cd demo_runner
pip install -r requirements.txt
ollama pull myaniu/OCRFlux-3B:Q8_0   # Demo 2 only
python app.py
# → http://localhost:8000
```

### Demos

| # | Title | Model | Size | Runtime |
|---|-------|-------|------|---------|
| 1 | JSON Parsing | NuExtract-2.0 | 2B | Ollama |
| 2 | PDF Extraction | PaddleOCR-VL-1.5 | 0.9B | MLX-VLM |
| 3 | General Reasoning | Qwen3.5 (think/no_think) | 2B | Ollama |
| 4 | Code Generation | Qwen3.5 | 4B | Ollama |
| 5 | Multilingual | Tiny Aya Fire | 3B | Ollama |

All models run locally — no internet required during demos.

### Features

- Live token streaming via SSE
- Side-by-side thinking vs direct mode (Demo 3)
- Real-time metrics: tokens/sec, TTFT, RAM, cost vs cloud
- Stop button cancels generation mid-stream
- Keyboard shortcuts: `1–5` switch demo, `R` run, `D` clear

## Slides

Built with [Slidev](https://sli.dev).

```bash
pnpm install
pnpm dev
```
