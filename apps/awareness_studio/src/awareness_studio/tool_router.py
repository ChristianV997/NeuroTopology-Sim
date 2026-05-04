"""
Tool router for Awareness Studio — gated, optional, logged.

Environment controls:
  TOOLS_ENABLED=true|false             (default false — tools are OFF)
  TOOLS_ALLOWLIST=pubmed_search,...    (comma-separated; empty = deny all)
  TOOLS_MAX_CALLS_PER_REQUEST=1        (default 1 per request)

Concrete routers available in Python runtime:
  NullToolRouter      — no-op default; all calls return disabled status
  LiteratureToolRouter— pubmed_search + biorxiv_search via stdlib urllib
  LinearToolRouter    — linear_list_issues via Linear GraphQL API (needs LINEAR_API_KEY)
  GatedToolRouter     — wraps any router; enforces allowlist + per-request cap

Factory: get_tool_router() returns a GatedToolRouter wrapping a CompositeToolRouter
of all enabled concrete routers.

NOTE: MCP connectors (Notion, Supabase, Netlify, Google Drive) are accessible to
Claude during an active session but NOT from this Python subprocess. Use them
directly via Claude's session tooling; the Python router only covers public/keyed
HTTP APIs.
"""
import json
import logging
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from awareness_studio import config

logger = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ToolSpec:
    name: str
    description: str
    provider: str
    readonly: bool = True
    requires_auth: bool = False


@dataclass
class ToolCallRecord:
    tool_name: str
    args: Dict[str, Any]
    timestamp: str
    result_summary: str
    error: Optional[str] = None
    duration_ms: Optional[float] = None


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    data: Any
    record: ToolCallRecord


# ── Exceptions ────────────────────────────────────────────────────────────────

class ToolNotAllowedError(ValueError):
    pass


class ToolNotFoundError(KeyError):
    pass


# ── Abstract base ─────────────────────────────────────────────────────────────

class ToolRouter(ABC):
    @abstractmethod
    def list_tools(self) -> List[ToolSpec]:
        """Return specs for all tools this router can handle."""

    @abstractmethod
    def call_tool(self, name: str, args: dict) -> ToolResult:
        """Execute a tool and return a logged result."""

    def handles(self, name: str) -> bool:
        return any(t.name == name for t in self.list_tools())


# ── NullToolRouter ────────────────────────────────────────────────────────────

class NullToolRouter(ToolRouter):
    """Default no-op router. Tools are always disabled."""

    def list_tools(self) -> List[ToolSpec]:
        return []

    def call_tool(self, name: str, args: dict) -> ToolResult:
        ts = _now()
        record = ToolCallRecord(
            tool_name=name,
            args=args,
            timestamp=ts,
            result_summary="tools disabled",
            error="NullToolRouter: TOOLS_ENABLED=false or no router configured",
        )
        return ToolResult(tool_name=name, success=False, data=None, record=record)


# ── LiteratureToolRouter ──────────────────────────────────────────────────────

