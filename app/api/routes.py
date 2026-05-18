from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.blog_service import (
    generate_blog,
    generate_blog_stream,
    generate_plan,
    generate_blog_from_plan,
    generate_blog_from_plan_stream,
    bundle_zip,
)

router = APIRouter()


class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    as_of: Optional[str] = None


class GenerateFromPlanRequest(BaseModel):
    topic: str
    as_of: str
    mode: Optional[str] = None
    needs_research: Optional[bool] = None
    queries: Optional[list] = None
    recency_days: Optional[int] = None
    plan: Dict[str, Any]
    evidence: Optional[list] = None


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/generate")
def generate(req: GenerateRequest) -> dict:
    return generate_blog(req.topic, req.as_of)


@router.post("/generate/stream")
def generate_stream(req: GenerateRequest):
    return StreamingResponse(
        generate_blog_stream(req.topic, req.as_of),
        media_type="application/x-ndjson",
    )


@router.post("/generate/plan")
def generate_plan_only(req: GenerateRequest) -> dict:
    return generate_plan(req.topic, req.as_of)


@router.post("/generate/continue")
def generate_continue(req: GenerateFromPlanRequest) -> dict:
    return generate_blog_from_plan(req.model_dump())


@router.post("/generate/continue/stream")
def generate_continue_stream(req: GenerateFromPlanRequest):
    return StreamingResponse(
        generate_blog_from_plan_stream(req.model_dump()),
        media_type="application/x-ndjson",
    )


@router.get("/download/bundle/{slug}")
def download_bundle(slug: str):
    md_path = Path(f"{slug}.md")
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="Markdown file not found")

    md_text = md_path.read_text(encoding="utf-8", errors="replace")
    payload = bundle_zip(md_text, md_path.name, Path("images"))

    return StreamingResponse(
        BytesIO(payload),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={slug}.zip"},
    )
