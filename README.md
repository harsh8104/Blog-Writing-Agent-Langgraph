# Blog-Write — FastAPI backend

This workspace contains a LangGraph-based blog writer. I added a minimal FastAPI backend to invoke the compiled graph and to download generated bundles.

Quick start

1. Install requirements:

```powershell
python -m pip install -r requirements.txt
```

2. Run the API server:

```powershell
uvicorn app.api.main:app --reload --port 8000
```

3. POST to `/generate` with JSON body:

```json
{ "topic": "Your topic here" }
```

The endpoint will synchronously invoke the compiled graph and return the final state as JSON.

4. If a markdown file `my_blog.md` exists, download a bundle:

GET `/download/bundle/my_blog`

Notes
- The graph relies on environment variables and LLM/image provider keys (use `.env`).
- Streamlit UI entrypoint: run `streamlit run app/ui/streamlit_app.py`.
