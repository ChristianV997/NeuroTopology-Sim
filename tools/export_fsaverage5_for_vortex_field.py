"""
Export FreeSurfer's fsaverage5 pial cortical surface for the /vortex-field 3D viewer.

Reads the fsaverage5 pial surface and sulcal curvature that ships locally with the
installed `nilearn` package (no network fetch: `nilearn.datasets.data.fsaverage5`),
combines both hemispheres into one mesh, and writes a compact base64-encoded JSON
payload for embedding directly in
apps/awareness_studio/src/awareness_studio/web/static/vortex_field.html.

This surface is a REAL, standard, published group-average anatomical template. It
is used only as a realistic reference surface for the classical-style heat overlay
in that page -- it is not any ds005620 subject's individual anatomy, and no source
localization is performed anywhere in this pipeline.

Usage:
  python tools/export_fsaverage5_for_vortex_field.py --out /tmp/fsaverage5_pial.json

Then splice the output file's contents into the page's
<script id="vf-brain-data" type="application/json"> block in place of the existing
payload.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import nibabel as nib
import numpy as np


def _load_gii_mesh(path: Path) -> tuple[np.ndarray, np.ndarray]:
    gifti = nib.load(str(path))
    return gifti.darrays[0].data, gifti.darrays[1].data


def _load_gii_scalar(path: Path) -> np.ndarray:
    return nib.load(str(path)).darrays[0].data


def _b64(arr: np.ndarray) -> str:
    return base64.b64encode(arr.tobytes()).decode("ascii")


def build_payload(fsaverage5_dir: Path) -> dict:
    verts_l, faces_l = _load_gii_mesh(fsaverage5_dir / "pial_left.gii.gz")
    verts_r, faces_r = _load_gii_mesh(fsaverage5_dir / "pial_right.gii.gz")
    curv_l = _load_gii_scalar(fsaverage5_dir / "curv_left.gii.gz")
    curv_r = _load_gii_scalar(fsaverage5_dir / "curv_right.gii.gz")

    n_left = verts_l.shape[0]
    verts = np.vstack([verts_l, verts_r]).astype(np.float32)
    faces = np.vstack([faces_l, faces_r + n_left])
    if faces.max() >= 65536:
        raise ValueError(
            f"fsaverage5 has {faces.max() + 1} vertices; a Uint16 index buffer "
            "(max 65536) no longer fits -- widen faces_b64 to Uint32 in both this "
            "script and the page's decoder before using a higher-resolution surface."
        )
    faces = faces.astype(np.uint16)
    curv = np.concatenate([curv_l, curv_r]).astype(np.float32)
    hemi = np.concatenate(
        [np.zeros(n_left, dtype=np.int8), np.ones(verts_r.shape[0], dtype=np.int8)]
    )

    return {
        "n_vertices": int(verts.shape[0]),
        "n_faces": int(faces.shape[0]),
        "n_left": int(n_left),
        # Float32, [x,y,z]*N, FreeSurfer surface RAS mm (+X=Right +Y=Anterior +Z=Superior)
        "vertices_b64": _b64(verts),
        # Uint16, [a,b,c]*N
        "faces_b64": _b64(faces),
        # Float32, real sulcal curvature, one value per vertex
        "curv_b64": _b64(curv),
        # Int8, 0=left hemisphere, 1=right hemisphere
        "hemi_b64": _b64(hemi),
        "source": (
            "nilearn-bundled fsaverage5 (FreeSurfer standard template): "
            "pial surface + curvature"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fsaverage5-dir",
        default=None,
        help=(
            "Directory containing pial_left.gii.gz etc. Defaults to the "
            "nilearn-bundled copy (nilearn.datasets.data.fsaverage5)."
        ),
    )
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    if args.fsaverage5_dir:
        fsaverage5_dir = Path(args.fsaverage5_dir)
    else:
        import nilearn.datasets.data as nilearn_data

        fsaverage5_dir = Path(nilearn_data.__file__).parent / "fsaverage5"

    payload = build_payload(fsaverage5_dir)
    out_path = Path(args.out)
    out_path.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
