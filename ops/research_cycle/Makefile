# Research-cycle operator pack local cycle
# Run from this directory or via `make -C ops/research_cycle <target>`.

REPO_ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
PYTHON ?= python3
OUT ?= /tmp/rcop-operator-pack-out
PYTEST := $(PYTHON) -m pytest -q --tb=line tests/ops/research_cycle
SH := $(REPO_ROOT)/scripts/run_research_cycle_audit.sh

.PHONY: help validate-catalog inventory syntax-posix syntax-pwsh test audit-fixtures cycle

help:
	@echo "validate-catalog inventory syntax-posix syntax-pwsh test audit-fixtures cycle"
	@echo "Infrastructure PASS is not a scientific PASS."

validate-catalog:
	cd "$(REPO_ROOT)" && PYTHONPATH="$(REPO_ROOT)" $(PYTHON) -m ops.research_cycle validate-catalog

inventory:
	cd "$(REPO_ROOT)" && PYTHONPATH="$(REPO_ROOT)" $(PYTHON) -m ops.research_cycle inventory --json

syntax-posix:
	bash -n "$(SH)"

syntax-pwsh:
	@if command -v pwsh >/dev/null 2>&1; then \
	  pwsh -NoProfile -Command "$$null = [System.Management.Automation.Language.Parser]::ParseFile('$(REPO_ROOT)/scripts/run_research_cycle_audit.ps1', [ref]$$null, [ref]$$errs); if ($$errs) { $$errs | ForEach-Object { $$_.ToString() }; exit 1 }"; \
	else \
	  echo "pwsh NOT_AVAILABLE; POSIX syntax still checked via syntax-posix"; \
	fi

test:
	cd "$(REPO_ROOT)" && PYTHONPATH="$(REPO_ROOT)" $(PYTEST)

audit-fixtures:
	cd "$(REPO_ROOT)" && PYTHONPATH="$(REPO_ROOT)" $(PYTHON) -m ops.research_cycle audit --output-dir "$(OUT)" --no-surfaces --steps repository_state,schema_validation,research_plan_audit,claim_gate,artifact_manifest,evidence_graph,cache_policy,simulation_campaign,release_evidence,finite_json_no_network

cycle: validate-catalog syntax-posix syntax-pwsh test
	@echo "cycle complete. Infrastructure PASS is not a scientific PASS."
