"""
FastAPI web frontend for Awareness Studio.

Endpoints:
  GET  /                           — Control Panel UI (static)
  GET  /static/*                   — Static assets
  GET  /health                     — liveness probe
  POST /chat                       — RAG query (JSON or SSE stream)
  POST /literature/search          — PubMed / bioRxiv search
  GET  /linear/search              — Linear issues (requires LINEAR_API_KEY)
  GET  /tools/list                 — list enabled tools
  GET  /airtable/status            — Airtable config check
  POST /airtable/sync/runs         — sync run cards (?allow_write=false)

Run:
  uvicorn awareness_studio.web.app:app --reload --port 8000

Environment:
  CORS_ALLOW_ORIGINS=*             — enable CORS (comma-separated origins or *)
  PORT=8000                        — port used by main() / Replit
"""
import json
import logging
import re
import threading
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from awareness_studio import config
from awareness_studio.answer_modes import build_chat_prompt
from awareness_studio.orchestrator.orchestrator import Orchestrator, OrchestratorConfig
from awareness_studio.index_build import get_or_build_index
from awareness_studio.llm_client import get_llm_client
from awareness_studio.tool_router import (
    ToolCallRecord,
    format_tool_results,
    get_tool_router,
    has_tool_trigger,
)

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Awareness Studio",
    description="Monk+Scientist RAG chatbot for the Awareness Research knowledge base.",
    version="0.3.0",
)

# ── CORS (optional, controlled by env) ───────────────────────────────────────

_cors_origins = config.CORS_ALLOW_ORIGINS
if _cors_origins:
    from fastapi.middleware.cors import CORSMiddleware
    origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ── Static files ──────────────────────────────────────────────────────────────

if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

_VALID_MODES = {"TEACH", "EXPLAIN", "ELABORATE", "MATRIX", "CARD", "CANONICAL"}


# ── Request / response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    mode: str = Field("EXPLAIN", description="One of: TEACH EXPLAIN ELABORATE MATRIX CARD CANONICAL")
    k: int = Field(config.DEFAULT_TOP_K, ge=1, le=20)
    stream: bool = Field(False, description="Return SSE token stream instead of JSON")
    use_tools: bool = Field(False, description="Enable external tool lookup for this query")
    request_id: Optional[str] = Field(None, description="Client-supplied idempotency key")


class ToolCallSummary(BaseModel):
    tool_name: str
    success: bool
    result_summary: str
    error: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    mode: str
    retrieved: int
    sources_used: List[str] = Field(default_factory=list)
    tool_calls: List[ToolCallSummary] = Field(default_factory=list)
    request_id: str = ""


class HealthResponse(BaseModel):
    status: str
    backend: str
    embedding_provider: Optional[str]
    tools_enabled: bool


class LiteratureRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    source: str = Field("pubmed", description="'pubmed' or 'biorxiv' or 'medrxiv'")
    max_results: int = Field(5, ge=1, le=20)
    as_card: bool = Field(False, description="Return results as Evidence Card drafts")


class LiteratureResult(BaseModel):
    source: str
    items: List[Dict[str, Any]]
    tool_record: Optional[Dict[str, Any]] = None


# ── Auth dependency ───────────────────────────────────────────────────────────

async def _require_auth(x_awareness_key: Optional[str] = Header(default=None)) -> None:
    """Gate write endpoints when AUTH_ENABLED=true.

    Pass the key via HTTP header:  X-Awareness-Key: <your-key>
    """
    if not config.AUTH_ENABLED:
        return
    if not config.AUTH_API_KEY:
        raise HTTPException(status_code=503, detail="Auth enabled but AUTH_API_KEY not set.")
    if x_awareness_key != config.AUTH_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Awareness-Key header.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_sources_used(text: str) -> List[str]:
    """Pull chunk IDs from the '## Sources used' section of the answer."""
    m = re.search(r"## Sources used\n([\s\S]*?)(?:\n##|$)", text)
    if not m:
        return []
    return re.findall(r"`([^`]+)`", m.group(1))


def _record_to_summary(record: ToolCallRecord) -> ToolCallSummary:
    return ToolCallSummary(
        tool_name=record.tool_name,
        success=record.error is None,
        result_summary=record.result_summary,
        error=record.error,
    )


def _make_request_id(client_id: Optional[str]) -> str:
    return client_id or str(uuid.uuid4())[:8]


