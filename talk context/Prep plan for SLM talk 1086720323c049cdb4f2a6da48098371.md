# Prep plan for SLM talk

### Goal

End-to-end plan to prepare for the "Small Language Models in Production: When Less Is More" PyConf talk.

---

### 1. Study plan

**Goal:** Be fluent enough to answer deep questions, not just run a demo.

[**Foundations of SLMs and quantization (2–3 days, part-time)**](Foundations%20of%20SLMs%20and%20quantization%20(2%E2%80%933%20days,%20pa%20820f45550bf744318429ae5fdbcc29b5.md)

1. **Runtimes and serving from Python (2–3 days)**
    - How to load and run these models in Python using a CPU-friendly runtime.
    - Expose a simple HTTP API (FastAPI or Flask) around a model.
    - Deliverable: tiny "model server" with `POST /completion` and basic logging (latency, tokens).
2. **Application patterns where SLMs shine (2–3 days)**
    - Patterns: routing / intent detection, classification / tagging, structured extraction to JSON.
    - Pick a single domain **(RPA and automation)** and frame all examples around bots running business workflows.
    - Deliverable: 3–5 real prompts per pattern in that domain.
3. **SLM-first / LLM-fallback architecture (1–2 days)**
    - How to call SLM locally, validate outputs, and only then call big LLM as fallback.
    - Deliverable: pseudo-code + diagrams for request flow, validation, logging, and metrics.

---

### 2. POC phase (playground)

**Goal:** Have one playground that touches every concept in the outline.

### 2.1 SLM benchmarking POC

- Implement [`benchmark.py`](http://benchmark.py) that, for each candidate SLM:
    - Runs on a fixed set of prompts (classification, extraction, short generation).
    - Measures tokens/sec and latency per request.
    - Computes simple "quality" signal (JSON parses, labels match expected, etc.).
- Deliverable: CSV or table (model vs size vs latency vs pass rate) for slides.

### 2.2 Task POCs: route, classify, extract

Using the chosen domain **RPA and automation** (e.g. bots handling repetitive business workflows):

1. **Routing / intent detection**
    - Input: free-text message.
    - Output: one of N intents (e.g. billing, bug, feature request).
    - Add confidence heuristic: valid label and simple confidence/heuristic check.
2. **Classification / tagging**
    - Multi-label tags (priority, product area, etc.).
    - Validate output against a whitelist of tags.
3. **Structured extraction**
    - Input: message or short transcript.
    - Output: JSON with 3–5 fields (e.g. customer_id, priority, product, summary).
    - Strict JSON parsing and required-keys validation.

### 2.3 Fallback POC

- Wrap tasks with an orchestrator that:
    - Calls SLM.
    - Validates output (schema, regex, required fields).
    - On failure, calls a big cloud LLM as fallback.
- Log: model_used, reason_for_fallback, latency_total.
- Deliverable: working SLM-first / LLM-fallback prototype.

---

### 3. Production-style demo system

**Goal:** Turn the POC into a clean, believable demo aligned with the 25+5 min talk.

Pick one scenario, for example:

- Service that ingests automation requests or task descriptions, classifies them, extracts structured fields, and routes to the right RPA bot / desktop workflow.

### 3.1 System shape

Components:

1. **SLM service (local, CPU)**
    - FastAPI app exposing `POST /infer` with `{task, payload}`.
    - Handles routing, classification, and extraction via different prompts.
2. **Gateway / orchestrator**
    - Receives raw request.
    - Decides which task(s) to run.
    - Calls SLM, validates, optionally calls big LLM.
    - Returns final JSON result.
3. **Tiny UI or CLI**
    - Simple web page or CLI:
        - Text box or stdin for input.
        - Shows model used (SLM vs fallback), latency, and final structured result.

### 3.2 Hardening for "production-ish" feel

- Config via env or config file: model names, thresholds, endpoint URLs.
- Validation:
    - Small JSON schema for outputs.
    - Regex for IDs/emails where relevant.
- Logging & metrics:
    - Request ID, model used, latency, whether fallback occurred.
- Optional: small synthetic dataset you can replay during the demo to get predictable results.

---

### 4. Suggested schedule to hit Jan 1

- Days 1–3: Study + choose models + runtime setup.
- Days 4–6: POC (benchmark + routing/classification/extraction with SLM only).
- Days 7–9: Add fallback + orchestrator (validation + cloud LLM + logging/metrics).
- Days 10–11: Turn POC into final demo (clean code, add UI/CLI, define demo script).
- Day 12: Slides (diagrams, benchmark table, screenshots from the running system).