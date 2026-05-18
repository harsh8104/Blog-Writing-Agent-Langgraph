import json
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Generator
import zipfile

from pydantic import BaseModel

from app.graph.build import app as graph_app


def build_inputs(topic: str, as_of: str | None) -> Dict[str, Any]:
    as_of_date = as_of or date.today().isoformat()
    return {
        "topic": topic.strip(),
        "mode": "",
        "needs_research": False,
        "queries": [],
        "evidence": [],
        "plan": None,
        "as_of": as_of_date,
        "recency_days": 7,
        "sections": [],
        "merged_md": "",
        "md_with_placeholders": "",
        "image_specs": [],
        "final": "",
    }


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


def generate_blog(topic: str, as_of: str | None) -> Dict[str, Any]:
    inputs = build_inputs(topic, as_of)
    out = graph_app.invoke(inputs)
    return json.loads(json.dumps(_to_jsonable(out), default=str))


def _apply_update(state: Dict[str, Any], update: Dict[str, Any]) -> None:
    for key, value in update.items():
        if key == "sections" and isinstance(value, list):
            state.setdefault("sections", [])
            state["sections"].extend(value)
        else:
            state[key] = value


def generate_blog_stream(topic: str, as_of: str | None) -> Generator[str, None, None]:
    inputs = build_inputs(topic, as_of)
    state: Dict[str, Any] = dict(inputs)
    state.setdefault("sections", [])

    try:
        for update in graph_app.stream(inputs, stream_mode="updates"):
            if not isinstance(update, dict):
                continue
            for node_name, node_update in update.items():
                yield json.dumps({"event": "node", "node": node_name}) + "\n"
                if isinstance(node_update, dict):
                    _apply_update(state, node_update)

        payload = json.loads(json.dumps(_to_jsonable(state), default=str))
        yield json.dumps({"event": "final", "data": payload}) + "\n"
    except Exception as exc:
        yield json.dumps({"event": "error", "message": str(exc)}) + "\n"


def bundle_zip(md_text: str, md_filename: str, images_dir: Path) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(md_filename, md_text.encode("utf-8"))

        if images_dir.exists() and images_dir.is_dir():
            for p in images_dir.rglob("*"):
                if p.is_file():
                    z.write(p, arcname=str(p))
    return buf.getvalue()
