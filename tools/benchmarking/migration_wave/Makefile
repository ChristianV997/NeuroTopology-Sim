# Local Makefile for migration-wave measurements (owned-path cycle).
# Does not edit the repository-root Makefile.

PYTHON ?= python3
REPO_ROOT := $(abspath ../../../)
OUT := $(abspath outputs)
SIZE ?= 64
REPS ?= 1
CLI := $(REPO_ROOT)/scripts/benchmark_migration_wave.py

.PHONY: generate validate test isolated compile cycle inventory smoke preserve-check finite-json

generate:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) generate --out $(OUT) --size $(SIZE) --repetitions $(REPS)

validate:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) validate --root $(OUT)

inventory:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) --size $(SIZE) --repetitions $(REPS) --output $(OUT)/inventory_run.json

test:
	cd $(REPO_ROOT) && $(PYTHON) -m pytest tests/benchmarking/migration_wave -q

isolated:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) --isolated --size 32 --repetitions 1 --per-target-timeout-s 45 --output $(OUT)/isolated_run.json

compile:
	cd $(REPO_ROOT) && $(PYTHON) -m py_compile \
		scripts/benchmark_migration_wave.py \
		tools/benchmarking/migration_wave/__init__.py \
		tools/benchmarking/migration_wave/schema.py \
		tools/benchmarking/migration_wave/helpers.py \
		tools/benchmarking/migration_wave/variants.py \
		tools/benchmarking/migration_wave/fixtures.py \
		tools/benchmarking/migration_wave/probes.py \
		tools/benchmarking/migration_wave/harness.py \
		tools/benchmarking/migration_wave/reporting.py \
		tools/benchmarking/migration_wave/validator.py

finite-json:
	cd $(REPO_ROOT) && $(PYTHON) $(CLI) --size 32 --repetitions 1 --output $(OUT)/finite_check.json
	cd $(REPO_ROOT) && $(PYTHON) -c "import json,pathlib; json.loads(pathlib.Path(r'$(OUT)/finite_check.json').read_text(), parse_constant=lambda t: (_ for _ in ()).throw(ValueError(t)))"

preserve-check:
	cd $(REPO_ROOT) && git diff --check -- \
		tools/benchmarking/migration_wave \
		scripts/benchmark_migration_wave.py \
		tests/benchmarking/migration_wave \
		docs/performance/migration_wave.md

smoke: compile test

cycle: compile generate validate test preserve-check