async def _stream_tokens(
    question: str, mode: str, k: int, use_tools: bool, request_id: str
) -> AsyncIterator[str]:
    index = get_or_build_index()
    chunks = [c for c, _ in index.retrieve(question, k=k)]
    system, user = build_chat_prompt(question, mode, chunks)

    tool_records = []
    if use_tools and has_tool_trigger(question):
        router = get_tool_router()
        router.reset_request()
        for spec in router.list_tools():
            if spec.provider in ("pubmed", "biorxiv"):
                res = router.call_tool(spec.name, {"query": question, "max_results": 3})
                tool_records.append(res)
                if router._calls_this_request >= router._max_calls:
                    break
        suffix = format_tool_results(tool_records)
        if suffix:
            user = user + suffix

    client = get_llm_client()
    full_text = ""
    for token in client.complete_stream(system, user):
        full_text += token
        yield f"data: {json.dumps({'token': token})}\n\n"

    if tool_records:
        summaries = [
            {"tool_name": r.record.tool_name, "success": r.success,
             "result_summary": r.record.result_summary}
            for r in tool_records
        ]
        yield f"data: {json.dumps({'tool_calls': summaries})}\n\n"

    meta = {
        "sources_used": _extract_sources_used(full_text),
        "request_id": request_id,
        "mode": mode,
    }
    yield f"data: {json.dumps({'meta': meta})}\n\n"
    yield "data: [DONE]\n\n"


def _as_evidence_card(item: dict) -> str:
    title = item.get("title", "(no title)")
    authors = item.get("authors", "")
    doi = item.get("doi", "")
    url = item.get("url", "")
    abstract = item.get("abstract", item.get("title", ""))[:300]
    source = item.get("source", "external")
    return (
        f"**Card ID:** {doi or title[:40].lower().replace(' ', '-')}\n"
        f"**Text:** {abstract}\n"
        f"**EBT confidence:** none (external — not EBT)\n"
        f"**Primary quote:** {doi or 'N/A'}\n"
        f"**Claim statement:** [Hypothesis] {title}\n"
        f"**Operationalization:** Requires mapping to gain/latch/loop model\n"
        f"**Telemetry proxy:** TBD\n"
        f"**Discriminator / confounds:** External source ({source}); not peer-reviewed "
        f"for EBT alignment; may conflict with canonical vedanā framing\n"
        f"**Source:** {url or doi}\n"
        f"**Authors:** {authors}"
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def index():
    """Serve the Control Panel UI."""
    html_file = _STATIC_DIR / "index.html"
    if html_file.exists():
        return FileResponse(str(html_file), media_type="text/html")
    return HTMLResponse("<h1>Awareness Studio API</h1><p>UI not built.</p>")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        backend=config.INDEX_BACKEND,
        embedding_provider=(
            config.EMBEDDING_PROVIDER if config.INDEX_BACKEND == "embedding" else None
        ),
        tools_enabled=config.TOOLS_ENABLED,
    )


@app.get("/tools/list")
async def tools_list():
    router = get_tool_router()
    return {
        "enabled": config.TOOLS_ENABLED,
        "allowlist": config.TOOLS_ALLOWLIST,
        "tools": [
            {"name": t.name, "description": t.description,
             "provider": t.provider, "readonly": t.readonly}
            for t in router.list_tools()
        ],
    }


@app.post("/chat")
async def chat(req: ChatRequest):
    mode = req.mode.upper()
    if mode not in _VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid mode '{req.mode}'. Valid: {sorted(_VALID_MODES)}",
        )
    request_id = _make_request_id(req.request_id)

    if req.stream:
        return StreamingResponse(
            _stream_tokens(req.question, mode, req.k, req.use_tools, request_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    index = get_or_build_index()
    chunks = [c for c, _ in index.retrieve(req.question, k=req.k)]
    system, user = build_chat_prompt(req.question, mode, chunks)

    tool_records = []
    if req.use_tools and has_tool_trigger(req.question):
        router = get_tool_router()
        router.reset_request()
        for spec in router.list_tools():
            if spec.provider in ("pubmed", "biorxiv"):
                res = router.call_tool(spec.name, {"query": req.question, "max_results": 3})
                tool_records.append(res)
                if router._calls_this_request >= router._max_calls:
                    break
        suffix = format_tool_results(tool_records)
        if suffix:
            user = user + suffix

    client = get_llm_client()
    answer = client.complete(system, user)

    return ChatResponse(
        answer=answer,
        mode=mode,
        retrieved=len(chunks),
        sources_used=_extract_sources_used(answer),
        tool_calls=[_record_to_summary(r.record) for r in tool_records],
        request_id=request_id,
    )


@app.post("/literature/search", response_model=LiteratureResult)
async def literature_search(req: LiteratureRequest):
    source = req.source.lower()
    if source not in ("pubmed", "biorxiv", "medrxiv"):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid source '{req.source}'. Use: pubmed, biorxiv, medrxiv",
        )
    tool_name = "pubmed_search" if source == "pubmed" else "biorxiv_search"
    args: dict = {"query": req.query, "max_results": req.max_results}
    if source != "pubmed":
        args["server"] = source

    from awareness_studio.tool_router import LiteratureToolRouter
    lit_router = LiteratureToolRouter()
    result = lit_router.call_tool(tool_name, args)

    items = result.data or []
    if req.as_card and items:
        items = [{"card_draft": _as_evidence_card(item), **item} for item in items]

    return LiteratureResult(
        source=source,
        items=items,
        tool_record={
            "tool_name": result.record.tool_name,
            "success": result.success,
            "result_summary": result.record.result_summary,
            "duration_ms": result.record.duration_ms,
            "error": result.record.error,
        },
    )


@app.get("/linear/search")
async def linear_search(
    query: str = Query(default="", description="Search term for issue title"),
    limit: int = Query(default=10, ge=1, le=50),
):
    if not config.LINEAR_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="LINEAR_API_KEY not configured. Set it in .env to enable this endpoint.",
        )
    from awareness_studio.tool_router import LinearToolRouter
    router = LinearToolRouter()
    result = router.call_tool("linear_list_issues", {"query": query, "limit": limit})
    if not result.success:
        raise HTTPException(status_code=502, detail=result.record.error)
    return {"issues": result.data, "count": len(result.data), "query": query}


