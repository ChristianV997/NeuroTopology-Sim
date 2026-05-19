from __future__ import annotations
from pathlib import Path

SPEC_KWS = ["uttl", "ontology", "soul", "afterlife", "vacuum_hygiene", "vacuum hygiene"]


def classify(path: Path) -> tuple[str,str,str]:
    p = str(path).lower()
    ext = path.suffix.lower()
    if any(k in p for k in SPEC_KWS): return ("ontology", "speculative_ontology", "ontology_quarantined")
    if any(k in p for k in ["governance", "claim", "validator", "falsifier"]): return ("governance", "governance", "publication_safe")
    if any(k in p for k in ["book", "publisher", "writer", "contract_template"]): return ("book_system", "book_system", "engineering_runtime")
    if any(k in p for k in ["runtime", "agent", "devops", "orchestration", "docker", "k8s"]): return ("runtime_archive", "os_runtime", "engineering_runtime")
    if ext in {".pdf", ".tex"} or (ext == ".md" and "manuscript" in p): return ("manuscript" if ext != ".pdf" else "pdf", "manuscripts", "publication_safe")
    if ext == ".zip": return ("zip", "simulator_assets", "engineering_runtime")
    if any(k in p for k in ["sim", "simulator", "config", "script"]): return ("code_repo_archive", "simulator_assets", "engineering_runtime")
    return ("code_repo_archive", "simulator_assets", "requires_validation")
