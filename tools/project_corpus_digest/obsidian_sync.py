from __future__ import annotations
import argparse
from pathlib import Path
from . import read_json, write_json
MAP=[('local_source_registry.json','Local_Source_Registry.md'),('local_file_inventory.json','File_Inventory.md'),('archive_inventory.json','Archive_Inventory.md'),('manuscript_digest_matrix.json','Manuscript_Digest_Matrix.md'),('simulator_artifact_matrix.json','Simulator_Artifact_Matrix.md'),('publication_lane_registry.json','Publication_Lanes.md'),('reusable_asset_registry.json','Reusable_Asset_Registry.md'),('speculative_quarantine_matrix.json','Speculative_Quarantine_Matrix.md'),('claim_risk_report.md','Claim_Risk_Report.md'),('system_integration_digest.md','System_Integration_Digest.md')]
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--vault',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    root=Path(a.root); vault=Path(a.vault); vault.mkdir(parents=True, exist_ok=True); written=[]
    for src,dst in MAP:
        sp=root/src
        if not sp.exists(): continue
        dp=vault/dst
        if src.endswith('.json'): dp.write_text('# '+dst.replace('.md','').replace('_',' ')+'\n\n```json\n'+sp.read_text(encoding='utf-8')+'\n```\n', encoding='utf-8')
        else: dp.write_text(sp.read_text(encoding='utf-8'), encoding='utf-8')
        written.append(str(dp))
    write_json(Path(a.out),{'written':written})
if __name__=='__main__': main()
