# End-to-End Multi-Agent SLM Demo — Architecture & Plan

## What This Demo Shows

A real multi-agent SLM pipeline running entirely on a laptop:
1. Parse a messy PDF invoice using a vision SLM
2. Structure the extracted data into validated JSON using a purpose-built SLM
3. Open a headless browser and fill a Google Form with the structured data

Three different SLMs, one supervisor, two open protocols (MCP + A2A), zero cloud API calls.

### Protocols Used
- **MCP (Model Context Protocol)** — Vertical integration: agents connect to tools (Playwright browser, file system)
- **A2A (Agent-to-Agent)** — Horizontal integration: agents discover and communicate with each other via Agent Cards and stateful Task objects

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     MULTI-AGENT SLM PIPELINE                             │
│                     MCP (tools) + A2A (agents)                           │
│                                                                          │
│  ┌─────────────────────┐             ┌─────────────────────────┐         │
│  │     SUPERVISOR      │◄───────────►│     SHARED STATE        │         │
│  │   Qwen 3.5 4B       │  R/W        │  In-memory / Redis      │         │
│  │   (Ollama)           │             └─────────────────────────┘         │
│  │                      │                                                │
│  │  • Plans steps       │   ┌──────────────────────────────────┐         │
│  │  • Discovers agents  │──►│  /.well-known/agent.json         │         │
│  │  • Sends A2A tasks   │   │  Agent Cards for each worker     │         │
│  │  • Validates output  │   │  (capabilities, endpoints, auth) │         │
│  │  • Re-plans on fail  │   └──────────────────────────────────┘         │
│  └──┬──────┬──────┬─────┘                                                │
│     │      │      │                                                      │
│     │  A2A Task   │   A2A Protocol (JSON-RPC / HTTP)                     │
│     │  Objects    │   Stateful: submitted → working → completed          │
│     │      │      │                                                      │
│     ▼      ▼      ▼                                                      │
│  ┌──────┐┌──────┐┌──────────┐   Each worker is an A2A Server            │
│  │STEP 1││STEP 2││  STEP 3  │   with its own Agent Card                 │
│  │      ││      ││          │                                            │
│  │OCR   ││JSON  ││BROWSER   │   Workers report status back              │
│  │Agent ││Agent ││Agent     │   via A2A task lifecycle                   │
│  └──┬───┘└──┬───┘└────┬─────┘                                            │
│     │       │         │         MCP Protocol (JSON-RPC / stdio)          │
│     │       │         │         Agent ↔ Tool (vertical)                  │
│     ▼       ▼         ▼                                                  │
│  ┌──────┐┌──────┐┌──────────┐                                            │
│  │OCR   ││JSON  ││Playwright│                                            │
│  │Flux  ││Schema││MCP       │   MCP Servers                              │
│  │-3B   ││0.6B  ││Server    │   (tools, not agents)                      │
│  │      ││      ││          │                                            │
│  │Ollama││MLX   ││npx       │                                            │
│  └──────┘└──────┘└──────────┘                                            │
│                                                                          │
│  ═══════════════════════════════════════════════════════════              │
│  A2A = Agent ↔ Agent (horizontal)  │  MCP = Agent ↔ Tool (vertical)     │
│  Discovery, task mgmt, lifecycle   │  Function calling, data access      │
│  ═══════════════════════════════════════════════════════════              │
│                                                                          │
│  INPUT: invoice.pdf ────────────────────► OUTPUT: Google Form filled     │
└──────────────────────────────────────────────────────────────────────────┘
```

### How A2A and MCP Work Together

```
Supervisor (A2A Client)
    │
    ├── Discovers OCR Agent via Agent Card (/.well-known/agent.json)
    │   └── Sends A2A Task: "Extract text from this PDF"
    │       └── OCR Agent uses MCP to call OCRFlux-3B model
    │           └── Returns A2A Task result: raw Markdown text
    │
    ├── Discovers JSON Agent via Agent Card
    │   └── Sends A2A Task: "Structure this text as invoice JSON"
    │       └── JSON Agent uses MCP to call Osmosis-0.6B model
    │           └── Returns A2A Task result: validated JSON
    │
    └── Discovers Browser Agent via Agent Card
        └── Sends A2A Task: "Fill this Google Form with this JSON"
            └── Browser Agent uses MCP to call Playwright tools
                └── Returns A2A Task result: form submitted ✅
