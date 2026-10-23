"""Pinned MNE-Python source used as the reference for this audit.

Provenance and its status:
- version, sdist filename and SHA-256: PyPI JSON for mne 1.13.2, recorded in the original audit
  (2026-10-17). Re-verified 2026-10-19 against https://pypi.org/pypi/mne/1.13.2/json, which gives the
  sdist digest 729829e35010a7273cce8608d61d930c973fbead6edc1a70316c01e3a5551521.
- tag commit: `git ls-remote` of refs/tags/v1.13.2 on mne-tools/mne-python, verified against the live tag on 2026-10-23; it resolves to `bf67729b805865b5bb0f2f97621e416278efd1b2`.

- source-file SHA-256 values: computed from the extracted sdist members. Re-verified 2026-10-19 from a
  fresh extraction of the same sdist.

The reference implementation here was written from the mathematical formulas; no MNE code is copied into
this package. The MNE code-path transcription in tests/mne_csd_reference_audit/conftest.py is test-only. It is
a near-literal copy of the pinned BSD-3-Clause operations, and it carries MNE's copyright notice and licence text.
It is cited to the same source lines.
"""
from __future__ import annotations

MNE_VERSION = "1.13.2"
MNE_TAG = "v1.13.2"
MNE_TAG_COMMIT = "bf67729b805865b5bb0f2f97621e416278efd1b2"
MNE_SDIST_FILENAME = "mne-1.13.2.tar.gz"
MNE_SDIST_SHA256 = "729829e35010a7273cce8608d61d930c973fbead6edc1a70316c01e3a5551521"
MNE_LICENSE = "BSD-3-Clause"
MNE_SOURCE_REPOSITORY = "https://github.com/mne-tools/mne-python"
MNE_SOURCE_FILES = {
    "mne/channels/interpolation.py": "bcb8b47e34eaa7fe002484662882e9fb5cf64d54c18e92611a2d1e9fd44936cd",
    "mne/preprocessing/_csd.py": "a77c8b02cf4f2465a43f994bf4dd1efdc7250ca274957f7b77af37057f51541f",
}
MNE_PYPI_JSON = "https://pypi.org/pypi/mne/1.13.2/json"
MNE_DEFAULTS = {"stiffness": 4, "n_legendre_terms": 50, "lambda2": 1e-5, "sphere": "auto"}
