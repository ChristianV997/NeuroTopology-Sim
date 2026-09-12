# Local Makefile for post-merge pipeline measurements (owned-path cycle).
# Does not edit the repository-root Makefile.

PYTHON ?= python3
REPO_ROOT := $(abspath ../../../)
OUT := $(abspath outputs)
SIZE ?= 16
REPS ?= 1
CLI := $(REPO_ROOT)/scripts/benchmark_post_merge_pipeline.py

.PHONY: generate validate test isolated compile cycle inventory smoke preserve-check finite-json

generate:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) generate --out $(OUT) --size $(SIZE) --repetitions $(REPS)

validate:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) validate --root $(OUT)

inventory:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) --json --size $(SIZE) --repetitions $(REPS) --output $(OUT)/inventory_run.json

test:
	cd $(REPO_ROOT) && $(PYTHON) -m pytest tests/benchmarking/post_merge_pipeline -q

isolated:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) --isolated --size 8 --repetitions 1 --per-target-timeout-s 45 --json --output $(OUT)/isolated_run.json

compile:
	cd $(REPO_ROOT) && $(PYTHON) -m py_compile \
		scripts/benchmark_post_merge_pipeline.py \
		tools/benchmarking/post_merge_pipeline/__init__.py \
		tools/benchmarking/post_merge_pipeline/schema.py \
		tools/benchmarking/post_merge_pipeline/adapters.py \
		tools/benchmarking/post_merge_pipeline/fixtures.py \
		tools/benchmarking/post_merge_pipeline/workloads.py \
		tools/benchmarking/post_merge_pipeline/harness.py \
		tools/benchmarking/post_merge_pipeline/streaming_compare.py \
		tools/benchmarking/post_merge_pipeline/reporting.py \
		tools/benchmarking/post_merge_pipeline/validator.py

finite-json:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) --json --size 8 --repetitions 1 --output $(OUT)/finite_check.json
	cd $(REPO_ROOT) && $(PYTHON) -c "import json,pathlib; json.loads(pathlib.Path(r'$(OUT)/finite_check.json').read_text(), parse_constant=lambda t: (_ for _ in ()).throw(ValueError(t)))"

preserve-check:
	cd $(REPO_ROOT) && git diff --check -- \
		tools/benchmarking/post_merge_pipeline \
		scripts/benchmark_post_merge_pipeline.py \
		tests/benchmarking/post_merge_pipeline \
		docs/performance/post_merge_pipeline.md

smoke: compile test

cycle: compile generate validate test preserve-check
