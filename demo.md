# SLM Demo Plan — PyConf Hyderabad 2026

## Setup

### Runtime: MLX for text models, Ollama for vision model

MLX runs 20–50% faster than Ollama on Apple Silicon with ~half the memory usage. Use MLX (via `mlx-lm`) for text-only demos and Ollama for the vision model (OCRFlux-3B).

```bash
# Install MLX (for Demos 1, 3, 4 — text models)
pip install mlx-lm

# Install Ollama (for Demo 2 — vision model)
brew install ollama

# Pull MLX models (auto-downloads from HuggingFace)
# These download on first run — no separate pull needed

# Pull Ollama vision model
ollama pull myaniu/OCRFlux-3B
```

### Why two runtimes?
- **MLX**: Apple-built framework, targets unified memory directly, no CPU↔GPU copy overhead, optimized Metal shaders. ~230 tok/s on M-series vs ~120 tok/s on Ollama. Uses ~50% less memory for the same model.
- **Ollama**: Better ecosystem support for vision-language models (VLMs). OCRFlux-3B needs image input which mlx-lm doesn't handle natively.
- **Talking point for audience**: "Different runtimes for different tasks — that's the SLM stack in practice."

Total memory: ~8–12GB running one at a time. Fits on any M-series Mac.

---

## Demo 1 — JSON Extraction (Osmosis-Structure-0.6B)

**Model**: Osmosis-Structure-0.6B (0.6B params, Qwen3-0.6B base, RL-trained on 500K JSON examples)
**Point**: A 0.6B model doing structured extraction that used to need GPT-4.

### Run via MLX (recommended — ~2× faster, half the memory)

```bash
mlx_lm.generate \
  --model mlx-community/Osmosis-Structure-0.6B-4bit \
  --prompt 'Extract the following fields as JSON from this text:

"Invoice #INV-2024-0847 dated March 12, 2026. Bill to: Acme Corp,
42 Innovation Drive, Bangalore 560001. Items: 3x GPU Server Rack
($12,500 each), 1x Network Switch ($3,200), Setup fee $500.
Payment terms: Net 30. Tax: 18% GST."

Fields needed: invoice_number, date, company, address, line_items (array with name, quantity, unit_price), subtotal, tax_rate, total'
```

### Fallback via Ollama

```bash
ollama run osmosis/osmosis-structure-0.6b
# Then paste the same prompt
```

### Expected output
Clean JSON with correct calculations. Highlight to audience:
- 0.6B params — runs in <100ms on MLX, <200ms on Ollama
- No cloud, no API key, no cost
- Trained specifically for this task via RL — not prompt engineering
- **MLX bonus**: Show the tokens/sec in terminal output — audience sees raw speed

---

## Demo 2 — PDF Extraction (OCRFlux-3B)

**Model**: OCRFlux-3B (3B params, fine-tuned from Qwen2.5-VL-3B, 0.967 Edit Distance Similarity)
**Point**: Beats olmOCR-7B (a model 2× its size) on extraction benchmarks.

### Setup
Prepare a messy real-world PDF — an invoice with tables, a research paper page, or a scanned receipt.

### Prompt

```bash
ollama run myaniu/OCRFlux-3B
```

Feed it a screenshot/image of a PDF page:

```
Convert this document to clean Markdown. Preserve all table structures, headers, and formatting.
```

### Expected output
Structured Markdown with tables intact. Highlight to audience:
- Vision-language model — takes images as input, not parsed text
- Handles complex layouts, multi-column, tables
- 3B params, runs on laptop GPU
- Compare: traditional OCR pipeline (Tesseract + regex + postprocessing) vs one model call

---

## Demo 3 — Reasoning with Thinking Mode (SmolLM3-3B)

**Model**: SmolLM3-3B (3B params, dual-mode /think and /no_think)
**Point**: Same model, same prompt — 4× better with thinking mode. AIME 2025: 36.7% vs 9.3%.

### Run 1 — Without thinking (fast, direct) via MLX

```bash
mlx_lm.generate \
  --model mlx-community/SmolLM3-3B-Instruct-4bit \
  --prompt '/no_think
A store offers a 20% discount on a jacket that originally costs $150.
Then they apply an additional 15% discount on the already discounted price.
A customer also has a $10 coupon.
What is the final price? Is this better or worse than a single 35% discount?'
```

### Run 2 — With thinking (chain-of-thought visible) via MLX