```

---

## Models & Roles

| Role | Model | Size | Runtime | Why This Model |
|------|-------|------|---------|----------------|
| **Supervisor** | Qwen 3.5 4B | 4B | Ollama | Native function calling, thinking mode, plans multi-step tasks. Recommended by Qwen docs for agentic use with `enable_thinking=true` |
| **Step 1: OCR Worker** | OCRFlux-3B | 3B | Ollama | Vision-language model, takes PDF page images as input, outputs Markdown. Beats olmOCR-7B (2× its size). 0.967 Edit Distance Similarity |
| **Step 2: JSON Worker** | Osmosis-Structure-0.6B | 0.6B | MLX | Purpose-built for JSON extraction via RL on 500K examples. Surgical precision on structured output |
| **Step 3: Browser Worker** | Qwen 3.5 4B (reuse supervisor) | 4B | Ollama | Supervisor doubles as browser agent — it already has function calling for Playwright MCP tools |

**Total unique models**: 3 (Qwen 3.5 4B, OCRFlux-3B, Osmosis-0.6B)
**Total memory**: ~10–14GB running one worker at a time

---

## Step-by-Step Pipeline

### Step 1: PDF → Raw Text (OCRFlux-3B via Ollama)

**Input**: `invoice.pdf` (a messy real-world invoice with tables, logos, varying layouts)

**Process**:
1. Convert PDF pages to images using `pdf2image` or `PyMuPDF`
2. Send each page image to OCRFlux-3B via Ollama API
3. Get back clean Markdown with tables preserved

```python
import ollama
from pdf2image import convert_from_path

# Convert PDF to images
images = convert_from_path("invoice.pdf", dpi=200)

# OCR each page
raw_text_pages = []
for i, img in enumerate(images):
    img.save(f"/tmp/page_{i}.png")
    response = ollama.chat(
        model="myaniu/OCRFlux-3B",
        messages=[{
            "role": "user",
            "content": "Convert this document page to clean Markdown. Preserve all table structures.",
            "images": [f"/tmp/page_{i}.png"]
        }]
    )
    raw_text_pages.append(response["message"]["content"])

raw_text = "\n\n".join(raw_text_pages)
```

**Output**: Raw Markdown text with tables, headers, line items extracted from PDF

---

### Step 2: Raw Text → Validated JSON (Osmosis-Structure-0.6B via MLX)

**Input**: Raw Markdown text from Step 1

**Process**:
1. Send raw text to Osmosis with a JSON schema prompt
2. Parse output, validate against schema
3. If validation fails → supervisor re-plans (retry with different prompt or escalate)

```python
import subprocess
import json

prompt = f"""Extract the following fields as JSON from this invoice text:

{raw_text}

Required JSON schema:
{{
  "invoice_number": "string",
  "date": "string",
  "vendor": {{
    "name": "string",
    "address": "string"
  }},
  "bill_to": {{
    "name": "string",
    "address": "string"
  }},
  "line_items": [
    {{
      "description": "string",
      "quantity": "number",
      "unit_price": "number",
      "total": "number"
    }}
  ],
  "subtotal": "number",
  "tax_rate": "string",
  "tax_amount": "number",
  "total": "number"
}}"""

# Run via MLX
result = subprocess.run(
    ["mlx_lm.generate",
     "--model", "mlx-community/Osmosis-Structure-0.6B-4bit",
     "--prompt", prompt,
     "--max-tokens", "1024"],
    capture_output=True, text=True
)

# Parse and validate
invoice_data = json.loads(result.stdout)

# Validation
assert "invoice_number" in invoice_data
assert isinstance(invoice_data["line_items"], list)
assert invoice_data["total"] > 0
```

**Output**: Validated JSON object with all invoice fields

---

### Step 3: JSON → Google Form Submission (Playwright MCP via Qwen 3.5 4B)

**Input**: Validated JSON from Step 2

**Process**:
1. Supervisor (Qwen 3.5 4B) receives the JSON data and the Google Form URL
2. Uses Playwright MCP tools to navigate, fill fields, and submit
3. Playwright MCP uses accessibility tree (no vision needed) — the LLM sees form field labels and interacts via structured commands

#### Playwright MCP Server Setup

```bash
# Install Playwright MCP server
npm install -g @playwright/mcp@latest

# Or run directly via npx (no install needed)
npx @playwright/mcp@latest
```

#### MCP Server Configuration (for the agent)

```json
{
  "mcpServers": {
    "playwright": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"],
      "timeout": 30000
    }
  }
}
```

#### Agent Code (Supervisor drives browser via MCP tools)

```python
import ollama
import json

