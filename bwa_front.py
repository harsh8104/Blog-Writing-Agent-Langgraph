from __future__ import annotations

import json
import os
import re
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple

import pandas as pd
import requests
import streamlit as st


# -----------------------------
# Helpers (unchanged logic)
# -----------------------------
def safe_slug(title: str) -> str:
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9 _-]+", "", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s or "blog"


def bundle_zip(md_text: str, md_filename: str, images_dir: Path) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(md_filename, md_text.encode("utf-8"))
        if images_dir.exists() and images_dir.is_dir():
            for p in images_dir.rglob("*"):
                if p.is_file():
                    z.write(p, arcname=str(p))
    return buf.getvalue()


def images_zip(images_dir: Path) -> Optional[bytes]:
    if not images_dir.exists() or not images_dir.is_dir():
        return None
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in images_dir.rglob("*"):
            if p.is_file():
                z.write(p, arcname=str(p))
    return buf.getvalue()


def call_generate(api_base: str, topic: str, as_of: str) -> Dict[str, Any]:
    resp = requests.post(
        f"{api_base.rstrip('/')}/generate",
        json={"topic": topic, "as_of": as_of},
        timeout=600,
    )
    resp.raise_for_status()
    return resp.json()


def call_generate_stream(api_base: str, topic: str, as_of: str):
    with requests.post(
        f"{api_base.rstrip('/')}/generate/stream",
        json={"topic": topic, "as_of": as_of},
        timeout=600,
        stream=True,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            yield json.loads(line)


def call_generate_plan(api_base: str, topic: str, as_of: str) -> Dict[str, Any]:
    resp = requests.post(
        f"{api_base.rstrip('/')}/generate/plan",
        json={"topic": topic, "as_of": as_of},
        timeout=600,
    )
    resp.raise_for_status()
    return resp.json()


def call_generate_continue_stream(api_base: str, payload: Dict[str, Any]):
    with requests.post(
        f"{api_base.rstrip('/')}/generate/continue/stream",
        json=payload,
        timeout=600,
        stream=True,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            yield json.loads(line)


# -----------------------------
# Markdown renderer that supports local images (unchanged)
# -----------------------------
_MD_IMG_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)")
_CAPTION_LINE_RE = re.compile(r"^\*(?P<cap>.+)\*$")


def _resolve_image_path(src: str) -> Path:
    src = src.strip().lstrip("./")
    return Path(src).resolve()


def render_markdown_with_local_images(md: str):
    matches = list(_MD_IMG_RE.finditer(md))
    if not matches:
        st.markdown(md, unsafe_allow_html=False)
        return

    parts: List[Tuple[str, str]] = []
    last = 0
    for m in matches:
        before = md[last : m.start()]
        if before:
            parts.append(("md", before))
        alt = (m.group("alt") or "").strip()
        src = (m.group("src") or "").strip()
        parts.append(("img", f"{alt}|||{src}"))
        last = m.end()

    tail = md[last:]
    if tail:
        parts.append(("md", tail))

    i = 0
    while i < len(parts):
        kind, payload = parts[i]
        if kind == "md":
            st.markdown(payload, unsafe_allow_html=False)
            i += 1
            continue

        alt, src = payload.split("|||", 1)
        caption = None
        if i + 1 < len(parts) and parts[i + 1][0] == "md":
            nxt = parts[i + 1][1].lstrip()
            if nxt.strip():
                first_line = nxt.splitlines()[0].strip()
                mcap = _CAPTION_LINE_RE.match(first_line)
                if mcap:
                    caption = mcap.group("cap").strip()
                    rest = "\n".join(nxt.splitlines()[1:])
                    parts[i + 1] = ("md", rest)

        if src.startswith("http://") or src.startswith("https://"):
            st.image(src, caption=caption or (alt or None), use_container_width=True)
        else:
            img_path = _resolve_image_path(src)
            if img_path.exists():
                st.image(str(img_path), caption=caption or (alt or None), use_container_width=True)
            else:
                st.warning(f"Image not found: `{src}` (looked for `{img_path}`)")
        i += 1


# -----------------------------
# Past blogs helpers (unchanged)
# -----------------------------
def list_past_blogs() -> List[Path]:
    cwd = Path(".")
    files = [p for p in cwd.glob("*.md") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def read_md_file(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def extract_title_from_md(md: str, fallback: str) -> str:
    for line in md.splitlines():
        if line.startswith("# "):
            t = line[2:].strip()
            return t or fallback
    return fallback


# -----------------------------
# Custom CSS — Modern Editorial Dark Theme
# -----------------------------
st.set_page_config(
    page_title="Blog Writing Agent",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  /* ── Google Fonts ── */
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

  /* ── Root palette ── */
  :root {
    --bg:        #0f1117;
    --surface:   #181c27;
    --surface2:  #1f2535;
    --border:    #2a2f42;
    --amber:     #f5a623;
    --amber-dim: #c17d0e;
    --text:      #e8eaf0;
    --muted:     #7a8099;
    --success:   #3ecf8e;
    --error:     #f25f5c;
  }

  /* ── Global resets ── */
  html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif !important;
    background-color: var(--bg) !important;
    color: var(--text) !important;
  }

  /* ── Hide Streamlit chrome ── */
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 2rem !important; padding-bottom: 4rem !important; max-width: 1280px !important; }

  /* ── App title ── */
  .app-title {
    font-family: 'DM Serif Display', serif;
    font-size: 2.4rem;
    letter-spacing: -0.02em;
    color: var(--text);
    line-height: 1.1;
    padding-bottom: 0.25rem;
  }
  .app-subtitle {
    font-size: 0.85rem;
    color: var(--muted);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-top: -0.1rem;
    margin-bottom: 1.8rem;
  }

  /* ── Sidebar ── */
  [data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
  }
  [data-testid="stSidebar"] .block-container { padding-top: 1.5rem !important; }

  /* Sidebar section labels */
  .sidebar-label {
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--amber);
    margin-bottom: 0.5rem;
    margin-top: 1.2rem;
  }

  /* ── Inputs & textareas ── */
  [data-testid="stTextArea"] textarea,
  [data-testid="stTextInput"] input {
    background: var(--surface2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--text) !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.9rem !important;
    transition: border-color 0.2s;
  }
  [data-testid="stTextArea"] textarea:focus,
  [data-testid="stTextInput"] input:focus {
    border-color: var(--amber) !important;
    box-shadow: 0 0 0 2px rgba(245,166,35,0.15) !important;
  }

  /* ── Date input ── */
  [data-testid="stDateInput"] input {
    background: var(--surface2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--text) !important;
  }

  /* ── Primary button (Generate Plan) ── */
  .stButton > button[kind="primary"] {
    background: var(--amber) !important;
    color: #0f1117 !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    letter-spacing: 0.03em !important;
    padding: 0.55rem 1.2rem !important;
    width: 100% !important;
    transition: background 0.2s, transform 0.1s !important;
  }
  .stButton > button[kind="primary"]:hover {
    background: var(--amber-dim) !important;
    transform: translateY(-1px) !important;
  }

  /* ── Secondary buttons ── */
  .stButton > button:not([kind="primary"]) {
    background: var(--surface2) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    padding: 0.5rem 1rem !important;
    width: 100% !important;
    transition: border-color 0.2s, background 0.2s !important;
  }
  .stButton > button:not([kind="primary"]):hover {
    border-color: var(--amber) !important;
    background: rgba(245,166,35,0.06) !important;
  }

  /* ── Download buttons ── */
  [data-testid="stDownloadButton"] button {
    background: var(--surface2) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    transition: border-color 0.2s, background 0.2s !important;
  }
  [data-testid="stDownloadButton"] button:hover {
    border-color: var(--amber) !important;
    background: rgba(245,166,35,0.06) !important;
  }

  /* ── Tabs ── */
  [data-testid="stTabs"] [role="tablist"] {
    border-bottom: 1px solid var(--border) !important;
    gap: 0 !important;
    background: transparent !important;
  }
  [data-testid="stTabs"] button[role="tab"] {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.03em !important;
    color: var(--muted) !important;
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    padding: 0.6rem 1.1rem !important;
    border-radius: 0 !important;
    transition: color 0.2s, border-color 0.2s !important;
  }
  [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: var(--amber) !important;
    border-bottom: 2px solid var(--amber) !important;
  }
  [data-testid="stTabs"] button[role="tab"]:hover {
    color: var(--text) !important;
  }
  [data-testid="stTabs"] [role="tabpanel"] {
    padding-top: 1.5rem !important;
  }

  /* ── DataFrames ── */
  [data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    overflow: hidden !important;
  }
  [data-testid="stDataFrame"] th {
    background: var(--surface2) !important;
    color: var(--muted) !important;
    font-size: 0.75rem !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
    font-weight: 600 !important;
  }
  [data-testid="stDataFrame"] td {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.85rem !important;
    color: var(--text) !important;
  }

  /* ── Info / warning / error banners ── */
  [data-testid="stAlert"] {
    border-radius: 10px !important;
    border: 1px solid var(--border) !important;
    background: var(--surface2) !important;
    font-size: 0.87rem !important;
  }

  /* ── Status / spinner ── */
  [data-testid="stStatusWidget"] {
    background: var(--surface2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
  }

  /* ── Expander ── */
  [data-testid="stExpander"] {
    background: var(--surface2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
  }
  [data-testid="stExpander"] summary {
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    color: var(--muted) !important;
  }

  /* ── Radio (past blogs list) ── */
  [data-testid="stRadio"] label {
    font-size: 0.82rem !important;
    color: var(--text) !important;
    padding: 4px 0 !important;
  }
  [data-testid="stRadio"] label:hover { color: var(--amber) !important; }

  /* ── Text areas (log) ── */
  textarea {
    background: var(--surface2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--muted) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.78rem !important;
  }

  /* ── Divider ── */
  hr { border-color: var(--border) !important; margin: 1.2rem 0 !important; }

  /* ── Markdown headings ── */
  h1 { font-family: 'DM Serif Display', serif !important; font-size: 2rem !important; color: var(--text) !important; }
  h2 { font-family: 'DM Serif Display', serif !important; font-size: 1.5rem !important; color: var(--text) !important; }
  h3 { font-family: 'DM Sans', sans-serif !important; font-weight: 600 !important; font-size: 1.1rem !important; color: var(--text) !important; }

  /* ── Approval section card ── */
  .approval-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 3px solid var(--amber);
    border-radius: 12px;
    padding: 1.4rem 1.6rem;
    margin-top: 2rem;
  }
  .approval-title {
    font-family: 'DM Sans', sans-serif;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--amber);
    margin-bottom: 0.4rem;
  }
  .approval-desc {
    font-size: 0.9rem;
    color: var(--muted);
    margin-bottom: 1rem;
  }

  /* ── Stat pill ── */
  .stat-pill {
    display: inline-block;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 0.78rem;
    color: var(--muted);
    margin-right: 6px;
  }
  .stat-pill span { color: var(--text); font-weight: 600; }

  /* ── Blog list item in sidebar ── */
  .blog-entry {
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 0.8rem;
    line-height: 1.4;
    border-left: 2px solid transparent;
    margin-bottom: 2px;
  }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 5px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

  /* ── Plan meta row ── */
  .plan-meta-row {
    display: flex;
    gap: 12px;
    margin: 1rem 0 1.4rem;
    flex-wrap: wrap;
  }
  .plan-meta-item {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 14px;
    min-width: 130px;
  }
  .plan-meta-key {
    font-size: 0.68rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    font-weight: 600;
    margin-bottom: 3px;
  }
  .plan-meta-val {
    font-size: 0.9rem;
    color: var(--text);
    font-weight: 500;
  }
</style>
""", unsafe_allow_html=True)


# -----------------------------
# Page header
# -----------------------------
st.markdown('<div class="app-title">Blog Writing Agent</div>', unsafe_allow_html=True)
st.markdown('<div class="app-subtitle">Powered by LangGraph · AI-assisted authorship</div>', unsafe_allow_html=True)


# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.markdown('<div class="sidebar-label">New Blog</div>', unsafe_allow_html=True)

    topic = st.text_area(
        "Topic",
        height=130,
        placeholder="e.g. The rise of agentic AI in 2025 and what it means for software engineers…",
        label_visibility="collapsed",
    )

    col_date, col_url = st.columns([1, 1])
    with col_date:
        st.markdown('<div style="font-size:0.78rem;color:#7a8099;margin-bottom:4px;font-weight:500;">As-of date</div>', unsafe_allow_html=True)
        as_of = st.date_input("As-of date", value=date.today(), label_visibility="collapsed")
    with col_url:
        st.markdown('<div style="font-size:0.78rem;color:#7a8099;margin-bottom:4px;font-weight:500;">API base URL</div>', unsafe_allow_html=True)
        api_base = st.text_input("API base URL", value="http://localhost:8000", label_visibility="collapsed")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    run_btn = st.button("🚀  Generate Plan", type="primary")

    # ── Past blogs ──
    st.markdown('<div class="sidebar-label" style="margin-top:1.6rem;">Past Blogs</div>', unsafe_allow_html=True)

    past_files = list_past_blogs()
    if not past_files:
        st.markdown('<div style="font-size:0.8rem;color:#7a8099;padding:6px 0;">No saved blogs found (*.md in current folder).</div>', unsafe_allow_html=True)
        selected_md_file = None
    else:
        options: List[str] = []
        file_by_label: Dict[str, Path] = {}
        for p in past_files[:50]:
            try:
                md_text = read_md_file(p)
                title = extract_title_from_md(md_text, p.stem)
            except Exception:
                title = p.stem
            label = f"{title}  ·  {p.name}"
            options.append(label)
            file_by_label[label] = p

        selected_label = st.radio(
            "Select a blog to load",
            options=options,
            index=0,
            label_visibility="collapsed",
        )
        selected_md_file = file_by_label.get(selected_label)

        if st.button("📂  Load selected blog"):
            if selected_md_file:
                md_text = read_md_file(selected_md_file)
                st.session_state["last_out"] = {
                    "plan": None,
                    "evidence": [],
                    "image_specs": [],
                    "final": md_text,
                }
                st.session_state["topic_prefill"] = extract_title_from_md(md_text, selected_md_file.stem)


# ── Session state init ──
if "last_out" not in st.session_state:
    st.session_state["last_out"] = None
if "pending_plan" not in st.session_state:
    st.session_state["pending_plan"] = None
if "pending_context" not in st.session_state:
    st.session_state["pending_context"] = None

logs: List[str] = []
def log(msg: str):
    logs.append(msg)


# ── Generate plan ──
if run_btn:
    if not topic.strip():
        st.warning("Please enter a topic.")
        st.stop()

    status = st.status("Generating plan…", expanded=True)
    try:
        plan_out = call_generate_plan(api_base, topic.strip(), as_of.isoformat())
        st.session_state["pending_plan"] = plan_out
        st.session_state["pending_context"] = {
            "topic": topic.strip(),
            "as_of": as_of.isoformat(),
        }
        st.session_state["last_out"] = None
        status.update(label="✅ Plan ready — awaiting your approval", state="complete", expanded=False)
        log("[plan] received plan")
        log(f"[plan] {json.dumps(plan_out, default=str)[:1200]}")
    except Exception as e:
        status.update(label="❌ Failed", state="error", expanded=True)
        st.error(f"API call failed: {e}")


def _selected_output() -> Optional[Dict[str, Any]]:
    return st.session_state.get("last_out") or st.session_state.get("pending_plan")


out = _selected_output()

if out:
    tab_plan, tab_evidence, tab_preview, tab_images, tab_logs = st.tabs(
        ["🧩  Plan", "🔎  Evidence", "📝  Preview", "🖼️  Images", "🧾  Logs"]
    )

    # ── Plan tab ──
    with tab_plan:
        plan_obj = out.get("plan")
        if not plan_obj:
            st.info("No plan found in output.")
        else:
            if hasattr(plan_obj, "model_dump"):
                plan_dict = plan_obj.model_dump()
            elif isinstance(plan_obj, dict):
                plan_dict = plan_obj
            else:
                plan_dict = json.loads(json.dumps(plan_obj, default=str))

            # Title
            blog_title_display = plan_dict.get("blog_title", "—")
            st.markdown(
                f'<div style="font-family:\'DM Serif Display\',serif;font-size:1.6rem;color:#e8eaf0;margin-bottom:0.8rem;">{blog_title_display}</div>',
                unsafe_allow_html=True,
            )

            # Meta pills
            meta_html = '<div class="plan-meta-row">'
            for key, label in [("audience", "Audience"), ("tone", "Tone"), ("blog_kind", "Format")]:
                val = plan_dict.get(key, "—") or "—"
                meta_html += f'<div class="plan-meta-item"><div class="plan-meta-key">{label}</div><div class="plan-meta-val">{val}</div></div>'
            meta_html += "</div>"
            st.markdown(meta_html, unsafe_allow_html=True)

            tasks = plan_dict.get("tasks", [])
            if tasks:
                st.markdown(
                    f'<div style="font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;color:#7a8099;font-weight:600;margin-bottom:0.6rem;">{len(tasks)} sections planned</div>',
                    unsafe_allow_html=True,
                )
                df = pd.DataFrame(
                    [
                        {
                            "id": t.get("id"),
                            "title": t.get("title"),
                            "words": t.get("target_words"),
                            "research": "✓" if t.get("requires_research") else "—",
                            "citations": "✓" if t.get("requires_citations") else "—",
                            "code": "✓" if t.get("requires_code") else "—",
                            "tags": ", ".join(t.get("tags") or []),
                        }
                        for t in tasks
                    ]
                ).sort_values("id")
                st.dataframe(df, use_container_width=True, hide_index=True)

                with st.expander("Raw task JSON"):
                    st.json(tasks)

    # ── Evidence tab ──
    with tab_evidence:
        evidence = out.get("evidence") or []
        if not evidence:
            st.info("No evidence returned — closed-book mode or no results.")
        else:
            st.markdown(
                f'<div style="font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;color:#7a8099;font-weight:600;margin-bottom:0.8rem;">{len(evidence)} sources retrieved</div>',
                unsafe_allow_html=True,
            )
            rows = []
            for e in evidence:
                if hasattr(e, "model_dump"):
                    e = e.model_dump()
                rows.append({
                    "title": e.get("title"),
                    "published_at": e.get("published_at"),
                    "source": e.get("source"),
                    "url": e.get("url"),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Preview tab ──
    with tab_preview:
        final_md = out.get("final") or ""
        if not final_md:
            st.warning("No final markdown found.")
        else:
            # Render in a clean content column
            col_content, col_actions = st.columns([3, 1])

            with col_content:
                render_markdown_with_local_images(final_md)

            with col_actions:
                st.markdown(
                    '<div style="font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;color:#7a8099;font-weight:600;margin-bottom:0.8rem;">Export</div>',
                    unsafe_allow_html=True,
                )

                plan_obj = out.get("plan")
                if hasattr(plan_obj, "blog_title"):
                    blog_title = plan_obj.blog_title
                elif isinstance(plan_obj, dict):
                    blog_title = plan_obj.get("blog_title", "blog")
                else:
                    blog_title = extract_title_from_md(final_md, "blog")

                md_filename = f"{safe_slug(blog_title)}.md"
                st.download_button(
                    "⬇️  Markdown (.md)",
                    data=final_md.encode("utf-8"),
                    file_name=md_filename,
                    mime="text/markdown",
                )
                st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
                bundle = bundle_zip(final_md, md_filename, Path("images"))
                st.download_button(
                    "📦  Full bundle (.zip)",
                    data=bundle,
                    file_name=f"{safe_slug(blog_title)}_bundle.zip",
                    mime="application/zip",
                )

    # ── Images tab ──
    with tab_images:
        specs = out.get("image_specs") or []
        images_dir = Path("images")

        if not specs and not images_dir.exists():
            st.info("No images generated for this blog.")
        else:
            if specs:
                st.markdown(
                    '<div style="font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;color:#7a8099;font-weight:600;margin-bottom:0.6rem;">Image plan</div>',
                    unsafe_allow_html=True,
                )
                st.json(specs)

            if images_dir.exists():
                files = [p for p in images_dir.iterdir() if p.is_file()]
                if not files:
                    st.warning("images/ directory exists but is empty.")
                else:
                    img_cols = st.columns(3)
                    for idx, p in enumerate(sorted(files)):
                        with img_cols[idx % 3]:
                            st.image(str(p), caption=p.name, use_container_width=True)

                z = images_zip(images_dir)
                if z:
                    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
                    st.download_button(
                        "⬇️  Download all images (.zip)",
                        data=z,
                        file_name="images.zip",
                        mime="application/zip",
                    )

    # ── Logs tab ──
    with tab_logs:
        if "logs" not in st.session_state:
            st.session_state["logs"] = []
        if logs:
            st.session_state["logs"].extend(logs)

        st.markdown(
            '<div style="font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;color:#7a8099;font-weight:600;margin-bottom:0.6rem;">Event log</div>',
            unsafe_allow_html=True,
        )
        st.text_area(
            "log",
            value="\n\n".join(st.session_state["logs"][-80:]),
            height=520,
            label_visibility="collapsed",
        )

# ── Empty state ──
else:
    st.markdown(
        """
        <div style="
          margin-top: 3rem;
          text-align: center;
          padding: 4rem 2rem;
          border: 1px dashed #2a2f42;
          border-radius: 16px;
          color: #7a8099;
        ">
          <div style="font-size:2.5rem;margin-bottom:1rem;">✍️</div>
          <div style="font-family:'DM Serif Display',serif;font-size:1.3rem;color:#e8eaf0;margin-bottom:0.5rem;">
            Start with a topic
          </div>
          <div style="font-size:0.88rem;max-width:400px;margin:0 auto;line-height:1.6;">
            Enter your blog topic in the sidebar, pick an as-of date, and click
            <strong style="color:#f5a623;">Generate Plan</strong> to get started.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Human approval section ──
pending_plan = st.session_state.get("pending_plan")
pending_context = st.session_state.get("pending_context")

if pending_plan and pending_context:
    st.markdown(
        """
        <div class="approval-card">
          <div class="approval-title">Awaiting your approval</div>
          <div class="approval-desc">Review the plan above, then approve to generate the full blog or regenerate for a new plan.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)

    col_approve, col_regen, col_spacer = st.columns([1, 1, 2])
    with col_approve:
        if st.button("✅  Approve & Generate"):
            status = st.status("Generating blog…", expanded=True)
            try:
                payload = {
                    "topic": pending_context["topic"],
                    "as_of": pending_context["as_of"],
                    "mode": pending_plan.get("mode"),
                    "needs_research": pending_plan.get("needs_research"),
                    "queries": pending_plan.get("queries"),
                    "recency_days": pending_plan.get("recency_days"),
                    "plan": pending_plan.get("plan"),
                    "evidence": pending_plan.get("evidence"),
                }
                final_out = None
                for event in call_generate_continue_stream(api_base, payload):
                    if event.get("event") == "node":
                        node = event.get("node", "unknown")
                        status.update(label=f"Running: {node}…", state="running", expanded=True)
                        log(f"[node] {node}")
                    elif event.get("event") == "final":
                        final_out = event.get("data")
                        break
                    elif event.get("event") == "error":
                        raise RuntimeError(event.get("message", "Unknown error"))

                if final_out is None:
                    raise RuntimeError("No final result received from stream.")

                st.session_state["last_out"] = final_out
                st.session_state["pending_plan"] = None
                st.session_state["pending_context"] = None
                status.update(label="✅ Blog generated successfully", state="complete", expanded=False)
                log("[final] received final state")
                log(f"[final] {json.dumps(final_out, default=str)[:1200]}")
                st.rerun()
            except Exception as e:
                status.update(label="❌ Failed", state="error", expanded=True)
                st.error(f"API call failed: {e}")

    with col_regen:
        if st.button("🔁  Regenerate Plan"):
            status = st.status("Regenerating plan…", expanded=True)
            try:
                plan_out = call_generate_plan(api_base, pending_context["topic"], pending_context["as_of"])
                st.session_state["pending_plan"] = plan_out
                status.update(label="✅ Plan updated", state="complete", expanded=False)
                log("[plan] regenerated plan")
                st.rerun()
            except Exception as e:
                status.update(label="❌ Failed", state="error", expanded=True)
                st.error(f"API call failed: {e}")