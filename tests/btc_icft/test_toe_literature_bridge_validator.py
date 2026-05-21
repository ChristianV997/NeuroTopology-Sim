import subprocess, sys
from pathlib import Path

def generate(out):
    cmds=[['generator','--roots','outputs/literature_senses','--out',str(out)],['topology_telemetry_digest','--out',str(out/'topology_telemetry_upgrade_digest.md')],['active_inference_digest','--out',str(out/'active_inference_allostasis_digest.md')],['computational_psychiatry_digest','--out',str(out/'computational_psychiatry_digest.md')],['bioelectric_digest','--out',str(out/'bioelectric_basal_cognition_digest.md')],['cosmology_constraints','--out',str(out/'cosmology_constraint_matrix.json')],['gravitational_wave_constraints','--out',str(out/'gravitational_wave_constraint_matrix.json')],['adversarial_consciousness_matrix','--out',str(out/'consciousness_theory_adversarial_matrix.json')],['equation_registry','--out',str(out/'equation_candidate_registry.json')],['falsifier_registry','--out',str(out/'toe_falsifier_watchlist.json')],['reporting','--root',str(out),'--out',str(out/'toe_literature_bridge_report.md')]]
    for c in cmds: subprocess.run([sys.executable,'-m',f'tools.toe_research.literature_bridge.{c[0]}',*c[1:]],check=True)

def test_validator_ok(tmp_path):
    out=tmp_path/'o'; out.mkdir(); generate(out)
    (out/'toe_theory_integration_digest.md').write_text('x')
    (out/'generation_manifest.json').write_text('{}')
    r=subprocess.run([sys.executable,'-m','tools.toe_research.literature_bridge.validator','--root',str(out),'--json-out',str(out/'v.json')])
    assert r.returncode==0