```bash
mlx_lm.generate \
  --model mlx-community/SmolLM3-3B-Instruct-4bit \
  --prompt '/think
A store offers a 20% discount on a jacket that originally costs $150.
Then they apply an additional 15% discount on the already discounted price.
A customer also has a $10 coupon.
What is the final price? Is this better or worse than a single 35% discount?'
```

### Fallback via Ollama

```bash
ollama run smollm3
# Use system prompt: /no_think or /think, then paste the question
```

### Expected output
- Run 1: Likely gets the number but may miss the comparison or make an error
- Run 2: Shows step-by-step reasoning, correctly computes both paths, and explains why stacked discounts ≠ combined discount

Highlight to audience:
- Thinking mode is a toggle, not a different model
- 3B params doing multi-step math reasoning
- The audience sees the chain-of-thought streaming in real time
- **MLX bonus**: ~120+ tok/s means the thinking chain streams fast — more impressive live than waiting for Ollama at ~60 tok/s

---

## Demo 4 — Code Generation (Qwen 2.5 Coder 7B)

**Model**: Qwen 2.5 Coder 7B (7B params, coding specialist)
**Point**: A local model generating production-quality code — no Copilot subscription needed.

### Run via MLX (recommended)

```bash
mlx_lm.generate \
  --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit \
  --prompt 'Write a Python FastAPI endpoint that:
1. Accepts a POST request with a JSON body containing "text" and "language" fields
2. Uses a simple rule-based approach to count sentences, words, and characters
3. Returns a JSON response with the analysis results
4. Includes proper error handling and type hints
5. Add a health check endpoint

Include the complete runnable file with imports.'
```

### Fallback via Ollama

```bash
ollama run qwen2.5-coder:7b
# Then paste the same prompt
```

### Expected output
A complete, runnable FastAPI app. Highlight to audience:
- Clean code with type hints, error handling, docstrings
- 7B model, runs locally, ~50-60 tok/s on MLX vs ~30 tok/s on Ollama
- 5× faster prompt processing on MLX — noticeable when the prompt is long
- For scoped code tasks, this replaces a cloud API call entirely

### Bonus — if time permits
Ask it to add tests:
```
Now write pytest tests for the endpoints above. Include edge cases.
```

---

## Demo Flow & Narrative

| # | Demo | Model | Size | Runtime | Time | Key Takeaway |
|---|------|-------|------|---------|------|--------------|
| 1 | JSON Extraction | Osmosis-Structure | 0.6B | MLX | 2 min | Tiny model, surgical precision |
| 2 | PDF Extraction | OCRFlux-3B | 3B | Ollama | 3 min | Beats models 2× its size |
| 3 | Reasoning | SmolLM3 | 3B | MLX | 3 min | Thinking mode = 4× better |
| 4 | Code Generation | Qwen 2.5 Coder | 7B | MLX | 3 min | Local Copilot, zero cost |

**Total demo time**: ~11 minutes

**Narrative arc**: 0.6B → 3B → 3B → 7B — the right small model for the right task beats a general-purpose LLM every time.

**Runtime arc**: MLX → Ollama → MLX → MLX — different runtimes for different tasks, that's the real SLM stack.

---

## Live Metrics to Show

After each demo, flash these numbers:
- **Tokens/sec**: MLX prints this automatically in terminal output
- **Latency**: Time from prompt to first token (TTFT)
- **Model size on disk**: How much space it takes
- **RAM usage**: Check via Activity Monitor or `ollama ps` for Ollama demos
- **Cost**: $0.00 (vs equivalent cloud API cost)

```bash
# For Ollama demos — show running model stats
ollama ps

# For MLX demos — tokens/sec is printed automatically after generation
# Example output: "Prompt: 45 tokens, 892.3 tokens/s | Generation: 128 tokens, 112.5 tokens/s"
```

---

## Fallback Plan

If a demo fails or produces poor output:
1. That IS the demo — show the failure, explain why SLMs have limits
2. Pivot to: "This is exactly why we need the cascade pattern — SLM first, LLM fallback"
3. Have pre-recorded outputs as backup screenshots

---

## Pre-demo Checklist

- [ ] `pip install mlx-lm` installed and working
- [ ] `brew install ollama` installed and running (`ollama serve`)
- [ ] MLX models downloaded (run each `mlx_lm.generate` command once to cache)
- [ ] Ollama model pulled: `ollama pull myaniu/OCRFlux-3B`
- [ ] Sample PDF/invoice image prepared for Demo 2
- [ ] Terminal font size set to 18+ for readability
- [ ] WiFi OFF during demos (proves it's truly local)
- [ ] Backup screenshots of successful runs
- [ ] Test run all 4 demos end-to-end the night before
