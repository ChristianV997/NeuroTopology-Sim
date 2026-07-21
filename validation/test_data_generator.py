"""Generate synthetic BIDS-format EEG data for pipeline testing when OpenNeuro access is restricted.

This module creates realistic synthetic ds005620-format EEG data matching the pipeline's
expectations. Use this for validation when network restrictions block OpenNeuro S3/git-annex
access. Production runs should use the actual OpenNeuro data via datalad.

Generates:
- BrainVision triplets (.vhdr, .vmrk, .eeg) in BIDS structure
- 64-channel synthetic signals at 5000 Hz
- Awake and sedated conditions with realistic topology metrics
"""
from pathlib import Path
import numpy as np
import json
from dataclasses import asdict


def generate_brainavision_triplet(subject: str, condition: str, run: str, out_dir: Path,
                                  n_channels: int = 64, sfreq: float = 5000.0,
                                  duration_s: float = 60.0, seed: int = 42,
                                  task: str = None, acq: str = None,
                                  ch_names: list[str] = None):
    """Generate a synthetic BrainVision EEG triplet for testing.

    Parameters
    ----------
    subject : str
        Subject ID (e.g., "1010")
    condition : str
        Condition label (e.g., "awake", "sed")
    run : str
        Run/session label (e.g., "", "run-1")
    out_dir : Path
        Output directory
    n_channels : int
        Number of EEG channels (default 64)
    sfreq : float
        Sampling frequency in Hz (default 5000)
    duration_s : float
        Recording duration in seconds (default 60)
    seed : int
        Random seed for reproducibility
    task : str
        BIDS task label (overrides condition for filename)
    acq : str
        BIDS acquisition label (e.g., "EC", "rest")
    ch_names : list[str]
        Channel names (must be 10-20 compatible or list of n_channels)
    """
    # Default ds005620 channel list (64 channels including VEOG, HEOG, EMG)
    DS005620_CHANNELS = [
        "Iz", "O2", "Oz", "O1", "PO8", "PO4", "POz", "PO3", "PO7",
        "P8", "P6", "P4", "P2", "Pz", "P1", "P3", "P5", "P7",
        "TP10", "TP8", "CP6", "CP4", "CP2", "CPz", "CP1", "CP3", "CP5", "TP7", "TP9",
        "T8", "C6", "C4", "C2", "Cz", "C1", "C3", "C5", "T7",
        "FT8", "FC6", "FC4", "FC2", "FCz", "FC1", "FC3", "FC5", "FT7",
        "F8", "F6", "F4", "F2", "Fz", "F1", "F3", "F5", "F7",
        "AF4", "AFz", "AF3", "Fp2", "Fpz", "Fp1",
        "VEOG", "HEOG", "EMG"
    ]

    rng = np.random.RandomState(seed)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Use provided task/acq or default from condition
    if task is None:
        task = condition
    if acq is None:
        acq = "EC" if condition == "awake" else "rest"

    # Use provided channel names or default
    if ch_names is None:
        ch_names = DS005620_CHANNELS[:n_channels]

    # Generate synthetic EEG data
    n_samples = int(sfreq * duration_s)

    # Multi-scale synthetic signal: slow oscillations + faster bands + noise
    t = np.arange(n_samples) / sfreq
    signal = np.zeros((n_channels, n_samples))

    for ch in range(n_channels):
        # Delta/theta oscillations (realistic baseline)
        signal[ch] += 50.0 * np.sin(2 * np.pi * 1.5 * t) * np.exp(-0.01 * t)

        # Alpha band modulation (condition-dependent)
        alpha_power = 30.0 if condition == "awake" else 10.0  # Reduced alpha in sedation
        signal[ch] += alpha_power * np.sin(2 * np.pi * 10.0 * t + 0.1 * ch)

        # Beta band (for cognitive engagement, higher in awake)
        beta_power = 15.0 if condition == "awake" else 5.0
        signal[ch] += beta_power * np.sin(2 * np.pi * 20.0 * t + 0.05 * ch)

        # 1/f pink noise background
        freq_domain = rng.randn(n_samples // 2 + 1) + 1j * rng.randn(n_samples // 2 + 1)
        freqs = np.fft.rfftfreq(n_samples, 1/sfreq)
        freq_domain /= np.sqrt(freqs + 1) ** 1.5  # 1/f spectrum
        noise = np.real(np.fft.irfft(freq_domain, n_samples))
        signal[ch] += noise * np.sqrt(10.0)  # Scale noise appropriately

    # Quantize to 16-bit (as in real BrainVision)
    signal = np.int16(signal * 1000)  # Scale to use full int16 range

    # Build filenames using BIDS convention
    run_str = f"_run-{run}" if run else ""
    base = f"sub-{subject}_task-{task}_acq-{acq}{run_str}_eeg"

    # Write .eeg (binary data file)
    eeg_path = out_dir / f"{base}.eeg"
    signal.astype("<i2").tofile(eeg_path)  # Little-endian int16

    # Write .vhdr (header file)
    vhdr_path = out_dir / f"{base}.vhdr"

    # Build vhdr content (BrainVision format, case-sensitive)
    vhdr_lines = [
        "Brain Vision Data Exchange Header File Version 1.0",
        f"; Data file: {eeg_path.name}",
        f"; Marker file: {base}.vmrk",
        "",
        "[Common Infos]",
        "Codepage=UTF-8",
        f"DataFile={eeg_path.name}",
        f"MarkerFile={base}.vmrk",
        "DataFormat=BINARY",
        "DataOrientation=MULTIPLEXED",
        "DataType=EEG",
        f"NumberOfChannels={n_channels}",
        f"SamplingInterval={int(1e6/sfreq)}",
        "",
        "[Binary Infos]",
        "BinaryFormat=INT_16",
        "",
        "[Channel Infos]"
    ]

    # Add channel specifications using proper 10-20 channel names
    for i in range(n_channels):
        ch = ch_names[i]
        vhdr_lines.append(f"Ch{i+1}={ch},,0.1,µV,0.0,{int(1e6/sfreq)},Fpz")

    vhdr_lines.extend([
        "",
        "[Comment]",
        "Synthetic test data for ds005620 pipeline validation",
        f"Subject: sub-{subject}",
        f"Condition: {condition}",
        f"Duration: {duration_s} seconds",
        f"Sampling Rate: {sfreq} Hz"
    ])

    vhdr_path.write_text('\n'.join(vhdr_lines))

    # Write .vmrk (marker file - empty for simplicity)
    vmrk_path = out_dir / f"{base}.vmrk"
    vmrk_path.write_text(f"""Brain Vision Data Exchange Marker File, Version 1.0

[Common Infos]
Codepage=UTF-8

[Marker Infos]
; Generated synthetic data
""")

    # Write BIDS JSON sidecar
    json_path = out_dir / f"{base}.json"
    json_path.write_text(json.dumps({
        "SamplingFrequency": sfreq,
        "PowerLineFrequency": 50.0,
        "EEGChannelCount": n_channels,
        "EEGReference": "unknown",
        "RecordingDuration": duration_s,
        "TaskName": condition,
        "SyntheticData": True,
        "GeneratedFor": "pipeline_testing"
    }, indent=2))

    return vhdr_path


def generate_ds005620_test_dataset(base_dir: Path, subjects: list[str],
                                   conditions: list[str] = ["awake", "sed"]) -> dict:
    """Generate a complete test dataset matching ds005620 BIDS structure.

    Parameters
    ----------
    base_dir : Path
        Root directory for the synthetic dataset
    subjects : list[str]
        Subject IDs to generate (e.g., ["1010", "1016", "1017"])
    conditions : list[str]
        Conditions to generate per subject

    Returns
    -------
    dict
        Metadata about generated files
    """
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    generated = {"subjects": {}}

    for sub in subjects:
        sub_dir = base_dir / f"sub-{sub}" / "eeg"
        sub_dir.mkdir(parents=True, exist_ok=True)
        generated["subjects"][sub] = {"conditions": {}}

        for cond in conditions:
            if cond == "awake":
                # Awake: EC acquisition, one recording
                runs = [""]
                acq = "EC"
                task = "awake"
            elif cond == "sed":
                # Sed: rest acquisition (not EC), multiple runs
                runs = ["1", "2", "3"]
                acq = "rest"
                task = "sed"
            else:
                continue

            for run in runs:
                # Use ds005620 channel list (64 channels including EOG/EMG)
                vhdr = generate_brainavision_triplet(
                    sub, cond, run, sub_dir, seed=hash((sub, cond, run)) % (2**31),
                    task=task, acq=acq
                )
                run_label = run
                generated["subjects"][sub]["conditions"].setdefault(cond, []).append({
                    "run": run_label,
                    "vhdr": str(vhdr)
                })

    return generated


if __name__ == "__main__":
    import sys
    out_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/ds005620_synthetic")

    print(f"Generating synthetic ds005620 test data in {out_root}...")
    metadata = generate_ds005620_test_dataset(
        out_root,
        subjects=["1010", "1016", "1017"],
        conditions=["awake", "sed"]
    )

    print(json.dumps(metadata, indent=2))
    print(f"\n✓ Generated {sum(len(v['conditions']) for v in metadata['subjects'].values())} conditions")
