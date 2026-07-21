"""Atlas and parcellation utilities via nilearn (BSD-3 license).

Provides standardized, no-gate atlas fetchers (Schaefer, Yeo, HarvardOxford) and
parcellation maskers for fast NIfTI → parcel-timeseries pipelines. Replaces
ad-hoc region definitions (e.g., mmp360_yeo.json) with published, versioned atlases.

Schaefer atlas: 100, 200, 400, or 1000 ROIs
Yeo networks: 7 or 17 functional networks (for Schaefer subfolding)
HarvardOxford: 48 or 110 regions (alternative cortical atlas)

All atlases are installed via nilearn's native fetchers, cached locally, and require
no downloading at runtime after first fetch.
"""
from __future__ import annotations

from typing import Optional, Tuple
import warnings

import numpy as np

try:
    from nilearn import datasets, maskers
    NILEARN_AVAILABLE = True
except ImportError:
    NILEARN_AVAILABLE = False


def fetch_schaefer_atlas(
    n_rois: int = 400,
    yeo_colors: bool = True,
) -> dict:
    """Fetch the Schaefer parcellation atlas (Schaefer et al., 2018).

    Parameters
    ----------
    n_rois : int
        Number of ROIs: 100, 200, 400, or 1000 (default 400).
    yeo_colors : bool
        If True (default), returns the Yeo-colorized version (ROIs grouped into
        7 or 17 functional networks). If False, returns the unlabeled atlas.

    Returns
    -------
    dict
        Keys: 'maps' (3D NIfTI-like array), 'labels' (list of region names),
        'atlas' (nibabel Nifti1Image object for direct write).

    Raises
    ------
    ImportError
        If nilearn is not installed.
    ValueError
        If n_rois is not one of {100, 200, 400, 1000}.
    """
    if not NILEARN_AVAILABLE:
        raise ImportError("nilearn is required for atlas fetching; pip install nilearn")

    if n_rois not in (100, 200, 400, 1000):
        raise ValueError(f"n_rois must be in {{100, 200, 400, 1000}}, got {n_rois}")

    atlas = datasets.fetch_atlas_schaefer_2018(
        n_rois=n_rois,
        yeo_networks=7 if yeo_colors else None,
        data_dir=None,  # Use default nilearn cache
    )

    return {
        "maps": atlas.maps,
        "labels": atlas.labels.tolist() if hasattr(atlas.labels, "tolist") else list(atlas.labels),
        "atlas": atlas,
        "n_rois": n_rois,
        "source": "Schaefer et al., 2018",
    }


def fetch_yeo_networks(
    n_networks: int = 7,
) -> dict:
    """Fetch Yeo functional network atlas (Yeo et al., 2011).

    Parameters
    ----------
    n_networks : int
        Number of networks: 7 or 17 (default 7).

    Returns
    -------
    dict
        Keys: 'maps', 'labels', 'atlas', 'n_networks', 'source'.
    """
    if not NILEARN_AVAILABLE:
        raise ImportError("nilearn is required for atlas fetching; pip install nilearn")

    if n_networks not in (7, 17):
        raise ValueError(f"n_networks must be in {{7, 17}}, got {n_networks}")

    atlas = datasets.fetch_atlas_yeo_2011(
        data_dir=None,
    )

    # Select the appropriate network map
    if n_networks == 7:
        maps = atlas.anat_7networks
        labels_key = "networks_7"
    else:
        maps = atlas.anat_17networks
        labels_key = "networks_17"

    # Build labels from the networks
    labels = [f"Network_{i+1}" for i in range(n_networks)]

    return {
        "maps": maps,
        "labels": labels,
        "atlas": atlas,
        "n_networks": n_networks,
        "source": "Yeo et al., 2011",
    }


def fetch_harvard_oxford_atlas(
    n_regions: int = 48,
) -> dict:
    """Fetch HarvardOxford cortical atlas.

    Parameters
    ----------
    n_regions : int
        Number of regions: 48 (basic) or 110 (expanded, default 48).

    Returns
    -------
    dict
        Keys: 'maps', 'labels', 'atlas', 'n_regions', 'source'.
    """
    if not NILEARN_AVAILABLE:
        raise ImportError("nilearn is required for atlas fetching; pip install nilearn")

    if n_regions not in (48, 110):
        raise ValueError(f"n_regions must be in {{48, 110}}, got {n_regions}")

    atlas = datasets.fetch_atlas_harvard_oxford(
        "cort-maxprob-thr25-1mm" if n_regions == 48 else "cort-maxprob-thr25-2mm",
        data_dir=None,
    )

    labels = getattr(atlas, "labels", [f"Region_{i}" for i in range(n_regions)])

    return {
        "maps": atlas.maps,
        "labels": labels if isinstance(labels, list) else labels.tolist(),
        "atlas": atlas,
        "n_regions": n_regions,
        "source": "HarvardOxford",
    }


def get_parcel_timeseries(
    bold_img,
    atlas_maps,
    atlas_labels: Optional[list] = None,
) -> Tuple[np.ndarray, list]:
    """Extract parcel timeseries from BOLD data using atlas.

    Parameters
    ----------
    bold_img : nibabel.Nifti1Image or str
        4D BOLD image (3D spatial + time).
    atlas_maps : nibabel.Nifti1Image or str
        3D parcellation atlas (integer labels per voxel).
    atlas_labels : list of str, optional
        Human-readable labels for each parcel (index=parcel_id-1).

    Returns
    -------
    parcel_timeseries : (n_parcels, n_timepoints) array
        Mean timeseries per parcel.
    labels : list
        Parcel labels (or ["Parcel_1", ...] if atlas_labels is None).
    """
    if not NILEARN_AVAILABLE:
        raise ImportError("nilearn is required for parcellation masking; pip install nilearn")

    masker = maskers.NiftiLabelsMasker(atlas_maps)
    timeseries = masker.fit_transform(bold_img)

    if atlas_labels is None:
        n_parcels = timeseries.shape[1]
        labels = [f"Parcel_{i+1}" for i in range(n_parcels)]
    else:
        labels = atlas_labels

    return timeseries, labels


def ci_fixture_adhd_sample() -> dict:
    """Fetch small ADHD 200 sample for CI/offline testing (40 subjects, pre-cached).

    Requires no network access after initial fetch; nilearn caches it locally.
    Use this instead of live OpenNeuro fetches for CI gates.

    Returns
    -------
    dict
        Keys: 'data' (list of subject dictionaries), 'description' (str).
        Each subject dict: {'anat': path, 'func': list of paths, 'confounds': path}.
    """
    if not NILEARN_AVAILABLE:
        raise ImportError("nilearn is required for fixture fetching; pip install nilearn")

    adhd = datasets.fetch_adhd(
        n_subjects=40,
        data_dir=None,
    )

    return {
        "data": adhd.data,
        "description": "ADHD 200 sample (40 subjects, CC0 open data, no DUA required)",
        "source": "http://fcon_1000.projects.nitrc.org/indi/adhd200/",
    }