# ── Airtable routes ────────────────────────────────────────────────────────────

@app.get("/airtable/status")
async def airtable_status_route():
    from awareness_studio.integrations.airtable_sync import airtable_status
    return airtable_status()


@app.post("/airtable/sync/runs")
async def airtable_sync_runs(
    allow_write: bool = Query(default=False),
    run_cards_dir: Optional[str] = Query(default=None),
    _auth: None = Depends(_require_auth),
):
    from pathlib import Path
    from awareness_studio.integrations.airtable_sync import sync_runs_from_run_cards
    rcd = Path(run_cards_dir) if run_cards_dir else None
    summary = sync_runs_from_run_cards(run_cards_dir=rcd, allow_write=allow_write)
    return summary.to_dict()


# ── Orchestrator routes ────────────────────────────────────────────────────────

_orch_lock = threading.Lock()
_active_run_id: Optional[str] = None
_SAFE_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


def _find_orchestrator_run_dir(run_id: str) -> Optional[Path]:
    if not _SAFE_PATH_SEGMENT.fullmatch(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id format.")
    orch_base = config.APP_ROOT / "outputs" / "orchestrator"
    if not orch_base.exists():
        return None
    for run_dir in orch_base.iterdir():
        if run_dir.is_dir() and run_dir.name == run_id:
            return run_dir
    return None


def _resolve_orchestrator_artifact_path(run_dir: Path, filename: str) -> Path:
    if not _SAFE_PATH_SEGMENT.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Invalid filename format.")
    for fpath in run_dir.iterdir():
        if fpath.is_file() and fpath.name == filename:
            return fpath
    raise HTTPException(status_code=404, detail=f"{filename} not found in run {run_dir.name}.")


@app.post("/cmd/orchestrate", dependencies=[Depends(_require_auth)])
async def cmd_orchestrate(dry_run: bool = Query(default=True)):
    """Start an orchestrator run. Only one run allowed at a time."""
    global _active_run_id
    if not _orch_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="An orchestrator run is already in progress.")
    try:
        from awareness_studio.orchestrator.orchestrator import Orchestrator, OrchestratorConfig
        cfg = OrchestratorConfig(dry_run=dry_run)
        result = Orchestrator().run(config=cfg)
        _active_run_id = result.run_id
        return result.to_dict()
    finally:
        _orch_lock.release()


@app.get("/cmd/runs/recent")
async def cmd_runs_recent(limit: int = Query(default=10, ge=1, le=50)):
    """List recent orchestrator run directories."""
    orch_base = config.APP_ROOT / "outputs" / "orchestrator"
    if not orch_base.exists():
        return {"runs": []}
    run_dirs = sorted(orch_base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    runs = []
    for d in run_dirs[:limit]:
        if d.is_dir():
            artifacts = [f.name for f in d.iterdir() if f.is_file()]
            runs.append({"run_id": d.name, "artifacts": artifacts})
    return {"runs": runs}


@app.get("/cmd/runs/{run_id}/artifacts")
async def cmd_run_artifacts(run_id: str):
    """List artifacts for a specific orchestrator run."""
    orch_dir = _find_orchestrator_run_dir(run_id)
    if orch_dir is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
    files = {f.name: str(f) for f in orch_dir.iterdir() if f.is_file()}
    return {"run_id": run_id, "artifacts": files}


@app.get("/cmd/runs/{run_id}/file/{filename}")
async def cmd_run_file(run_id: str, filename: str):
    """Serve a text artifact from an orchestrator run."""
    orch_dir = _find_orchestrator_run_dir(run_id)
    if orch_dir is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
    fpath = _resolve_orchestrator_artifact_path(orch_dir, filename)
    text = fpath.read_text(encoding="utf-8")
    return {"run_id": run_id, "filename": filename, "content": text}


@app.get("/cmd/orchestrate/stream")
async def cmd_orchestrate_stream(run_id: str = Query(...)):
    """Stream orchestrator event log as SSE for a given run_id."""
    from awareness_studio.orchestrator.event_model import EventEnvelope
    orch_dir = _find_orchestrator_run_dir(run_id)

    async def _generate():
        if orch_dir is not None:
            events_path = _resolve_orchestrator_artifact_path(orch_dir, "events.jsonl")
            with events_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = EventEnvelope.from_dict(json.loads(line))
                    except Exception:
                        continue
                    yield f"data: {ev.to_jsonl()}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    import os
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("awareness_studio.web.app:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