# Invoice data from Step 2
invoice_json = json.dumps(invoice_data, indent=2)

# Supervisor plans and executes browser automation
# Using Qwen 3.5 4B with function calling + Playwright MCP tools

GOOGLE_FORM_URL = "https://forms.google.com/your-form-id"

messages = [
    {
        "role": "system",
        "content": f"""/think
You are a browser automation agent. You have access to Playwright MCP tools.

Your task:
1. Navigate to the Google Form at {GOOGLE_FORM_URL}
2. Fill in the form fields using this invoice data:
{invoice_json}
3. Map the JSON fields to the form fields by matching labels
4. Submit the form
5. Confirm submission was successful

Use the Playwright MCP tools to interact with the browser.
Think step by step about which fields to fill and in what order."""
    },
    {
        "role": "user",
        "content": "Please fill the Google Form with the invoice data. Start by navigating to the form URL."
    }
]

# The supervisor calls Playwright MCP tools in a loop:
# browser_navigate → browser_snapshot → browser_type → browser_click → ...
response = ollama.chat(
    model="qwen3.5:4b",
    messages=messages,
    tools=[
        # Playwright MCP tools are exposed as function definitions
        {"type": "function", "function": {"name": "browser_navigate", "parameters": {"url": "string"}}},
        {"type": "function", "function": {"name": "browser_snapshot", "parameters": {}}},
        {"type": "function", "function": {"name": "browser_type", "parameters": {"element": "string", "text": "string"}}},
        {"type": "function", "function": {"name": "browser_click", "parameters": {"element": "string"}}},
    ]
)
```

**Output**: Google Form submitted with invoice data

---

## Orchestration Options

### Option A: Simple Python Script (recommended for demo)

A linear Python script that calls each step sequentially. Easiest to demo, easiest to debug live.

```python
# demo_pipeline.py
import time

print("=" * 60)
print("MULTI-AGENT SLM PIPELINE — ZERO CLOUD APIs")
print("=" * 60)

# Step 1: PDF → Text
print("\n[STEP 1] OCR Worker (OCRFlux-3B, 3B params, Ollama)")
print("-" * 40)
t1 = time.time()
raw_text = ocr_worker("invoice.pdf")  # function from Step 1 above
print(f"✅ Extracted {len(raw_text)} chars in {time.time()-t1:.1f}s")

# Step 2: Text → JSON
print("\n[STEP 2] JSON Worker (Osmosis-0.6B, 600M params, MLX)")
print("-" * 40)
t2 = time.time()
invoice_data = json_worker(raw_text)  # function from Step 2 above
print(f"✅ Structured into {len(invoice_data['line_items'])} line items in {time.time()-t2:.1f}s")
print(json.dumps(invoice_data, indent=2))

# Step 3: JSON → Browser
print("\n[STEP 3] Browser Worker (Qwen 3.5 4B + Playwright MCP)")
print("-" * 40)
t3 = time.time()
browser_worker(invoice_data)  # function from Step 3 above
print(f"✅ Form submitted in {time.time()-t3:.1f}s")

print("\n" + "=" * 60)
print(f"TOTAL: {time.time()-t1:.1f}s | 3 models | 0 API calls | $0.00")
print("=" * 60)
```

### Option B: LangGraph Orchestration (if you want to show the framework)

```python
from langgraph.graph import StateGraph, START, END
from typing import TypedDict

class PipelineState(TypedDict):
    pdf_path: str
    raw_text: str
    invoice_json: dict
    form_submitted: bool
    error: str | None

def ocr_node(state: PipelineState) -> PipelineState:
    """Step 1: OCRFlux-3B extracts text from PDF"""
    state["raw_text"] = ocr_worker(state["pdf_path"])
    return state

def json_node(state: PipelineState) -> PipelineState:
    """Step 2: Osmosis-0.6B structures text into JSON"""
    state["invoice_json"] = json_worker(state["raw_text"])
    return state

def browser_node(state: PipelineState) -> PipelineState:
    """Step 3: Qwen 3.5 4B fills Google Form via Playwright MCP"""
    browser_worker(state["invoice_json"])
    state["form_submitted"] = True
    return state

def should_retry(state: PipelineState) -> str:
    """Supervisor decides: continue or retry?"""
    if state.get("error"):
        return "retry"
    return "continue"

