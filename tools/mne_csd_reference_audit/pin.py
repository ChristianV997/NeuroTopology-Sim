"""Pinned MNE-Python source used as the reference for this audit.

Every value here was verified in the audit session:
- version, sdist filename and SHA-256: PyPI JSON for mne 1.13.2; the downloaded
  sdist's SHA-256 matched the PyPI digest exactly.
- tag commit: `git ls-remote` of refs/tags/v1.13.2 on mne-tools/mne-python.
- source-file SHA-256 values: computed from the extracted sdist members.

The reference implementation here was written from the mathematical
formulas. No MNE code is copied into this package.
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
