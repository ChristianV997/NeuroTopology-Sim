from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from sciencer_d.btc_icft.io.eeg_reader_preflight import (
    build_reader_preflight_omega_event,
    build_reader_preflight_report,
    check_optional_reader_capabilities,
    detect_file_format,
    scan_eeg_dataset_files,
    write_reader_preflight_outputs,
)


def test_detect_formats():
    assert detect_file_format('a.csv')['status'] == 'readable_text_fixture'
    assert detect_file_format('a.tsv')['status'] == 'readable_text_fixture'
    assert detect_file_format('a.txt')['status'] == 'readable_text_fixture'
    assert detect_file_format('a.edf')['package'] == 'mne'
    assert detect_file_format('a.set')['package'] == 'mne'
    assert detect_file_format('a.fdt')['package'] == 'mne'
    assert detect_file_format('a.vhdr')['package'] == 'mne'
    assert detect_file_format('a.vmrk')['package'] == 'mne'
    assert detect_file_format('a.eeg')['package'] == 'mne'
    assert detect_file_format('a.hea')['package'] == 'wfdb'
    assert detect_file_format('a.dat')['package'] == 'wfdb'
    assert detect_file_format('a.mat')['package'] == 'scipy'
    assert detect_file_format('a.xyz')['status'] == 'unsupported_extension'
    assert detect_file_format('a')['status'] == 'unknown_format'


def test_capabilities_no_fail():
    caps = check_optional_reader_capabilities()
    assert any(c.reader_name == 'text_fixture_reader' for c in caps)


def test_scan_and_limits_and_status(tmp_path: Path):
    nested = tmp_path / 'a/b'; nested.mkdir(parents=True)
    (nested / 'x.csv').write_text('1,2\n', encoding='utf-8')
    (nested / 'y.edf').write_text('bin', encoding='utf-8')
    (tmp_path / 'z.xyz').write_text('u', encoding='utf-8')
    rows = scan_eeg_dataset_files(str(tmp_path), 'DS', None)
    assert len(rows) == 3
    assert any(r.readable_now for r in rows)
    assert any(r.reader_status in {'dependency_missing', 'dependency_available_not_extracted'} for r in rows)
    rows2 = scan_eeg_dataset_files(str(tmp_path), 'DS', 1)
    assert len(rows2) == 1


def test_report_outputs_and_json_csv(tmp_path: Path):
    rows = scan_eeg_dataset_files(str(tmp_path), 'DS')
    res = build_reader_preflight_report('DS', rows, check_optional_reader_capabilities())
    assert 'no_files_found' in res.extraction_blockers
    out = write_reader_preflight_outputs(res, str(tmp_path / 'out'))
    assert set(out.keys()) == {
        'eeg_file_manifest.csv','reader_capability_report.json','reader_preflight_summary.json','extraction_blockers.json','omega_event.json','report.md'
    }
    for p in out.values():
        assert Path(p).exists()
    json.loads(Path(out['reader_preflight_summary.json']).read_text())
    json.loads(Path(out['reader_capability_report.json']).read_text())
    with open(out['eeg_file_manifest.csv'], newline='', encoding='utf-8') as f:
        header = next(csv.reader(f))
    for col in ['dataset_id','file_path','file_name','extension','detected_format','file_size_bytes','reader_status','recommended_reader','optional_package_required','readable_now','blocked_reason','warnings']:
        assert col in header
    report = Path(out['report.md']).read_text().lower()
    assert 'reader capability' in report
    assert 'extraction readiness' in report
    assert 'without parsing binary signals or inferring labels' in report
    assert 'proves consciousness' not in report


def test_ready_true_false_and_omega(tmp_path: Path):
    (tmp_path / 'a.csv').write_text('1,2\n', encoding='utf-8')
    res = build_reader_preflight_report('DS', scan_eeg_dataset_files(str(tmp_path), 'DS'), check_optional_reader_capabilities())
    assert res.extraction_ready is True
    tmp2 = tmp_path / 'b'; tmp2.mkdir(); (tmp2/'a.edf').write_text('x', encoding='utf-8')
    res2 = build_reader_preflight_report('DS', scan_eeg_dataset_files(str(tmp2), 'DS'), check_optional_reader_capabilities())
    assert res2.extraction_ready is False
    omega = build_reader_preflight_omega_event(res)
    assert 'safe_claim' in omega
    assert 'proves consciousness' not in json.dumps(omega).lower()


def test_cli_and_config_and_boundaries(tmp_path: Path):
    out = tmp_path / 'o'
    ok = subprocess.run([sys.executable, '-m', 'sciencer_d.btc_icft.pipelines.preflight_eeg_readers', '--dataset-id','DS005620','--out',str(out),'--mock-fixture'], capture_output=True, text=True)
    assert ok.returncode == 0
    assert (out / 'report.md').exists()
    bad = subprocess.run([sys.executable, '-m', 'sciencer_d.btc_icft.pipelines.preflight_eeg_readers'], capture_output=True, text=True)
    assert bad.returncode != 0
    empty = tmp_path / 'empty'; empty.mkdir()
    ok2 = subprocess.run([sys.executable, '-m', 'sciencer_d.btc_icft.pipelines.preflight_eeg_readers', '--root', str(empty), '--out', str(tmp_path/'e')], capture_output=True, text=True)
    assert ok2.returncode == 0
    summary = json.loads((tmp_path/'e'/'reader_preflight_summary.json').read_text())
    assert summary['extraction_ready'] is False
    cfg = Path('configs/btc_icft/eeg_reader_preflight.yaml').read_text()
    assert 'required_outputs' in cfg and 'guardrails' in cfg
    src = Path('sciencer_d/btc_icft/pipelines/preflight_eeg_readers.py').read_text()
    assert 'ds005620_contract_activation' not in src
    assert 'run_eeg_signal_mt' not in src
    assert 'mt_real' not in src
