# Blog-Write — LangGraph Blog Writer

An end-to-end, plan-first blog generation system that combines a LangGraph state machine, parallel worker agents, FastAPI APIs, and a Streamlit UI. It produces structured outlines, evidence-backed sections, image-ready markdown, and downloadable bundles.

## Highlights

- Plan-first workflow with human approval before drafting
- Parallel worker agents for section-level drafting
- Optional web research with evidence extraction and citation control
- NDJSON streaming for real-time progress updates
- Image planning and optional generation with placeholder insertion
- Export-ready markdown plus zipped image bundles

## Architecture overview

The pipeline is a LangGraph state machine:

1. **Router** decides research mode (closed_book, hybrid, open_book).
2. **Research** (optional) gathers evidence via Tavily and normalizes sources.
3. **Orchestrator** produces a structured outline (Plan schema).
4. **Workers (parallel)** draft each section based on the plan and evidence.
5. **Reducer** merges sections, inserts image placeholders, and optionally generates images.

## Project structure

- [bwa_front.py](bwa_front.py) — Streamlit UI
- [app/api/main.py](app/api/main.py) — FastAPI entrypoint
- [app/api/routes.py](app/api/routes.py) — API routes
- [app/services/blog_service.py](app/services/blog_service.py) — Orchestration for plan/stream/full runs
- [app/graph/build.py](app/graph/build.py) — LangGraph definition
- [app/nodes/](app/nodes/) — Router, research, orchestrator, worker nodes
- [app/reducer/images.py](app/reducer/images.py) — Merge + image planning/generation
- [app/schemas.py](app/schemas.py) — Pydantic models and graph state

## Tech stack

FastAPI, Streamlit, LangGraph, LangChain, OpenAI API, Tavily, Pydantic, Python, Gemini Image (optional)

## Setup

1) Install dependencies

```powershell
python -m pip install -r requirements.txt
```

2) Create a `.env` file (optional but recommended)

```env
OPENAI_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here  # optional for web research
GOOGLE_API_KEY=your_key_here  # optional for image generation
```

## Run the backend

```powershell
uvicorn app.api.main:app --reload --port 8000
```

## Run the frontend

```powershell
streamlit run bwa_front.py
```

## API endpoints

### Health

`GET /health`

### Generate full blog (sync)

`POST /generate`

```json
{ "topic": "Your topic here", "as_of": "2026-05-20" }
```

### Generate full blog (stream)

`POST /generate/stream`

NDJSON events:

```json
{"event":"node","node":"router"}
{"event":"node","node":"research"}
{"event":"final","data":{...}}
```

### Generate plan only

`POST /generate/plan`

### Continue from an approved plan (sync)

`POST /generate/continue`

```json
{
	"topic": "Your topic here",
	"as_of": "2026-05-20",
	"mode": "hybrid",
	"needs_research": true,
	"queries": ["query 1", "query 2"],
	"recency_days": 45,
	"plan": { "blog_title": "...", "audience": "...", "tone": "...", "tasks": [] },
	"evidence": []
}
```

### Continue from plan (stream)

`POST /generate/continue/stream`

### Download bundle

`GET /download/bundle/{slug}`

Downloads `{slug}.md` and any images under `images/` as a zip.

## Notes

- If `TAVILY_API_KEY` is not set, research mode will return empty evidence and proceed.
- Image generation is optional. If `GOOGLE_API_KEY` is missing, the pipeline keeps placeholders or inserts failure notes.
- Streaming endpoints use `application/x-ndjson`.