class LiteratureToolRouter(ToolRouter):
    """
    Searches PubMed E-utilities and bioRxiv.

    Tools provided:
      pubmed_search  — args: query (str), max_results (int, default 5)
      biorxiv_search — args: query (str), server ("biorxiv"|"medrxiv"), max_results (int)

    Both use stdlib urllib; no API key required for basic queries.
    PUBMED_API_KEY improves rate limits when set.
    """

    _TOOLS = [
        ToolSpec(
            name="pubmed_search",
            description="Search PubMed for peer-reviewed biomedical literature",
            provider="pubmed",
            readonly=True,
            requires_auth=False,
        ),
        ToolSpec(
            name="biorxiv_search",
            description="Search bioRxiv/medRxiv preprint servers",
            provider="biorxiv",
            readonly=True,
            requires_auth=False,
        ),
    ]

    def list_tools(self) -> List[ToolSpec]:
        return list(self._TOOLS)

    def call_tool(self, name: str, args: dict) -> ToolResult:
        t0 = time.monotonic()
        ts = _now()
        try:
            if name == "pubmed_search":
                data = self._pubmed_search(
                    args.get("query", ""),
                    max_results=int(args.get("max_results", 5)),
                )
            elif name == "biorxiv_search":
                data = self._biorxiv_search(
                    args.get("query", ""),
                    server=args.get("server", "biorxiv"),
                    max_results=int(args.get("max_results", 5)),
                )
            else:
                raise ToolNotFoundError(name)

            duration = (time.monotonic() - t0) * 1000
            summary = f"returned {len(data)} results"
            record = ToolCallRecord(
                tool_name=name, args=args, timestamp=ts,
                result_summary=summary, duration_ms=round(duration, 1),
            )
            logger.info("[tool] %s → %s (%.0fms)", name, summary, duration)
            return ToolResult(tool_name=name, success=True, data=data, record=record)

        except Exception as exc:
            duration = (time.monotonic() - t0) * 1000
            msg = str(exc)
            record = ToolCallRecord(
                tool_name=name, args=args, timestamp=ts,
                result_summary="error", error=msg, duration_ms=round(duration, 1),
            )
            logger.warning("[tool] %s failed: %s", name, msg)
            return ToolResult(tool_name=name, success=False, data=[], record=record)

    # ── PubMed ────────────────────────────────────────────────────────────────

    def _pubmed_search(self, query: str, max_results: int = 5) -> List[dict]:
        if not query.strip():
            return []
        api_key = config.PUBMED_API_KEY
        base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

        # Step 1: esearch — get PMIDs
        params: dict = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "usehistory": "n",
        }
        if api_key:
            params["api_key"] = api_key

        search_url = f"{base}/esearch.fcgi?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(search_url, timeout=10) as resp:
            search_data = json.loads(resp.read())

        ids = search_data.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        # Step 2: esummary — get article metadata
        sum_params: dict = {
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "json",
        }
        if api_key:
            sum_params["api_key"] = api_key

        sum_url = f"{base}/esummary.fcgi?{urllib.parse.urlencode(sum_params)}"
        with urllib.request.urlopen(sum_url, timeout=10) as resp:
            sum_data = json.loads(resp.read())

        results = []
        for pmid in ids:
            doc = sum_data.get("result", {}).get(pmid, {})
            if not doc:
                continue
            authors = [a.get("name", "") for a in doc.get("authors", [])[:3]]
            if len(doc.get("authors", [])) > 3:
                authors.append("et al.")
            results.append({
                "pmid": pmid,
                "title": doc.get("title", ""),
                "authors": ", ".join(authors),
                "journal": doc.get("fulljournalname", doc.get("source", "")),
                "pubdate": doc.get("pubdate", ""),
                "doi": next(
                    (a.get("value", "") for a in doc.get("articleids", []) if a.get("idtype") == "doi"),
                    "",
                ),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "source": "pubmed",
            })
        return results

    # ── bioRxiv ───────────────────────────────────────────────────────────────

    def _biorxiv_search(
        self, query: str, server: str = "biorxiv", max_results: int = 5
    ) -> List[dict]:
        if not query.strip():
            return []
        if server not in ("biorxiv", "medrxiv"):
            server = "biorxiv"

        # bioRxiv details API — recent preprints containing query terms
        # Public endpoint; no auth needed. 30-day interval.
        encoded = urllib.parse.quote(query)
        url = f"https://api.biorxiv.org/details/{server}/2024-01-01/2026-12-31/0/json"
        try:
            with urllib.request.urlopen(url, timeout=12) as resp:
                raw = json.loads(resp.read())
        except Exception:
            return []

        papers = raw.get("collection", [])
        q_terms = set(query.lower().split())
        scored = []
        for p in papers:
            text = (p.get("title", "") + " " + p.get("abstract", "")).lower()
            score = sum(1 for t in q_terms if t in text)
            if score > 0:
                scored.append((score, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for _, p in scored[:max_results]:
            results.append({
                "doi": p.get("doi", ""),
                "title": p.get("title", ""),
                "authors": p.get("authors", ""),
                "date": p.get("date", ""),
                "abstract": p.get("abstract", "")[:400],
                "url": f"https://www.{server}.org/content/{p.get('doi', '')}",
                "source": server,
            })
        return results


# ── LinearToolRouter ──────────────────────────────────────────────────────────

class LinearToolRouter(ToolRouter):
    """
    Read-only Linear integration via GraphQL API.

    Requires: LINEAR_API_KEY in environment.
    Tool: linear_list_issues — args: query (str), limit (int, default 10)
    """

    _TOOLS = [
        ToolSpec(
            name="linear_list_issues",
            description="List Linear issues matching a search query (read-only)",
            provider="linear",
            readonly=True,
            requires_auth=True,
        ),
    ]

    _GQL_URL = "https://api.linear.app/graphql"

    def list_tools(self) -> List[ToolSpec]:
        if not config.LINEAR_API_KEY:
            return []
        return list(self._TOOLS)

    def call_tool(self, name: str, args: dict) -> ToolResult:
        t0 = time.monotonic()
        ts = _now()
        if name != "linear_list_issues":
            raise ToolNotFoundError(name)
        if not config.LINEAR_API_KEY:
            record = ToolCallRecord(
                tool_name=name, args=args, timestamp=ts,
                result_summary="no key", error="LINEAR_API_KEY not set",
            )
            return ToolResult(tool_name=name, success=False, data=[], record=record)

        try:
            data = self._list_issues(
                args.get("query", ""),
                limit=int(args.get("limit", 10)),
            )
            duration = (time.monotonic() - t0) * 1000
            summary = f"returned {len(data)} issues"
            record = ToolCallRecord(
                tool_name=name, args=args, timestamp=ts,
                result_summary=summary, duration_ms=round(duration, 1),
            )
            return ToolResult(tool_name=name, success=True, data=data, record=record)
        except Exception as exc:
            duration = (time.monotonic() - t0) * 1000
            record = ToolCallRecord(
                tool_name=name, args=args, timestamp=ts,
                result_summary="error", error=str(exc),
                duration_ms=round(duration, 1),
            )
            return ToolResult(tool_name=name, success=False, data=[], record=record)

    def _list_issues(self, query: str, limit: int = 10) -> List[dict]:
        gql = """
        query SearchIssues($filter: IssueFilter, $first: Int) {
          issues(filter: $filter, first: $first, orderBy: updatedAt) {
            nodes {
              id
              identifier
              title
              state { name }
              priority
              assignee { name }
              url
              updatedAt
            }
          }
        }
        """
        variables: dict = {"first": limit}
        if query.strip():
            variables["filter"] = {"title": {"containsIgnoreCase": query}}

        payload = json.dumps({"query": gql, "variables": variables}).encode()
        req = urllib.request.Request(
            self._GQL_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": config.LINEAR_API_KEY,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())

        nodes = result.get("data", {}).get("issues", {}).get("nodes", [])
        return [
            {
                "id": n["identifier"],
                "title": n["title"],
                "state": n.get("state", {}).get("name", ""),
                "priority": n.get("priority", 0),
                "assignee": (n.get("assignee") or {}).get("name", ""),
                "url": n.get("url", ""),
                "updated": n.get("updatedAt", ""),
            }
            for n in nodes
        ]


# ── CompositeToolRouter ───────────────────────────────────────────────────────

class CompositeToolRouter(ToolRouter):
    """Delegates to the first child router that advertises the requested tool."""

    def __init__(self, routers: List[ToolRouter]) -> None:
        self._routers = routers

    def list_tools(self) -> List[ToolSpec]:
        seen: set = set()
        out = []
        for r in self._routers:
            for spec in r.list_tools():
                if spec.name not in seen:
                    seen.add(spec.name)
                    out.append(spec)
        return out

    def call_tool(self, name: str, args: dict) -> ToolResult:
        for r in self._routers:
            if r.handles(name):
                return r.call_tool(name, args)
        raise ToolNotFoundError(f"No router handles tool '{name}'")


# ── GatedToolRouter ───────────────────────────────────────────────────────────

class GatedToolRouter(ToolRouter):
    """
    Wraps any ToolRouter; enforces:
      - TOOLS_ENABLED gate (returns NullToolRouter behavior when false)
      - TOOLS_ALLOWLIST (rejects unlisted tools)
      - TOOLS_MAX_CALLS_PER_REQUEST per-request cap

    Call reset_request() at the start of each request.
    """

    def __init__(
        self,
        inner: ToolRouter,
        allowlist: List[str],
        max_calls: int,
        enabled: bool,
    ) -> None:
        self._inner = inner
        self._allowlist = set(allowlist)
        self._max_calls = max_calls
        self._enabled = enabled
        self._calls_this_request: int = 0

    def reset_request(self) -> None:
        self._calls_this_request = 0

    def list_tools(self) -> List[ToolSpec]:
        if not self._enabled:
            return []
        return [t for t in self._inner.list_tools() if t.name in self._allowlist]

    def call_tool(self, name: str, args: dict) -> ToolResult:
        ts = _now()
        if not self._enabled:
            record = ToolCallRecord(
                tool_name=name, args=args, timestamp=ts,
                result_summary="disabled", error="TOOLS_ENABLED=false",
            )
            return ToolResult(tool_name=name, success=False, data=None, record=record)

        if self._allowlist and name not in self._allowlist:
            raise ToolNotAllowedError(
                f"Tool '{name}' is not in TOOLS_ALLOWLIST. "
                f"Allowed: {sorted(self._allowlist)}"
            )

        if self._calls_this_request >= self._max_calls:
            raise ToolNotAllowedError(
                f"Per-request tool cap ({self._max_calls}) exceeded"
            )

        self._calls_this_request += 1
        return self._inner.call_tool(name, args)


# ── Factory ───────────────────────────────────────────────────────────────────

def get_tool_router() -> GatedToolRouter:
    """
    Build and return the configured tool router.

    Concrete routers included:
      - LiteratureToolRouter (always, no key needed)
      - LinearToolRouter     (only when LINEAR_API_KEY is set)
    """
    routers: List[ToolRouter] = [LiteratureToolRouter()]
    if config.LINEAR_API_KEY:
        routers.append(LinearToolRouter())

    inner = CompositeToolRouter(routers)
    return GatedToolRouter(
        inner=inner,
        allowlist=config.TOOLS_ALLOWLIST,
        max_calls=config.TOOLS_MAX_CALLS_PER_REQUEST,
        enabled=config.TOOLS_ENABLED,
    )


# ── Formatting helpers (for chat synthesis) ───────────────────────────────────

_TRIGGER_KEYWORDS: frozenset = frozenset({
    "pubmed", "biorxiv", "paper", "papers", "study", "studies",
    "citation", "citations", "rct", "meta-analysis", "meta analysis",
    "clinical trial", "clinical trials", "systematic review",
    "preprint", "journal", "research evidence", "find evidence",
    "peer-reviewed", "peer reviewed",
})


def has_tool_trigger(question: str) -> bool:
    """Return True if question contains literature-lookup trigger keywords."""
    q = question.lower()
    return any(kw in q for kw in _TRIGGER_KEYWORDS)


def format_tool_results(results: List[ToolResult]) -> str:
    """
    Format tool call outputs as an 'External tool results' section.
    All claims from this section must be treated as [Hypothesis] / external evidence.
    """
    if not results:
        return ""

    lines = [
        "\n\n---",
        "## External tool results (non-canonical)",
        "_Claims from external tools are [Hypothesis] / external evidence._",
        "_Always verify against primary sources before treating as established fact._",
        "",
    ]
    for res in results:
        lines.append(f"### Tool: `{res.tool_name}` — {res.record.result_summary}")
        if not res.success:
            lines.append(f"_Error: {res.record.error}_")
            continue
        if not res.data:
            lines.append("_No results returned._")
            continue
        for item in res.data[:5]:
            title = item.get("title", "(no title)")
            url = item.get("url", "")
            authors = item.get("authors", "")
            date = item.get("pubdate", item.get("date", ""))
            doi = item.get("doi", "")
            lines.append(f"- **{title}**")
            if authors:
                lines.append(f"  {authors} ({date})")
            if doi:
                lines.append(f"  DOI: {doi}")
            if url:
                lines.append(f"  {url}")
    return "\n".join(lines)


# ── Internal ──────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
