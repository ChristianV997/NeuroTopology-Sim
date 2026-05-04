"""
FastAPI web frontend for Awareness Studio.

Endpoints:
  GET  /health               — liveness probe
  POST /chat                 — RAG query (JSON or SSE stream)
  POST /literature/search    — PubMed / bioRxiv search
  GET  /linear/search        — Linear issues search (requires LINEAR_API_KEY)
  GET  /tools/list           — list enabled tools

Run:
  uvicorn awareness_studio.web.app:app --reload --port 8000
"""
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from awareness_studio import config
from awareness_studio.answer_modes import build_chat_prompt
from awareness_studio.index_build import get_or_build_index
from awareness_studio.llm_client import get_llm_client
from awareness_studio.tool_router import (
    ToolCallRecord,
    format_tool_results,
    get_tool_router,
    has_tool_trigger,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Awareness Studio",
    description="Monk+Scientist RAG chatbot for the Awareness Research knowledge base.",
    version="0.3.0",
)

_VALID_MODES = {"TEACH", "EXPLAIN", "ELABORATE", "MATRIX", "CARD", "CANONICAL"}


# ── Request / response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    mode: str = Field("EXPLAIN", description="One of: TEACH EXPLAIN ELABORATE MATRIX CARD CANONICAL")
    k: int = Field(config.DEFAULT_TOP_K, ge=1, le=20)
    stream: bool = Field(False, description="Return SSE token stream instead of JSON")
    use_tools: bool = Field(False, description="Enable external tool lookup for this query")


class ToolCallSummary(BaseModel):
    tool_name: str
    success: bool
    result_summary: str
    error: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    mode: str
    retrieved: int
    tool_calls: List[ToolCallSummary] = Field(default_factory=list)


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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _record_to_summary(record: ToolCallRecord) -> ToolCallSummary:
    return ToolCallSummary(
        tool_name=record.tool_name,
        success=record.error is None,
        result_summary=record.result_summary,
        error=record.error,
    )


async def _stream_tokens(
    question: str, mode: str, k: int, use_tools: bool
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
    for token in client.complete_stream(system, user):
        yield f"data: {json.dumps({'token': token})}\n\n"

    if tool_records:
        summaries = [_record_to_summary(r.record).__dict__ for r in tool_records]
        yield f"data: {json.dumps({'tool_calls': summaries})}\n\n"

    yield "data: [DONE]\n\n"


def _as_evidence_card(item: dict) -> str:
    """Format a literature result as an Evidence Card draft."""
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
    """Return the list of tools currently available via the configured router."""
    router = get_tool_router()
    return {
        "enabled": config.TOOLS_ENABLED,
        "allowlist": config.TOOLS_ALLOWLIST,
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "provider": t.provider,
                "readonly": t.readonly,
            }
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

    if req.stream:
        return StreamingResponse(
            _stream_tokens(req.question, mode, req.k, req.use_tools),
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
        tool_calls=[_record_to_summary(r.record) for r in tool_records],
    )


@app.post("/literature/search", response_model=LiteratureResult)
async def literature_search(req: LiteratureRequest):
    """Search PubMed or bioRxiv and return structured results (or Evidence Card drafts)."""
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

    router = get_tool_router()
    router.reset_request()

    # Literature search is always allowed on this endpoint regardless of TOOLS_ENABLED
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
    """Search Linear issues (read-only). Requires LINEAR_API_KEY env var."""
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
    return {
        "issues": result.data,
        "count": len(result.data),
        "query": query,
    }


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    import uvicorn
    uvicorn.run("awareness_studio.web.app:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
