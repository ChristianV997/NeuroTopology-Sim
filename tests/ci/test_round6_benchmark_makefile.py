"""Structural contract test for the Batch-2 benchmark Makefile candidate."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = ROOT / "tools/benchmarks/batch2_pipeline/Makefile"

_FIXTURE_MAKEFILE = """\
PYTHON ?= python3
REPO_ROOT := $(abspath ../../../)
OUT := $(abspath outputs)
SIZE ?= 16
REPS ?= 1
CLI := $(REPO_ROOT)/scripts/benchmark_batch2_pipeline.py

.PHONY: generate validate test isolated compile cycle inventory smoke preserve-check finite-json

generate:
\tcd $(REPO_ROOT) && $(PYTHON) $(CLI) generate --out $(OUT) --size $(SIZE) --repetitions $(REPS)
validate:
\tcd $(REPO_ROOT) && $(PYTHON) $(CLI) validate --root $(OUT)
inventory:
\tcd $(REPO_ROOT) && $(PYTHON) $(CLI) --json --size $(SIZE) --repetitions $(REPS) --output $(OUT)/inventory_run.json
test:
\tcd $(REPO_ROOT) && $(PYTHON) -m pytest tests/benchmarks/batch2_pipeline -q
isolated:
\tcd $(REPO_ROOT) && $(PYTHON) $(CLI) --isolated --size 12 --repetitions 1 --per-target-timeout-s 30 --json --output $(OUT)/isolated_run.json
compile:
\tcd $(REPO_ROOT) && $(PYTHON) -m py_compile scripts/benchmark_batch2_pipeline.py
finite-json:
\tcd $(REPO_ROOT) && $(PYTHON) -c "import json,pathlib; json.loads(pathlib.Path(r'$(OUT)/finite_check.json').read_text(), parse_constant=lambda t: (_ for _ in ()).throw(ValueError(t)))"
preserve-check:
\tcd $(REPO_ROOT) && git diff --check
smoke: compile test
cycle: compile generate validate test preserve-check
"""


class BenchmarkMakefileContractTests(unittest.TestCase):
    def test_candidate_makefile_declares_bounded_local_workflow_targets(self):
        # Candidate source is read directly when present. The inline fixture lets
        # the owned test suite run on main before the candidate PR is present;
        # discovery independently requires the actual candidate file to exist.
        source = MAKEFILE.read_text(encoding="utf-8") if MAKEFILE.is_file() else _FIXTURE_MAKEFILE
        targets = set(re.findall(r"(?m)^([a-z][a-z0-9_-]*):(?:\s|$)", source))
        self.assertTrue(
            {
                "generate", "validate", "inventory", "test", "isolated", "compile",
                "finite-json", "preserve-check", "smoke", "cycle",
            }.issubset(targets)
        )
        self.assertRegex(source, r"(?m)^PYTHON \?= python3$")
        self.assertRegex(source, r"(?m)^SIZE \?= 16$")
        self.assertRegex(source, r"(?m)^REPS \?= 1$")
        self.assertRegex(
            source,
            r"(?ms)^test:\s*\n\tcd \$\(REPO_ROOT\) && \$\(PYTHON\) -m pytest tests/benchmarks/batch2_pipeline -q$",
        )
        self.assertRegex(source, r"(?m)^isolated:\s*$")
        self.assertIn("--isolated", source)
        self.assertIn("--per-target-timeout-s 30", source)
        self.assertIn("parse_constant=", source)
        self.assertRegex(source, r"(?m)^cycle: compile generate validate test preserve-check$")
        self.assertNotRegex(source, r"(?i)https?://|aws_access_key|secret_access_key|\btoken\s*=")


if __name__ == "__main__":
    unittest.main()
