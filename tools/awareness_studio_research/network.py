"""Explicit opt-in network access gate.

Nothing in this package calls the network by default. Every function
here requires ``allow_network=True`` to do anything beyond raising --
the default test suite (and the default CLI invocation) never passes
that flag, so ingestion is offline-first end to end. This module never
scrapes arbitrary sites: it only ever targets the two well-known,
narrow metadata APIs (arXiv's export API, a DOI resolver) and only
when explicitly invoked by an operator.
"""
from __future__ import annotations

from typing import Optional


class NetworkDisabledError(RuntimeError):
    """Raised whenever a network fetch is attempted without explicit
    operator opt-in."""


def fetch_arxiv_metadata(arxiv_id: str, *, allow_network: bool = False) -> dict:
    if not allow_network:
        raise NetworkDisabledError(
            f"fetch_arxiv_metadata({arxiv_id!r}) requires allow_network=True; "
            "this package never makes a hidden network call"
        )
    import urllib.request
    import xml.etree.ElementTree as ET

    url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    with urllib.request.urlopen(url, timeout=15) as response:
        raw = response.read()
    root = ET.fromstring(raw)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    if entry is None:
        return {"exists": False, "arxiv_id": arxiv_id}
    title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
    return {"exists": True, "arxiv_id": arxiv_id, "title": title}


def fetch_doi_metadata(doi: str, *, allow_network: bool = False) -> dict:
    if not allow_network:
        raise NetworkDisabledError(
            f"fetch_doi_metadata({doi!r}) requires allow_network=True; "
            "this package never makes a hidden network call"
        )
    import json
    import urllib.request

    url = f"https://api.crossref.org/works/{doi}"
    with urllib.request.urlopen(url, timeout=15) as response:
        payload = json.loads(response.read())
    message = payload.get("message", {})
    title_list = message.get("title") or []
    return {
        "exists": True,
        "doi": doi,
        "title": title_list[0] if title_list else None,
    }