# Build the graph
graph = StateGraph(PipelineState)
graph.add_node("ocr", ocr_node)
graph.add_node("json", json_node)
graph.add_node("browser", browser_node)

graph.add_edge(START, "ocr")
graph.add_edge("ocr", "json")
graph.add_edge("json", "browser")
graph.add_edge("browser", END)

pipeline = graph.compile()

# Run
result = pipeline.invoke({
    "pdf_path": "invoice.pdf",
    "raw_text": "",
    "invoice_json": {},
    "form_submitted": False,
    "error": None
})
```

---

## Demo Script (What to Say & Show)

### Setup (before going on stage)

```bash
# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Pre-pull models
ollama pull qwen3.5:4b
ollama pull myaniu/OCRFlux-3B

# Terminal 3: Start Playwright MCP
npx @playwright/mcp@latest

# Verify MLX model is cached
mlx_lm.generate --model mlx-community/Osmosis-Structure-0.6B-4bit --prompt "test" --max-tokens 5
```

### Live Demo Flow (~5-7 minutes)

**[Show the PDF]** — "Here's a messy invoice PDF. Tables, logos, mixed formatting. Let's process it end-to-end with three SLMs."

**[Run Step 1]** — "First, OCRFlux-3B — a 3B vision model — extracts the text. Watch the terminal... it reads the image directly, no OCR pipeline needed."
- Show: raw Markdown output with tables preserved
- Metric: time taken, model size

**[Run Step 2]** — "Now Osmosis at just 0.6 billion parameters — trained via reinforcement learning specifically for JSON extraction — structures this into clean JSON."
- Show: validated JSON output
- Metric: time taken (should be <1s on MLX), tokens/sec

**[Run Step 3]** — "Finally, Qwen 3.5 4B acts as our supervisor AND browser agent. It reads the JSON, opens a headless Chrome via Playwright MCP, and fills the Google Form."
- Show: browser opening, fields being filled, form submitted
- Metric: total time, zero API calls

**[Show Summary]** — "Three models. 0.6B + 3B + 4B. Total cost: $0.00. Runs on this laptop with WiFi off."

---

## Key Talking Points During Demo

1. **Right-sized models**: OCRFlux for vision, Osmosis for JSON, Qwen for reasoning and tool use. No model does everything — each does one thing well.

2. **Mixed runtimes**: MLX for the tiny text model (speed), Ollama for vision and tool-calling models (ecosystem). This IS the production pattern.

3. **MCP is the glue**: Playwright MCP lets the SLM control a browser without being trained on browser automation. The model just calls functions — MCP handles the rest.

4. **Verification at each step**: The supervisor validates OCR output before passing to JSON, validates JSON schema before passing to browser. A 1B model can verify a 3B model's work.

5. **Failure recovery**: If Step 2 produces invalid JSON, the supervisor can retry with a different prompt or fall back to a larger model. Show this if time permits.

---

## File Structure for the Demo

```
demo/
├── architecture.md          # This file
├── demo_pipeline.py         # Main demo script (Option A)
├── langgraph_pipeline.py    # LangGraph version (Option B)
├── invoice.pdf              # Sample messy invoice
├── mcp_config.json          # Playwright MCP server config
├── requirements.txt         # Python dependencies
└── README.md                # Quick setup instructions
```

### requirements.txt

```
ollama
mlx-lm
pdf2image
Pillow
langgraph          # only for Option B
langchain-mcp-adapters  # only for Option B
```

---

## Pre-demo Checklist

- [ ] Ollama running (`ollama serve`)
- [ ] All 3 models pulled and tested: `qwen3.5:4b`, `myaniu/OCRFlux-3B`, MLX Osmosis
- [ ] Playwright MCP server starts cleanly (`npx @playwright/mcp@latest`)
- [ ] Sample invoice.pdf ready (use a real-looking invoice with tables)
- [ ] Google Form created with matching fields (invoice_number, date, vendor, line_items, total)
- [ ] Google Form URL hardcoded in script
- [ ] `demo_pipeline.py` tested end-to-end
- [ ] WiFi ON only for Google Form submission (or use a local form as alternative)
- [ ] Backup: pre-recorded video of the full pipeline running
- [ ] Terminal font size 18+, dark theme

---

## Fallback: Local Form Instead of Google Form

If WiFi is unreliable at the venue, replace Google Form with a local HTML form:

```bash
# Serve a simple local form
python -m http.server 8080 --directory ./local_form/
```

Then point Playwright at `http://localhost:8080/form.html`. The demo stays 100% offline.
