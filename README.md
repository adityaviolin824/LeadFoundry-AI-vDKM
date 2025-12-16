# LeadFoundry AI

LeadFoundry AI automates lead research by searching LinkedIn, Facebook, company websites, and Google Maps to find business contact information that matches user-defined criteria. It runs multiple searches in parallel, structures results into a clean Excel deliverable, and optionally emails the output when the run completes.

## Live Demo

* **API Backend**: Deployed on Google Cloud Run
* **Frontend UI**: Deployed on Streamlit Cloud
* **Architecture**: Decoupled deployment with a FastAPI backend handling orchestration and a Streamlit frontend for interactive submissions

![Architecture Diagram](templates/architecture_diagram.png)

## How It Works

### Query Generation

Users provide search criteria such as industry, location, personas, and keywords. An intake agent converts these inputs into 3–5 optimized search queries designed to maximize coverage while avoiding duplicate result sets. Each run includes at least one contact-focused query to surface pages containing email or phone information.

### Multi‑Agent Research

Each query is distributed across four specialized agents running in parallel:

* **LinkedIn Agent**: Retrieves company profiles and business pages
* **Facebook Agent**: Locates business pages and public contact information
* **Website Agent**: Inspects company websites and extracts data from `/contact`, `/about`, and footer sections
* **Maps Agent**: Uses SERP API to extract business listings from Google Maps

Agents execute independently. Failures in one source do not block others, allowing the system to return partial but valid results when external services are unavailable.

### Structuring and Validation

Raw outputs from all agents are passed through a structuring layer that enforces a strict JSON schema. Each lead is normalized into consistent fields (`company`, `website`, `email`, `phone_number`, `location`, `description`). Missing values are explicitly set to `"unknown"`, and malformed responses are rejected.

### Deduplication and Sorting

Deduplication is handled deterministically in Python using company name and website as primary keys. Leads are ranked by contact completeness, prioritizing entries that contain both email and phone information.

### Enrichment

After initial consolidation, an enrichment step revisits leads with missing contact data. This stage fetches publicly accessible website pages such as contact pages, about pages, and footers to recover email addresses or phone numbers missed during the primary search. Enrichment is performed post‑research to avoid slowing down the core pipeline.

## Usage Modes

### With Email (Fire‑and‑Forget)

Designed for asynchronous use. Users submit a request, provide an email address, and close the browser. The pipeline runs in the background and sends the Excel output upon completion, even for long‑running executions.

### Without Email (Interactive)

Users can monitor progress in real time through the UI, observe agent execution, preview intermediate results, and download the final output manually. This mode is primarily intended for testing and exploration.

## Performance Considerations

Execution time and API cost depend on agent count, query breadth, and enrichment depth. The system minimizes LLM usage by relying on deterministic Python logic wherever possible:

* Deduplication is algorithmic
* Sorting and ranking are rule‑based
* Enrichment is triggered only for missing fields

This approach keeps runs cost‑efficient while preserving output quality.

## Output Format

All leads conform to a fixed schema:

* company
* website
* email
* phone_number
* location
* description
* source
* source_urls

Results are delivered as `final_leads_list.xlsx`, containing deduplicated, enriched, and ranked leads ready for outreach.

## Technology Stack

* Python 3.12+
* FastAPI
* asyncio for parallel execution
* MCP (Model Context Protocol)
* DuckDuckGo Search MCP
* Tavily API
* SERP API
* Configurable LLM providers
* Docker
* Google Cloud Run
* Streamlit

## Deployment

The backend API is deployed on Google Cloud Run with request‑driven autoscaling. The frontend UI is deployed separately on Streamlit Cloud. Both services are fully containerized and stateless, with each pipeline run assigned its own isolated directory for progress tracking and outputs.

## Legal and Data Use

The system uses official APIs and respects provider rate limits and usage policies. Only publicly available business contact information is processed.
