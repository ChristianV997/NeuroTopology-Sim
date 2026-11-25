# Notice for mne_code_path below. Its operations are those of MNE-Python 1.13.2 (mne/preprocessing/_csd.py and
# mne/channels/interpolation.py, from the pinned sdist). That source is Copyright 2011-2025 MNE-Python authors and is
# licensed under BSD-3-Clause. The licence text is reproduced here, as it requires for source copies:
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the
# following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following
#    disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the
#    following disclaimer in the documentation and/or other materials provided with the distribution.
# 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote
#    products derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from __future__ import annotations

import socket
from typing import Any

import numpy as np
import pytest
from numpy.polynomial.legendre import legval


def mne_code_path(pos: np.ndarray, radius: float, lambda2: float) -> tuple[np.ndarray, np.ndarray]:
    """Transcription of MNE 1.13.2 compute_current_source_density (NOT executed MNE output).

    Sources, from the sdist whose SHA-256 is pinned in tools/mne_csd_reference_audit/pin.py:
    mne/preprocessing/_csd.py lines 26-50 (_prepare_G, _compute_csd), line 158 (zero-position refusal),
    and mne/channels/interpolation.py lines 20-37 (_calc_h), 40-62 (_calc_g).

    Written with numpy.polynomial.legendre.legval and not via the package, so the package is compared against a
    second implementation of the same code path, including the TC = Gi.sum(0) ordering that the package's projection
    form does not use. It is not an independent derivation: a misreading shared with the source would pass here.
    Returns the operator and the regularised G, so callers can bound the error by its conditioning.
    """
    u = pos / np.linalg.norm(pos, axis=1, keepdims=True)
    cos = np.clip(u @ u.T, -1, 1)
    g = [0.0] + [(2 * n + 1) / (n**4 * (n + 1) ** 4 * 4 * np.pi) for n in range(1, 51)]
    h = [0.0] + [(2 * n + 1) / (n**3 * (n + 1) ** 3 * 4 * np.pi) for n in range(1, 51)]
    G = legval(cos, g)
    H = legval(cos, h)
    G.flat[:: len(G) + 1] += lambda2
    Gi = np.linalg.inv(G)
    TC = Gi.sum(0)
    sgi = np.sum(TC)
    n = G.shape[0]
    Z = np.eye(n) - np.eye(n).mean(0)
    Cp2 = np.dot(Gi, Z)
    c02 = np.sum(Cp2, axis=0) / sgi
    C2 = Cp2 - np.dot(TC[:, np.newaxis], c02[np.newaxis, :])
    return (np.dot(C2.T, H).T / radius**2), G


@pytest.fixture(scope="session")
def mne_code_path_oracle():
    return mne_code_path


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network access attempted by the MNE CSD reference audit")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
