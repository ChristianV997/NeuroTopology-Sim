"""
FastAPI web frontend for Awareness Studio (TASK-5).

Endpoints:
  GET  /health  — liveness probe
  POST /chat    — RAG query with optional SSE token streaming

Run:
  uvicorn awareness_studio.web.app:app --reload --port 8000

Stream example:
  curl -N -X POST http://localhost:8000/chat \
       -H "Content-Type: application/json" \
       -d '{"question": "What is vedana?", "mode": "EXPLAIN", "stream": true}'

Non-stream example:
  curl -X POST http://localhost:8000/chat \
       -H "Content-Type: application/json" \
       -d '{"question": "What is tanha?", "mode": "TEACH"}'
"""
import json
import logging
from typing import AsyncIterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from awareness_studio import config
from awareness_studio.answer_modes import build_chat_prompt
from awareness_studio.index_build import get_or_build_index
from awareness_studio.llm_client import get_llm_client

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Awareness Studio",
    description="Monk+Scientist RAG chatbot for the Awareness Research knowledge base.",
    version="0.2.0",
)

_VALID_MODES = {"TEACH", "EXPLAIN", "ELABORATE", "MATRIX", "CARD", "CANONICAL"}


# ── Request / response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    mode: str = Field("EXPLAIN", description="One of: TEACH EXPLAIN ELABORATE MATRIX CARD CANONICAL")
    k: int = Field(config.DEFAULT_TOP_K, ge=1, le=20)
    stream: bool = Field(False, description="Return SSE token stream instead of JSON")


class ChatResponse(BaseModel):
    answer: str
    mode: str
    retrieved: int


class HealthResponse(BaseModel):
    status: str
    backend: str
    embedding_provider: Optional[str]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _stream_tokens(question: str, mode: str, k: int) -> AsyncIterator[str]:
    index = get_or_build_index()
    chunks = [c for c, _ in index.retrieve(question, k=k)]
    system, user = build_chat_prompt(question, mode, chunks)
    client = get_llm_client()
    for token in client.complete_stream(system, user):
        yield f"data: {json.dumps({'token': token})}\n\n"
    yield "data: [DONE]\n\n"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        backend=config.INDEX_BACKEND,
        embedding_provider=(
            config.EMBEDDING_PROVIDER if config.INDEX_BACKEND == "embedding" else None
        ),
    )


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
            _stream_tokens(req.question, mode, req.k),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    index = get_or_build_index()
    chunks = [c for c, _ in index.retrieve(req.question, k=req.k)]
    system, user = build_chat_prompt(req.question, mode, chunks)
    client = get_llm_client()
    answer = client.complete(system, user)
    return ChatResponse(answer=answer, mode=mode, retrieved=len(chunks))


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    import uvicorn
    uvicorn.run("awareness_studio.web.app:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
