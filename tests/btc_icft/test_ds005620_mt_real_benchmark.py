from pathlib import Path
from sciencer_d.btc_icft.pipelines.run_ds005620_mt_real import main

def test_cli_mock_fixture_smoke(tmp_path):
    rc=main(['--out',str(tmp_path),'--mock-fixture'])
    assert rc==0
