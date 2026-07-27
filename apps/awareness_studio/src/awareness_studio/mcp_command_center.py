"""ChatGPT Apps MCP server for the empirical NeuroTopology Command Centre."""
from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from awareness_studio.integrations.neurotopology_results import (
    build_command_center_registry,
    build_real_results,
    build_visualization_payload,
)

WIDGET_URI = "ui://neurotopology/command-center-v1.html"
_WIDGET = Path(__file__).parent / "web" / "static" / "chatgpt_command_center.html"
_READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

mcp = FastMCP(
    "NeuroTopology Command Centre",
    instructions=(
        "Use this server for read-only empirical NeuroTopology artifacts. "
        "Treat q_net and f_dress as labeled proxies, never as clinical proof. "
        "Dataset search returns candidates to verify and never starts downloads or analysis."
    ),
    host=os.getenv("NEUROTOPOLOGY_MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("NEUROTOPOLOGY_MCP_PORT", "8022")),
)


@mcp.resource(
    WIDGET_URI,
    name="NeuroTopology Command Centre",
    title="NeuroTopology Command Centre",
    description="Interactive empirical result dashboard.",
    mime_type="text/html;profile=mcp-app",
    meta={
        "ui": {
            "prefersBorder": False,
            "csp": {"connectDomains": [], "resourceDomains": ["https://cdn.plot.ly"]},
        },
        "openai/widgetDescription": "Empirical NeuroTopology status, state summaries, and phase-space plot.",
    },
)
def command_center_widget() -> str:
    return _WIDGET.read_text(encoding="utf-8")


@mcp.tool(
    name="get_command_center",
    title="Show NeuroTopology Command Centre",
    description="Use this when the user asks for the current empirical NeuroTopology run, state summaries, or an interactive dashboard.",
    annotations=_READ_ONLY,
    meta={"ui": {"resourceUri": WIDGET_URI}, "openai/outputTemplate": WIDGET_URI},
)
def get_command_center() -> dict:
    results = build_real_results()
    registry = build_command_center_registry()
    return {
        "dataset": results["dataset"],
        "status": results["status"],
        "evidence_state": results["evidence_state"],
        "state_order": results["state_order"],
        "state_summaries": results["state_summaries"],
        "subject_summaries": results["subject_summaries"],
        "data_quality": results["data_quality"],
        "spatial_artifact": results["spatial_artifact"],
        "source_artifacts": results["source_artifacts"],
        "guardrails": registry["guardrails"],
        "command_registry": registry["command_registry"],
    }


@mcp.tool(name="get_visualization_payload", title="Get visualization payload", description="Use this when the user asks for playback frames or phase-space data for the NeuroTopology viewer.", annotations=_READ_ONLY)
def get_visualization_payload() -> dict:
    return build_visualization_payload()


@mcp.tool(name="search", title="Search empirical artifacts", description="Use this when the user asks to find available empirical datasets, reports, or result artifacts.", annotations=_READ_ONLY, structured_output=False)
def search(query: str) -> str:
    query_l = query.lower()
    results = build_real_results()
    candidates = [
        {"id": "ds005620", "title": "ds005620 Propofol empirical run", "url": results["results_root"]},
        *[{"id": f"report-{index}", "title": Path(path).name, "url": path} for index, path in enumerate(results["reports"])],
    ]
    matched = [item for item in candidates if query_l in item["title"].lower() or query_l in item["id"]]
    return json.dumps({"results": matched or candidates[:1]})


@mcp.tool(name="fetch", title="Fetch empirical artifact summary", description="Use this when the user asks to retrieve a known empirical dataset or report summary.", annotations=_READ_ONLY, structured_output=False)
def fetch(id: str) -> str:
    results = build_real_results()
    if id == "ds005620":
        return json.dumps({"id": id, "title": "ds005620 Propofol empirical run", "text": json.dumps(results["state_summaries"], indent=2), "url": results["results_root"], "metadata": {"evidence_state": results["evidence_state"]}})
    for index, report in enumerate(results["reports"]):
        if id == f"report-{index}":
            return json.dumps({"id": id, "title": Path(report).name, "text": Path(report).read_text(encoding="utf-8")[:12000], "url": report})
    return json.dumps({"id": id, "title": "Not found", "text": "No empirical artifact matches this id.", "url": ""})


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
