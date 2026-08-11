#!/usr/bin/env python3
"""Bring an MNI-space anatomical atlas (Schaefer-100) into a subject's native
functional grid, via real affine image registration -- not by feeding the raw
MNI atlas directly to native-space functional data.

ds000245 is raw BIDS: no fMRIPrep, no existing subject->MNI normalization. Using
an MNI atlas's labels directly against unwarped native-space BOLD would not be a
real anatomical parcellation -- the same label index would sample unrelated
anatomy in every subject, since no two subjects' native spaces line up with MNI
or with each other. This module performs the two registrations that make the
Schaefer atlas meaningful for a given subject's functional data:

  1. T1w (subject native anatomical) -> MNI152 template: affine (12 DOF)
     registration via `dipy`, mutual information metric (cross "modality" in the
     sense of contrast differences between an individual T1 and the template).
  2. Functional reference volume -> T1w (same subject): rigid (6 DOF)
     registration, same style as `motion_correction.py`'s per-volume realignment.

The Schaefer labels are then resampled (nearest-neighbor, since labels are
categorical) from MNI space -> T1 space -> functional native space by composing
the two `dipy` AffineMap inverse-transforms, giving a labels image on the exact
grid the functional data lives on, ready for `nilearn.maskers.NiftiLabelsMasker`.

Caveat carried into every result produced with this module: registration here is
AFFINE only (12 DOF: translation/rotation/scale/shear), not a full nonlinear
warp (e.g. ANTs SyN / FSL FNIRT). This corrects gross size/position/orientation
differences between a subject's brain and the template but does not capture
individual cortical-folding variability the way a nonlinear normalization would.
It is a real, registration-based anatomical alignment -- not zero normalization
-- but is coarser than a full nonlinear pipeline.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

import numpy as np

logging.getLogger("dipy").setLevel(logging.WARNING)


def _downsampled(data: np.ndarray, affine: np.ndarray, stride: int) -> tuple[np.ndarray, np.ndarray]:
    if stride <= 1:
        return data, affine
    ds = data[::stride, ::stride, ::stride, ...]
    scale = np.eye(4)
    scale[:3, :3] *= stride
    return ds, affine @ scale


def _affine_register(
    static: np.ndarray, static_affine: np.ndarray,
    moving: np.ndarray, moving_affine: np.ndarray,
    transform_cls,
    level_iters=(20, 10, 5), sigmas=(3.0, 1.0, 0.0), factors=(4, 2, 1),
):
    from dipy.align.imaffine import AffineRegistration, MutualInformationMetric, transform_centers_of_mass

    c_of_mass = transform_centers_of_mass(static, static_affine, moving, moving_affine)
    metric = MutualInformationMetric(nbins=32, sampling_proportion=0.3)
    affreg = AffineRegistration(
        metric=metric, level_iters=list(level_iters), sigmas=list(sigmas), factors=list(factors), verbosity=0,
    )
    return affreg.optimize(
        static, moving, transform_cls(), params0=None,
        static_grid2world=static_affine, moving_grid2world=moving_affine,
        starting_affine=c_of_mass.affine,
    )


def register_t1_to_mni(t1_path: str, downsample: int = 3):
    """Affine (12 DOF) T1w -> MNI152 (2mm) registration. Returns the dipy AffineMap."""
    import nibabel as nib
    from dipy.align.transforms import AffineTransform3D
    from nilearn import datasets

    t1_img = nib.load(t1_path)
    t1_data = np.asanyarray(t1_img.dataobj).astype(np.float32)
    t1_ds, t1_affine_ds = _downsampled(t1_data, t1_img.affine, downsample)

    mni_img = datasets.load_mni152_template(resolution=2)
    mni_data = np.asanyarray(mni_img.dataobj).astype(np.float32)

    return _affine_register(mni_data, mni_img.affine, t1_ds, t1_affine_ds, AffineTransform3D)


def register_func_to_t1(func_ref_vol: np.ndarray, func_affine: np.ndarray, t1_path: str, downsample: int = 3):
    """Rigid (6 DOF) functional-reference-volume -> T1w (same subject) registration."""
    import nibabel as nib
    from dipy.align.transforms import RigidTransform3D

    t1_img = nib.load(t1_path)
    t1_data = np.asanyarray(t1_img.dataobj).astype(np.float32)
    t1_ds, t1_affine_ds = _downsampled(t1_data, t1_img.affine, downsample)

    return _affine_register(t1_ds, t1_affine_ds, func_ref_vol.astype(np.float32), func_affine, RigidTransform3D)


def atlas_labels_in_func_space(
    atlas_labels_img_path: str,
    t1_to_mni_map,
    func_to_t1_map,
    func_shape: tuple[int, int, int],
    func_affine: np.ndarray,
) -> np.ndarray:
    """Resample MNI-space integer Schaefer labels into the subject's native functional grid."""
    import nibabel as nib

    atlas_img = nib.load(atlas_labels_img_path)
    atlas_data = np.asanyarray(atlas_img.dataobj).astype(np.float32)

    # MNI (static of t1_to_mni_map) -> T1 (moving of t1_to_mni_map)
    labels_in_t1 = t1_to_mni_map.transform_inverse(atlas_data, interpolation="nearest")

    # T1 (static of func_to_t1_map) -> func native (moving of func_to_t1_map)
    t1_img_affine = t1_to_mni_map.codomain_grid2world
    labels_in_t1_img = nib.Nifti1Image(labels_in_t1, t1_img_affine)
    # func_to_t1_map's static grid IS the (downsampled) T1 grid; rebuild an AffineMap
    # targeting the full-resolution T1 grid so labels line up with labels_in_t1's own array,
    # then invert into func space.
    from dipy.align.imaffine import AffineMap

    full_res_map = AffineMap(
        func_to_t1_map.affine,
        domain_grid_shape=labels_in_t1.shape,
        domain_grid2world=t1_img_affine,
        codomain_grid_shape=func_shape,
        codomain_grid2world=func_affine,
    )
    labels_in_func = full_res_map.transform_inverse(labels_in_t1, interpolation="nearest")
    return np.round(labels_in_func).astype(np.int32)


def _cache_key(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:16]


def get_or_compute_func_space_atlas(
    subject_id: str,
    t1_path: str,
    atlas_labels_img_path: str,
    func_ref_vol: np.ndarray,
    func_affine: np.ndarray,
    func_shape: tuple[int, int, int],
    cache_dir: Optional[Path],
    downsample: int = 3,
) -> np.ndarray:
    """Cache wrapper around the full T1->MNI + func->T1 -> atlas-in-func-space pipeline."""
    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = _cache_key(subject_id, t1_path, atlas_labels_img_path, str(downsample))
        cache_path = cache_dir / f"{key}_atlas_func_space.npz"
        if cache_path.exists():
            with np.load(cache_path) as npz:
                return npz["labels"]

    t1_to_mni_map = register_t1_to_mni(t1_path, downsample=downsample)
    func_to_t1_map = register_func_to_t1(func_ref_vol, func_affine, t1_path, downsample=downsample)
    labels = atlas_labels_in_func_space(
        atlas_labels_img_path, t1_to_mni_map, func_to_t1_map, func_shape, func_affine,
    )
    if cache_dir is not None:
        np.savez_compressed(cache_path, labels=labels)
    return labels
