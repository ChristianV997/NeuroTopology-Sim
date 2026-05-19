import subprocess, tempfile, pathlib

def test_validator_passes():
 root=pathlib.Path('outputs/literature_senses')
 subprocess.check_call(['make','literature-senses-fixture-run'])
 rc=subprocess.call(['python','-m','tools.literature_senses.validator','--root',str(root),'--json-out',str(root/'literature_senses_validation.json')])
 assert rc==0
