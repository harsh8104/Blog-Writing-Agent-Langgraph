import json
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Generator, List
import zipfile

from pydantic import BaseModel

from app.graph.build import app as graph_app
from app.nodes.orchestrator import orchestrator_node
from app.nodes.research import research_node
from app.nodes.router import router_node
from app.nodes.worker import worker_node
from app.reducer.images import build_reducer_subgraph
from app.schemas import EvidenceItem, Plan


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


def generate_plan(topic: str, as_of: str | None) -> Dict[str, Any]:
    state = build_inputs(topic, as_of)

    state.update(router_node(state))
    if state.get("needs_research"):
        state.update(research_node(state))
    state.update(orchestrator_node(state))

    payload = {
        "topic": state.get("topic"),
        "mode": state.get("mode"),
        "needs_research": state.get("needs_research"),
        "queries": state.get("queries", []),
        "evidence": state.get("evidence", []),
        "plan": state.get("plan"),
        "as_of": state.get("as_of"),
        "recency_days": state.get("recency_days"),
    }
    return json.loads(json.dumps(_to_jsonable(payload), default=str))


def _ensure_plan(plan_data: Any) -> Plan:
    if isinstance(plan_data, Plan):
        return plan_data
    if isinstance(plan_data, dict):
        return Plan(**plan_data)
    return Plan(**json.loads(json.dumps(plan_data, default=str)))


def _ensure_evidence(evidence_data: Any) -> List[EvidenceItem]:
    if not evidence_data:
        return []
    if isinstance(evidence_data, list):
        return [EvidenceItem(**e) if isinstance(e, dict) else EvidenceItem(**e.model_dump()) for e in evidence_data]
    return []


def generate_blog_from_plan(payload: Dict[str, Any]) -> Dict[str, Any]:
    plan = _ensure_plan(payload.get("plan"))
    evidence = _ensure_evidence(payload.get("evidence"))

    state = build_inputs(payload.get("topic") or "", payload.get("as_of"))
    state["mode"] = payload.get("mode") or state.get("mode")
    state["needs_research"] = payload.get("needs_research", False)
    state["queries"] = payload.get("queries", [])
    state["recency_days"] = payload.get("recency_days", state.get("recency_days"))
    state["plan"] = plan
    state["evidence"] = evidence

    sections: List[tuple[int, str]] = []
    for task in plan.tasks:
        update = worker_node(
            {
                "task": task.model_dump(),
                "topic": state["topic"],
                "mode": state["mode"],
                "as_of": state["as_of"],
                "recency_days": state["recency_days"],
                "plan": plan.model_dump(),
                "evidence": [e.model_dump() for e in evidence],
            }
        )
        sections.extend(update.get("sections", []))

    state["sections"] = sections

    reducer = build_reducer_subgraph()
    state.update(reducer.invoke(state))

    return json.loads(json.dumps(_to_jsonable(state), default=str))


def generate_blog_from_plan_stream(payload: Dict[str, Any]) -> Generator[str, None, None]:
    try:
        plan = _ensure_plan(payload.get("plan"))
        evidence = _ensure_evidence(payload.get("evidence"))

        state = build_inputs(payload.get("topic") or "", payload.get("as_of"))
        state["mode"] = payload.get("mode") or state.get("mode")
        state["needs_research"] = payload.get("needs_research", False)
        state["queries"] = payload.get("queries", [])
        state["recency_days"] = payload.get("recency_days", state.get("recency_days"))
        state["plan"] = plan
        state["evidence"] = evidence
        state.setdefault("sections", [])

        for task in plan.tasks:
            yield json.dumps({"event": "node", "node": "worker"}) + "\n"
            update = worker_node(
                {
                    "task": task.model_dump(),
                    "topic": state["topic"],
                    "mode": state["mode"],
                    "as_of": state["as_of"],
                    "recency_days": state["recency_days"],
                    "plan": plan.model_dump(),
                    "evidence": [e.model_dump() for e in evidence],
                }
            )
            _apply_update(state, update)

        yield json.dumps({"event": "node", "node": "reducer"}) + "\n"
        reducer = build_reducer_subgraph()
        state.update(reducer.invoke(state))

        payload_out = json.loads(json.dumps(_to_jsonable(state), default=str))
        yield json.dumps({"event": "final", "data": payload_out}) + "\n"
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
