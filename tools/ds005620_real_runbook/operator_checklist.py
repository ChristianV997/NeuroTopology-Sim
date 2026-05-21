from __future__ import annotations

def build_operator_checklist() -> str:
    sections = {
        "Local File Placement": ["Place DS005620 data under one approved local root.", "Confirm events.tsv and raw EEG files are present.", "Do not download or alter real data from this tooling."],
        "Contract Review": ["Complete human-reviewed contract audit with a peer.", "Record reviewer names and timestamp in reviewed contract artifact."],
        "Preflight": ["Run gate and readiness validators in dry/manual mode only.", "Confirm no auto-execution flags are enabled."],
        "Artifact Building": ["Build P18.3/P20/P21 readiness artifacts from local outputs.", "Verify output checksums/manifests are generated."],
        "Human Peer Review": ["Independent peer reviews command and readiness report.", "Peer verifies no label inference or target fabrication claims."],
        "Manual Real Execution": ["Human operator executes approved command manually.", "Tooling must not run --execute or peer-reviewed confirmation flags."],
        "Post-Run Controls": ["Collect expected artifacts and control reports.", "Run ontology/language governance checks before publication packaging."],
    }
    lines = ["# DS005620 Real Execution Operator Checklist", ""]
    for title, items in sections.items():
        lines.append(f"## {title}")
        lines += [f"- [ ] {x}" for x in items]
        lines.append("")
    return "\n".join(lines).strip() + "\n"
