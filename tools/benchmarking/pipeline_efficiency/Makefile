# Local Makefile for pipeline-efficiency (owned-path cycle).
# Does not edit the repository-root Makefile.

PYTHON ?= python3
REPO_ROOT := $(abspath ../../../)
OUT := $(abspath outputs)
SIZE ?= 24
REPS ?= 1
CLI := $(REPO_ROOT)/scripts/benchmark_pipeline_efficiency.py

.PHONY: generate validate test isolated compile cycle inventory smoke preserve-check finite-json

generate:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) generate --out $(OUT) --size $(SIZE) --repetitions $(REPS)

validate:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) validate --root $(OUT)

inventory:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) --json --size $(SIZE) --repetitions $(REPS) --output $(OUT)/inventory_run.json

test:
	cd $(REPO_ROOT) && $(PYTHON) -m pytest tests/benchmarking/pipeline_efficiency -q

isolated:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) --isolated --size 12 --repetitions 1 --per-target-timeout-s 30 --json --output $(OUT)/isolated_run.json

compile:
	cd $(REPO_ROOT) && $(PYTHON) -m py_compile \
		scripts/benchmark_pipeline_efficiency.py \
		tools/benchmarking/pipeline_efficiency/__init__.py \
		tools/benchmarking/pipeline_efficiency/schema.py \
		tools/benchmarking/pipeline_efficiency/telemetry.py \
		tools/benchmarking/pipeline_efficiency/budgets.py \
		tools/benchmarking/pipeline_efficiency/fixtures.py \
		tools/benchmarking/pipeline_efficiency/adapters.py \
		tools/benchmarking/pipeline_efficiency/workloads.py \
		tools/benchmarking/pipeline_efficiency/harness.py \
		tools/benchmarking/pipeline_efficiency/reporting.py \
		tools/benchmarking/pipeline_efficiency/validator.py

finite-json:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) --json --size 12 --repetitions 1 --output $(OUT)/finite_check.json
	cd $(REPO_ROOT) && $(PYTHON) -c "import json,pathlib; json.loads(pathlib.Path(r'$(OUT)/finite_check.json').read_text(), parse_constant=lambda t: (_ for _ in ()).throw(ValueError(t)))"

preserve-check:
	cd $(REPO_ROOT) && git diff --check -- \
		tools/benchmarking/pipeline_efficiency \
		scripts/benchmark_pipeline_efficiency.py \
		tests/benchmarking/pipeline_efficiency \
		docs/performance/pipeline_efficiency.md

smoke: compile test

cycle: compile generate validate test preserve-check
