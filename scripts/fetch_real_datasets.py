"""Download the explicitly requested local PDB and optional OpenNeuro EEG triplet."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


SCIENCER_ROOT = Path(__file__).resolve().parents[1]
NEURO_ROOT = SCIENCER_ROOT.parent / "NeuroTopology-Sim"
PDB_URL = "https://files.rcsb.org/download/1JFF.pdb"
# Verified public BIDS key (ds005620 has no ``ses-01`` directory for sub-1010).
S3_PREFIX = "s3://openneuro.org/ds005620/sub-1010/eeg/sub-1010_task-sed2_acq-rest_run-1_eeg"


def download_pdb(destination: Path) -> str:
    """Fetch PDB 1JFF by HTTPS and atomically place it in the local data directory."""
    if destination.is_file() and destination.stat().st_size >= 1000: return "already_present"
    destination.parent.mkdir(parents=True, exist_ok=True); temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(PDB_URL, timeout=60) as response, temporary.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        if temporary.stat().st_size < 1000: raise RuntimeError("download is unexpectedly small")
        temporary.replace(destination); return "downloaded"
    finally:
        if temporary.exists(): temporary.unlink()


def download_eeg(destination: Path) -> tuple[bool, str]:
    """Use public unsigned S3 only when AWS CLI is locally available; no credentials are used."""
    names = [destination / f"sub-1010_task-sed2_acq-rest_run-1_eeg{suffix}" for suffix in (".vhdr", ".eeg", ".vmrk")]
    if all(path.is_file() and path.stat().st_size > 0 for path in names): return True, "already_present"
    aws = shutil.which("aws")
    if aws is None:
        return False, f"AWS CLI unavailable. Manual command: aws s3 cp --no-sign-request {S3_PREFIX}.vhdr {destination}"
    destination.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for suffix in (".vhdr", ".eeg", ".vmrk"):
        target = destination / f"sub-1010_task-sed2_acq-rest_run-1_eeg{suffix}"
        completed = subprocess.run([aws, "s3", "cp", "--no-sign-request", S3_PREFIX + suffix, str(target)], capture_output=True, text=True, timeout=120, check=False)
        if completed.returncode != 0: failures.append(f"{suffix}: {completed.stderr.strip() or completed.stdout.strip()}")
    return not failures, "downloaded" if not failures else "; ".join(failures)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--skip-eeg", action="store_true"); args = parser.parse_args()
    pdb = SCIENCER_ROOT / "data" / "1jff.pdb"
    try: pdb_status = download_pdb(pdb)
    except Exception as exc: pdb_status = f"failed: {type(exc).__name__}: {exc}"
    eeg_ok, eeg_status = (False, "skipped") if args.skip_eeg else download_eeg(NEURO_ROOT / "data" / "ds005620")
    print({"pdb": str(pdb), "pdb_status": pdb_status, "eeg_available": eeg_ok, "eeg_status": eeg_status})
    return 0 if pdb_status in {"downloaded", "already_present"} else 1


if __name__ == "__main__": raise SystemExit(main())
