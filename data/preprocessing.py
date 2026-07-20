"""Real EEG preprocessing: bandpass/notch filtering and re-referencing.

Every metric this repository's dataset-report pipelines have computed so far
(topology, band power, connectivity, ...) was computed on completely
unfiltered signal -- `data/bids_ingest.py::read_window_signal` slices raw
samples directly; there is no bandpass filter, no line-noise notch, no
re-referencing anywhere upstream in any of the three published BTC/ICFT
dataset reports. This module is the fix, using `mne`'s built-in filtering
(already a dependency, essentially unused for this).

Filtering is applied to the FULL continuous recording, before windowing --
not per-window, which would introduce filter edge artifacts (transients) at
every window boundary. That's a correctness requirement of digital
filtering, not a style choice: `scipy`/`mne`'s filters need padding at the
signal edges, and a 4-10 second window has proportionally much more "edge"
relative to its length than a multi-minute recording does.

Opt-in via `read_window_signal`'s `preprocess` parameter (a dict of kwargs
for `preprocess_raw`, default `None`): omitting it produces byte-identical
output to before this module existed, so every currently-published number in
the three existing dataset reports stays reproducible until a pipeline
explicitly opts in and that re-derivation is documented (see the
repo-hardening plan's `REPRODUCIBILITY_NOTE.md` pattern).
"""
from __future__ import annotations

DEFAULT_BANDPASS_HZ = (0.5, 45.0)


def preprocess_raw(
    raw,
    l_freq: float | None = 0.5,
    h_freq: float | None = 45.0,
    notch_freq: float | list[float] | None = None,
    reference: str | list[str] | None = "average",
):
    """Apply real bandpass filtering, an optional line-noise notch, and
    re-referencing to an MNE `Raw` object, IN PLACE, on the FULL recording.

    Call this before slicing any window out of `raw` -- filtering after
    windowing would filter each short window independently, introducing edge
    transients this function's whole-recording application avoids.

    Parameters
    ----------
    l_freq, h_freq : bandpass edges in Hz, following `mne.io.Raw.filter`'s own
        convention -- either may be `None` to apply only a high-pass or
        low-pass. Default 0.5-45 Hz is a standard broadband EEG passband
        (removes DC drift/slow artifacts below 0.5 Hz and anything above
        typical EEG-relevant content).
    notch_freq : line-noise frequency (or list of harmonics) to notch out.
        Left `None` by default -- deliberately dataset-specific (50 Hz for
        EU/most-of-world recordings, 60 Hz for US recordings); pass it
        explicitly per dataset rather than guessing which mains frequency a
        given recording used.
    reference : `"average"` (common-average reference, the standard default
        for scalp EEG when no dedicated reference channel is trusted), a
        specific channel name/list, or `None` to skip re-referencing
        entirely.

    Returns
    -------
    The same `raw` object, filtered/re-referenced in place (also returned for
    convenient chaining).
    """
    import mne

    raw.load_data(verbose="ERROR")
    picks = mne.pick_types(raw.info, eeg=True)
    if l_freq is not None or h_freq is not None:
        raw.filter(l_freq=l_freq, h_freq=h_freq, picks=picks, verbose="ERROR")
    if notch_freq is not None:
        raw.notch_filter(freqs=notch_freq, picks=picks, verbose="ERROR")
    if reference is not None:
        raw.set_eeg_reference(reference, verbose="ERROR")
    return raw


def label_and_remove_ica_artifacts(
    raw,
    n_components: int | None = None,
    random_state: int = 97,
    exclude_labels: tuple[str, ...] = ("eye blink", "muscle artifact", "heart beat"),
):
    """Fit ICA on `raw` and use `mne-icalabel`'s ICLabel classifier to
    automatically flag and remove eye/muscle/heart-artifact components,
    returning a cleaned copy of `raw` plus a report of what was removed.

    Opt-in, heavier alternative/complement to `sciencer_d/btc_icft/level_m/
    features.py`'s hand-rolled `artifact_score` heuristic (a sample-to-sample
    jump/std ratio) -- this is the published, validated ICLabel classifier
    instead of an ad hoc statistic.

    Requires `raw.info` to already carry a channel montage (electrode
    positions) -- ICLabel's model uses topographic scalp features to classify
    each component; call `raw.set_montage(...)` first if the recording's own
    channel positions aren't already attached (real BIDS EEG recordings
    usually have positions from the manufacturer's cap layout; synthetic data
    needs one set explicitly).

    ICLabel specifically requires ICA fit with extended Infomax
    (`method="infomax", fit_params=dict(extended=True)`) and a 1-100 Hz
    bandpass (both ICLabel's own documented requirements, not free choices
    made here) -- applied internally on a copy so this function is correct
    regardless of what broader preprocessing (e.g. `preprocess_raw`'s default
    0.5-45 Hz) happened upstream.
    """
    import mne
    from mne_icalabel import label_components

    raw = raw.copy()
    raw.load_data(verbose="ERROR")
    nyq = float(raw.info["sfreq"]) / 2.0
    raw.filter(l_freq=1.0, h_freq=min(100.0, nyq - 1.0), verbose="ERROR")
    raw.set_eeg_reference("average", verbose="ERROR")  # ICLabel expects a referenced signal

    ica = mne.preprocessing.ICA(
        n_components=n_components, method="infomax",
        fit_params=dict(extended=True), random_state=random_state, max_iter="auto",
    )
    ica.fit(raw, verbose="ERROR")

    labels = label_components(raw, ica, method="iclabel")
    component_labels = list(labels["labels"])
    exclude_idx = [i for i, lbl in enumerate(component_labels) if lbl in exclude_labels]

    cleaned = raw.copy()
    ica.apply(cleaned, exclude=exclude_idx, verbose="ERROR")

    report = {
        "n_components": int(ica.n_components_),
        "labels": component_labels,
        "excluded_indices": exclude_idx,
        "excluded_labels": [component_labels[i] for i in exclude_idx],
    }
    return cleaned, report


def autoreject_epochs(epochs, random_state: int = 97, n_jobs: int = 1):
    """Cross-validated per-epoch/per-channel statistical rejection via
    `autoreject` (Jas et al. 2017) -- a validated, published method, unlike
    this repo's hand-rolled `artifact_score` heuristic.

    Operates on already-epoched `mne.Epochs` data. This repo's window-slicing
    pipelines (`data/bids_ingest.py::read_window_signal`) currently build raw
    numpy arrays directly rather than `mne.Epochs` objects, so this function
    is available for any pipeline stage that does construct Epochs (e.g. a
    future per-recording preprocessing step upstream of windowing), rather
    than wired into the per-window path itself.

    Returns `(clean_epochs, reject_log)` -- `reject_log.bad_epochs` records
    which epochs were dropped entirely; interpolated (repaired, not dropped)
    channels are recorded per-epoch in `reject_log.labels`.
    """
    from autoreject import AutoReject

    ar = AutoReject(random_state=random_state, n_jobs=n_jobs, verbose=False)
    clean_epochs, reject_log = ar.fit_transform(epochs, return_log=True)
    return clean_epochs, reject_log
