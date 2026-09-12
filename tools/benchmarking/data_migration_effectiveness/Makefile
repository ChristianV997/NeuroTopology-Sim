# Local Makefile for data-migration-effectiveness (owned-path cycle).
# Does not edit the repository-root Makefile.

PYTHON ?= python3
REPO_ROOT := $(abspath ../../../)
OUT := $(abspath outputs)
SIZE ?= 64
REPS ?= 1
CLI := $(REPO_ROOT)/scripts/benchmark_data_migration_effectiveness.py

.PHONY: generate validate test isolated compile cycle inventory smoke preserve-check finite-json

generate:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) generate --output $(OUT) --size $(SIZE) --repetitions $(REPS)

validate:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) validate --output $(OUT)

inventory:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) --json-stdout --size $(SIZE) --repetitions $(REPS) --output $(OUT)/inventory_run

test:
	cd $(REPO_ROOT) && $(PYTHON) -m pytest tests/benchmarking/data_migration_effectiveness -q

isolated:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) --isolated --size 32 --repetitions 1 --per-target-timeout-s 30 --json-stdout --output $(OUT)/isolated_run

compile:
	cd $(REPO_ROOT) && $(PYTHON) -m py_compile \
		scripts/benchmark_data_migration_effectiveness.py \
		tools/benchmarking/data_migration_effectiveness/__init__.py \
		tools/benchmarking/data_migration_effectiveness/schema.py \
		tools/benchmarking/data_migration_effectiveness/telemetry.py \
		tools/benchmarking/data_migration_effectiveness/budgets.py \
		tools/benchmarking/data_migration_effectiveness/fixtures.py \
		tools/benchmarking/data_migration_effectiveness/workloads.py \
		tools/benchmarking/data_migration_effectiveness/harness.py \
		tools/benchmarking/data_migration_effectiveness/report.py \
		tools/benchmarking/data_migration_effectiveness/validator.py

finite-json:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) --json-stdout --size 32 --repetitions 1 --output $(OUT)/finite_check
	cd $(REPO_ROOT) && $(PYTHON) -c "import json,pathlib; json.loads(pathlib.Path(r'$(OUT)/finite_check/data_migration_effectiveness.json').read_text(), parse_constant=lambda t: (_ for _ in ()).throw(ValueError(t)))"

preserve-check:
	cd $(REPO_ROOT) && git diff --check -- \
		tools/benchmarking/data_migration_effectiveness \
		scripts/benchmark_data_migration_effectiveness.py \
		tests/benchmarking/data_migration_effectiveness \
		docs/performance/data_migration_effectiveness.md

smoke: compile test

cycle: compile generate validate test preserve-check
