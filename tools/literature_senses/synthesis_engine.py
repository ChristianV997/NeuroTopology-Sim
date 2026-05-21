import argparse, os
from .common import read_json,write_json
if __name__=='__main__':
 p=argparse.ArgumentParser();
 for x in ['scored','claims','tiers','mapping','falsifiers','out']: p.add_argument(f'--{x}',required=True)
 a=p.parse_args();os.makedirs(a.out,exist_ok=True)
 Path=__import__('pathlib').Path
 Path(a.out,'theory_integration_digest.md').write_text('# Theory Integration Digest\n\nNo validation/proof claims.\n',encoding='utf-8')
 Path(a.out,'living_review_report.md').write_text('# Living Review Report\n\nClaim governance status: quarantined fixture evidence.\n',encoding='utf-8')
 write_json(str(Path(a.out,'generation_manifest.json')),{"inputs":a.__dict__})
