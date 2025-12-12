# LeadFoundry AI (Technical Summary)

## Architecture Diagram
![Architecture Diagram](templates/architecture_diagram.jpg)

### 1. User Input → Query Generation
User preferences are passed to an intake agent that produces **3 to 5 optimized search queries**. These queries drive all downstream lead discovery.

### 2. Lead Search Agents
The system uses four research agents:
* LinkedIn research agent
* Facebook research agent
* Company website research agent
* Google Maps / SERPAPI research agent

Each agent:
* Uses official APIs or MCP-based search tools (DuckDuckGo MCP as primary, Tavily as fallback).
* Never performs illegitimate scraping or direct HTML parsing.
* Runs inside a clean MCP session created for each execution.

### 3. Multi-source Research Execution
For each of the generated search queries:

#### 3.1 MCP-enabled search
Agents attempt search through:
* **DuckDuckGo Search MCP** first
* **Tavily** only if MCP returns too few results or crashes
* **SERPAPI** is used for Google Maps data when needed

#### 3.2 Structuring and normalization
Raw outputs from each agent are passed to a strict LLM structuring agent that:
* Normalizes results into the `LeadList` schema
* Forces "unknown" for missing fields
* Validates and sanitizes URLs
* Ensures output is valid JSON before accepting it

All inconsistencies in upstream agent outputs are resolved here.

#### 3.3 Error isolation
Any agent failure:
* Is captured without stopping the pipeline
* Is recorded as a structured error object
* Does not affect other agents or overall execution

### 4. Output Handling
Research results can appear in different shapes (`leads`, `results`, or raw lists).
* These are normalized into a list of lead dictionaries before consolidation.

### 5. Consolidation and Raw Storage
After all agents finish:
* Existing JSON is loaded if valid
* New leads are appended (no deduplication at this stage)
* File is written using atomic writes to avoid corruption
* A backup of the previous JSON is optionally created

The pipeline guarantees safe writes even in cases of crashes or partial failures.

### 6. Downstream Processing (outside this script)
Another stage performs:
* deduplication
* completeness scoring
* ranking
* Excel export

The lead search script’s responsibility ends at safe, consistent raw lead storage.

---

### One-sentence summary
> **Intake → 3–5 queries → four MCP/API-based research agents → strict LLM structuring → atomic, backed-up raw JSON storage with full error isolation.**
