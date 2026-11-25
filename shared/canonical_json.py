"""Single implementation of the repository's legacy canonical-JSON encoding.

Seventeen modules (benchmark_packs, evidence, job_runner, phase_space, reports, transitions,
workflows) each carried a byte-identical private ``_canonical_json``. Their output feeds content
hashes and record identities, so this helper preserves those bytes exactly:

* keys sorted, compact separators ``(",", ":")``;
* ``ensure_ascii=True`` (json default);
* non-JSON values stringified via ``default=str``;
* json's default ``allow_nan=True``.

Do not change these semantics in place: doing so silently changes every stored hash. New code that
needs strict RFC 8259 output should pass ``strict=True`` (rejects NaN/Infinity and non-JSON types).
"""

from __future__ import annotations

import json
from typing import Any


def canonical_json_text(value: Any, *, strict: bool = False, ensure_ascii: bool = True) -> str:
    """Return sorted-key compact JSON; ``strict`` rejects NaN/Infinity and non-JSON values.

    ``ensure_ascii=False`` keeps non-ASCII characters literal (several strict callers hash
    that form); the default keeps json's ``\\uXXXX`` escaping.
    """
    if strict:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=ensure_ascii
        )
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=ensure_ascii)
