# Local Makefile for Batch-2 pipeline benchmarks (owned-path cycle).
# Does not edit the repository-root Makefile.

PYTHON ?= python3
REPO_ROOT := $(abspath ../../../)
OUT := $(abspath outputs)
SIZE ?= 16
REPS ?= 1
CLI := $(REPO_ROOT)/scripts/benchmark_batch2_pipeline.py

.PHONY: generate validate test isolated compile cycle inventory smoke preserve-check finite-json

generate:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) generate --out $(OUT) --size $(SIZE) --repetitions $(REPS)

validate:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) validate --root $(OUT)

inventory:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) --json --size $(SIZE) --repetitions $(REPS) --output $(OUT)/inventory_run.json

test:
	cd $(REPO_ROOT) && $(PYTHON) -m pytest tests/benchmarks/batch2_pipeline -q

isolated:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) --isolated --size 12 --repetitions 1 --per-target-timeout-s 30 --json --output $(OUT)/isolated_run.json

compile:
	cd $(REPO_ROOT) && $(PYTHON) -m py_compile \
		scripts/benchmark_batch2_pipeline.py \
		tools/benchmarks/batch2_pipeline/__init__.py \
		tools/benchmarks/batch2_pipeline/schema.py \
		tools/benchmarks/batch2_pipeline/telemetry.py \
		tools/benchmarks/batch2_pipeline/budgets.py \
		tools/benchmarks/batch2_pipeline/fixtures.py \
		tools/benchmarks/batch2_pipeline/workloads.py \
		tools/benchmarks/batch2_pipeline/harness.py \
		tools/benchmarks/batch2_pipeline/reporting.py \
		tools/benchmarks/batch2_pipeline/validator.py

finite-json:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) --json --size 12 --repetitions 1 --output $(OUT)/finite_check.json
	cd $(REPO_ROOT) && $(PYTHON) -c "import json,pathlib; json.loads(pathlib.Path(r'$(OUT)/finite_check.json').read_text(), parse_constant=lambda t: (_ for _ in ()).throw(ValueError(t)))"

preserve-check:
	cd $(REPO_ROOT) && git diff --check -- \
		tools/benchmarks/batch2_pipeline \
		scripts/benchmark_batch2_pipeline.py \
		tests/benchmarks/batch2_pipeline \
		docs/performance/batch2_pipeline_benchmarks.md

smoke: compile test

cycle: compile generate validate test preserve-check
