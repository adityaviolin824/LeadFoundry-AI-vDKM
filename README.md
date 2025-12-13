# LeadFoundry AI vDKM (Technical Summary)

## Architecture Diagram
![Architecture Diagram](templates/architecture_diagram.jpg)

---

## 1. User Input → Query Generation
User preferences are processed by an intake agent that produces **3 to 5 optimized search queries**.  
These queries act as the root of all downstream lead discovery.

The intake stage:
- Validates and normalizes user constraints
- Generates search-intent-aligned queries
- Persists inputs atomically per run
- Remains fully deterministic and idempotent

---

## 2. Lead Search Agents
The system runs four research agents:
- LinkedIn research agent  
- Facebook research agent  
- Company website research agent  
- Google Maps or SERP API agent  

Each agent:
- Uses MCP search tools when available (DuckDuckGo MCP first, Tavily fallback)
- Never uses unauthorized APIs/extraction tools
- Runs inside its own isolated MCP session
- Produces structured or semi-structured lead data for normalization

Agents operate independently, ensuring that failure in one source never blocks others.

---

## 3. Multi-run, async-first execution model
LeadFoundry supports **multiple simultaneous research runs**, each identified by a unique **run ID**.

Each run is sandboxed inside:
- its own run folder
- its own configuration
- its own cancellation token
- its own progress files
- its own run-specific MCP sessions

This allows high throughput without cross-contamination or shared-state bugs.

---

### 3.1 Strong async architecture
The API is built around a strict async-first design:
- `asyncio.Task` for non-blocking pipeline stages
- async semaphores to cap concurrent execution
- `asyncio.to_thread` for CPU-bound or blocking I/O
- thread-safe `threading.Event` for cancellation compatibility
- per-stage progress files written using atomic I/O
- async locks guarding all shared registries

This produces predictable execution even under load.

---

### 3.2 Safe isolated run directories
Each run creates the following structure:

/runs/<run_id>/
├── .pipeline.lock
├── inputs/
└── outputs/


This guarantees:
- Parallel users do not collide
- Partial failures are fully contained
- Writes are never shared across runs
- Old runs can be safely garbage-collected

---

## 4. MCP-enabled multi-source research
For every optimized query:

### 4.1 Search resolution
Agents resolve data using:
- DuckDuckGo Search MCP as primary
- Tavily when MCP returns insufficient results
- SERP API for Google Maps and place-level signals

Search providers are dynamically selected with graceful fallback.

---

### 4.2 Structuring and normalization
A strict LLM-based structuring layer:
- Converts raw agent output into a fixed LeadList schema
- Fills missing fields with `"unknown"`
- Validates emails, phone numbers, and URLs
- Rejects malformed JSON and retries safely
- Guarantees deterministic output shape

No downstream stage ever consumes unvalidated data.

---

### 4.3 Full error isolation and strong exception handling
The research layer is designed for safe degradation:
- Individual agent failures do not stop the run
- Exceptions are captured as structured error objects
- Partial results are preserved
- Async task boundaries prevent cascading failures
- The pipeline proceeds unless explicitly cancelled

The goal is stability, not forced success.

---

## 5. Consolidation and raw storage
After all queries complete:
- Leads are appended into a consolidated JSON file
- Deduplication is intentionally deferred
- Atomic writes guarantee crash-safe persistence
- Backups prevent accidental overwrite
- Invalid writes never corrupt existing data

Raw data is preserved exactly as produced.

---

## 6. Downstream processing and delivery
A dedicated downstream stage performs:
- deduplication
- contact completeness scoring
- ranking
- Excel export

This stage can be triggered:
- manually via API
- automatically when email delivery is enabled

When an email is provided:
- research → finalize → email delivery happens automatically
- Excel is attached if available
- graceful fallback sends HTML-only email if Excel generation fails
- delivery status is persisted per run

The research layer remains purely data-focused.

---

## One sentence summary
Async-first, multi-run lead research system with run-level isolation, MCP-powered agents, strict LLM structuring, atomic persistence, automatic email delivery, and robust failure containment that guarantees safe partial completion under real-world conditions.
