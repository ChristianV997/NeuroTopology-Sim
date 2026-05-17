from __future__ import annotations
import argparse
from pathlib import Path

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--out',required=True); a=ap.parse_args(argv)
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    text='''# Public Language Rewrite Guide

## 1. Safe public language
Use model, candidate, proxy, and hypothesis terms.
## 2. Unsafe language
Avoid proof, metaphysical certainty, therapeutic guarantees.
## 3. Research-safe replacements
## 4. Book-safe replacements
## 5. Speculative quarantine replacements
## 6. Clinical/therapeutic caution replacements
## 7. Q/Qabs/fdress language rules
Treat as candidate telemetry only.
## 8. Ontology language rules
Ontology-candidate language remains quarantined.

Unsafe: “soul is real”
Safe: “some ToL drafts contain ontology-candidate language about selfhood; this remains quarantined.”

Unsafe: “Qabs proves liberation”
Safe: “Qabs/fdress may be tested as candidate fragmentation telemetry under controls.”

Unsafe: “trauma deletion”
Safe: “reduced affective reactivation is a possible therapeutic metaphor; clinical claims require safety validation.”

Unsafe: “theory validated”
Safe: “the current framework is hypothesis-generating and requires real-data tests.”

Unsafe: “instant arhat state”
Safe: “advanced liberation claims remain doctrinal/speculative and are not operational claims.”
'''
    out.write_text(text,encoding='utf-8')
    return 0
if __name__=='__main__': raise SystemExit(main())
