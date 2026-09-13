# Local Makefile for the evidence promotion gate (owned-path cycle).
# Does not edit the repository-root Makefile.

PYTHON ?= python3
REPO_ROOT := $(abspath ../..)
FIXTURES := $(REPO_ROOT)/tests/evidence_promotion_gate/fixtures
OUT := $(REPO_ROOT)/outputs/evidence_promotion_gate
VALIDATE := $(REPO_ROOT)/scripts/validate_evidence_promotion.py
GENERATE := $(REPO_ROOT)/scripts/generate_evidence_promotion_report.py

.PHONY: generate validate test compile finite-json smoke cycle preserve-check inventory

generate:
	cd $(REPO_ROOT) && $(PYTHON) $(GENERATE) --input $(FIXTURES) --output $(OUT)

validate:
	cd $(REPO_ROOT) && $(PYTHON) $(VALIDATE) --input $(FIXTURES) --output $(OUT)/validate.json; true

inventory:
	cd $(REPO_ROOT) && $(PYTHON) $(VALIDATE) --input $(FIXTURES) --output $(OUT)/inventory.json; true

test:
	cd $(REPO_ROOT) && $(PYTHON) -m pytest tests/evidence_promotion_gate -q

compile:
	cd $(REPO_ROOT) && $(PYTHON) -m py_compile \
		scripts/validate_evidence_promotion.py \
		scripts/generate_evidence_promotion_report.py \
		tools/evidence_promotion_gate/__init__.py \
		tools/evidence_promotion_gate/schema.py \
		tools/evidence_promotion_gate/adapters.py \
		tools/evidence_promotion_gate/evaluator.py \
		tools/evidence_promotion_gate/fingerprints.py \
		tools/evidence_promotion_gate/reporting.py \
		tools/evidence_promotion_gate/command_center.py \
		tools/evidence_promotion_gate/rag_pack.py

finite-json: generate
	cd $(REPO_ROOT) && $(PYTHON) -c "import json,pathlib; json.loads(pathlib.Path(r'$(OUT)/report.json').read_text(), parse_constant=lambda t: (_ for _ in ()).throw(ValueError(t)))"

preserve-check:
	cd $(REPO_ROOT) && git diff --check -- \
		tools/evidence_promotion_gate \
		scripts/validate_evidence_promotion.py \
		scripts/generate_evidence_promotion_report.py \
		tests/evidence_promotion_gate \
		docs/scientific_falsification/evidence_promotion_gate.md

smoke: compile test

cycle: compile generate validate test finite-json preserve-check
