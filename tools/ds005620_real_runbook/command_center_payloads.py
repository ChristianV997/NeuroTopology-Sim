from __future__ import annotations
import argparse
from pathlib import Path
from . import read_json, write_json

def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument('--root', default='outputs/btc_icft/ds005620_real_runbook'); ap.add_argument('--out', default='outputs/command_center/mock_payloads'); a=ap.parse_args()
    root=Path(a.root); out=Path(a.out); out.mkdir(parents=True, exist_ok=True)
    report = read_json(root / 'readiness_report.json') if (root / 'readiness_report.json').exists() else {}
    write_json(out / 'ds005620_real_runbook_status.json', {
        'dataset_id':'DS005620','ready_for_manual_real_run':report.get('ready_for_manual_real_run', False),'blocked_by':report.get('blocked_by', []),
        'ontology_promotion_allowed':False,'real_data_auto_execution_allowed':False,'claim_proof_allowed':False
    })

if __name__ == '__main__':
    main()
