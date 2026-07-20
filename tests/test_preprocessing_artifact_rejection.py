"""Tests for data/preprocessing.py's opt-in, heavier artifact-rejection
instruments: ICA + mne-icalabel (ICLabel) component classification, and
autoreject's cross-validated per-epoch/per-channel statistical rejection.
Both replace this repo's hand-rolled `artifact_score` heuristic
(sciencer_d/btc_icft/level_m/features.py) with published, validated methods.
"""
from __future__ import annotations

import importlib.util

import numpy as np
import pytest

_HAVE_ICALABEL = importlib.util.find_spec("mne_icalabel") is not None
_HAVE_AUTOREJECT = importlib.util.find_spec("autoreject") is not None


def _make_raw_with_montage(n_ch=6, sfreq=100.0, n_seconds=8.0, seed=0):
    import mne

    n_samples = int(sfreq * n_seconds)
    rng = np.random.default_rng(seed)
    data = rng.standard_normal((n_ch, n_samples)) * 1e-5
    ch_names = [f"EEG{i:03d}" for i in range(n_ch)]
    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    raw = mne.io.RawArray(data, info, verbose="ERROR")
    montage = mne.channels.make_standard_montage("standard_1020")
    std_names = montage.ch_names[:n_ch]
    raw.rename_channels(dict(zip(ch_names, std_names)))
    raw.set_montage(montage, verbose="ERROR")
    return raw


# ---------------------------------------------------------------------------
# label_and_remove_ica_artifacts
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAVE_ICALABEL, reason="requires mne-icalabel")
def test_ica_artifact_removal_excludes_labeled_components(monkeypatch):
    """Deterministic test of THIS function's own selection/apply logic:
    monkeypatch mne_icalabel.label_components to a controlled labeling so the
    test doesn't depend on ICLabel's real (slower, less predictable on pure
    synthetic noise) classification of this specific signal."""
    from data import preprocessing

    raw = _make_raw_with_montage(n_ch=4, n_seconds=4.0)

    def fake_label_components(inst, ica, method):
        return {"y_pred_proba": np.array([0.9, 0.9, 0.9]), "labels": ["eye blink", "other", "muscle artifact"]}

    monkeypatch.setattr(preprocessing, "label_components", fake_label_components, raising=False)
    monkeypatch.setattr("mne_icalabel.label_components", fake_label_components)

    cleaned, report = preprocessing.label_and_remove_ica_artifacts(raw, n_components=3)
    assert report["labels"] == ["eye blink", "other", "muscle artifact"]
    assert set(report["excluded_labels"]) == {"eye blink", "muscle artifact"}
    assert report["excluded_indices"] == [0, 2]
    assert not np.array_equal(cleaned.get_data(), raw.get_data())


@pytest.mark.skipif(not _HAVE_ICALABEL, reason="requires mne-icalabel")
def test_ica_artifact_removal_real_iclabel_smoke():
    """Real, unmocked end-to-end smoke test: ICA + real ICLabel classifier on
    synthetic multi-channel data with real 10-20 electrode positions. Proves
    the actual wiring (ICA fit -> ICLabel -> exclude -> apply) works, not
    just this function's internal branching logic."""
    from data.preprocessing import label_and_remove_ica_artifacts

    raw = _make_raw_with_montage(n_ch=6, n_seconds=8.0)
    cleaned, report = label_and_remove_ica_artifacts(raw, n_components=3)

    assert report["n_components"] == 3
    assert len(report["labels"]) == 3
    assert all(isinstance(lbl, str) for lbl in report["labels"])
    assert cleaned.get_data().shape == raw.get_data().shape


@pytest.mark.skipif(not _HAVE_ICALABEL, reason="requires mne-icalabel")
def test_ica_artifact_removal_requires_channel_positions():
    """No montage set -> ICLabel cannot compute topographic features and must
    fail loudly, not silently produce meaningless labels."""
    import mne

    from data.preprocessing import label_and_remove_ica_artifacts

    sfreq = 100.0
    rng = np.random.default_rng(0)
    data = rng.standard_normal((4, 800)) * 1e-5
    info = mne.create_info(ch_names=[f"EEG{i:03d}" for i in range(4)], sfreq=sfreq, ch_types="eeg")
    raw = mne.io.RawArray(data, info, verbose="ERROR")  # no montage set

    with pytest.raises(Exception):
        label_and_remove_ica_artifacts(raw, n_components=3)


# ---------------------------------------------------------------------------
# autoreject_epochs
# ---------------------------------------------------------------------------

def _make_epochs_with_one_bad(n_ch=6, sfreq=100.0, n_epochs=12, seed=0):
    import mne

    n_samples = int(sfreq * 1.0)
    rng = np.random.default_rng(seed)
    data = rng.standard_normal((n_epochs, n_ch, n_samples)) * 1e-5
    data[3] *= 500  # one obviously bad, huge-amplitude epoch

    ch_names = [f"EEG{i:03d}" for i in range(n_ch)]
    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    montage = mne.channels.make_standard_montage("standard_1020")
    std_names = montage.ch_names[:n_ch]
    info.rename_channels(dict(zip(ch_names, std_names)))
    events = np.array([[i * n_samples, 0, 1] for i in range(n_epochs)])
    epochs = mne.EpochsArray(data, info, events=events, verbose="ERROR")
    epochs.set_montage(montage, verbose="ERROR")
    return epochs


@pytest.mark.skipif(not _HAVE_AUTOREJECT, reason="requires autoreject")
def test_autoreject_flags_the_synthetic_bad_epoch():
    """A known-bad epoch (500x amplitude of the rest) must be flagged in
    reject_log.bad_epochs -- the ground-truth case autoreject exists to catch."""
    from data.preprocessing import autoreject_epochs

    epochs = _make_epochs_with_one_bad()
    clean_epochs, reject_log = autoreject_epochs(epochs, n_jobs=1)

    assert reject_log.bad_epochs[3] == True  # noqa: E712 (numpy bool, explicit compare is clearer here)
    assert len(clean_epochs) < len(epochs)


@pytest.mark.skipif(not _HAVE_AUTOREJECT, reason="requires autoreject")
def test_autoreject_requires_channel_positions():
    import mne

    from data.preprocessing import autoreject_epochs

    sfreq = 100.0
    n_samples = int(sfreq * 1.0)
    rng = np.random.default_rng(0)
    data = rng.standard_normal((6, 4, n_samples)) * 1e-5
    info = mne.create_info(ch_names=[f"EEG{i:03d}" for i in range(4)], sfreq=sfreq, ch_types="eeg")
    events = np.array([[i * n_samples, 0, 1] for i in range(6)])
    epochs = mne.EpochsArray(data, info, events=events, verbose="ERROR")  # no montage

    with pytest.raises(Exception):
        autoreject_epochs(epochs, n_jobs=1)
