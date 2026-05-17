.PHONY: validate-governance test-root test-core test-awareness test-all smoke smoke-core eval-awareness check ds005620-e2e-dry-run ds005620-e2e-mock validate-ds005620-e2e validate-ds005620-e2e-json validate-ds005620-contracts ds005620-ci-evidence-report ds005620-e2e-ci github-governance-check ontology-governance-docs-check ds005620-autonomy-check ds005620-build-manifest ds005620-export-evidence ds005620-paper-skeleton ds005620-inspect-runtime ds005620-preflight ds005620-test-runtime ds005620-ontology-eval-mock ds005620-ontology-check ds005620-test-ontology ontology-language-check ontology-language-check-strict-outputs ontology-language-baseline-candidate ds005620-generated-language-check ds005620-generated-artifact-check ds005620-real-execution-gate ds005620-real-operator-check ds005620-real-artifact-plan ds005620-real-readiness-loop ds005620-autonomous-iteration ds005620-autonomous-iteration-dry-run real-data-source-matrix multi-dataset-real-readiness multi-dataset-autonomous-iteration multi-dataset-autonomous-iteration-dry-run validate-real-data-source-matrix local-agent-policy-check local-agent-loop-dry-run local-agent-loop-once sync-obsidian local-agent-status local-agent-healthcheck local-agent-scheduler-plan local-ops-healthcheck local-ops-status local-ops-install-plan local-ops-run-once local-ops-run-loop-dry-run local-ops-run-loop

validate-governance:
	python -m governance.validate

test-root:
	python -m pytest tests/ -v --tb=short

test-core: test-root

test-awareness:
	cd apps/awareness_studio && python -m pytest tests/ -v --tb=short

test-all: test-core test-awareness

smoke:
	python main.py --mode synthetic

smoke-core: smoke

eval-awareness:
	cd apps/awareness_studio && python -m awareness_studio.eval_runner --no-llm --quiet

check:
	$(MAKE) validate-governance
	$(MAKE) test-core
	$(MAKE) smoke-core

validate-ds005620-artifacts:
	python tools/validate_ds005620_artifacts.py --root outputs/btc_icft/ds005620

validate-ds005620-mt-real:
	python tools/validate_ds005620_artifacts.py --root outputs/btc_icft/ds005620 --stage mt_real

validate-eeg-signal-artifacts:
	python tools/validate_eeg_signal_artifacts.py --root outputs/btc_icft --dataset-id DS005620

smoke-eeg-signal-pipeline:
	python tools/run_eeg_signal_pipeline_smoke.py --dataset-id DS005620 --root outputs/btc_icft --validate

ds005620-e2e-dry-run:
	python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark --out outputs/btc_icft/ds005620_real_benchmark_execution

ds005620-e2e-mock:
	python -m sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark --mock-e2e --execute --peer-reviewed-contract-confirmed --out outputs/btc_icft/ds005620_real_benchmark_execution_mock

validate-ds005620-e2e:
	python tools/validate_ds005620_e2e_execution.py --root outputs/btc_icft/ds005620_real_benchmark_execution_mock

validate-ds005620-e2e-json:
	python tools/validate_ds005620_e2e_execution.py --root outputs/btc_icft/ds005620_real_benchmark_execution_mock --json-out outputs/btc_icft/ds005620_real_benchmark_execution_mock/validation_summary.json

validate-ds005620-contracts:
	python tools/validate_ds005620_contracts.py --root outputs/btc_icft/ds005620_real_benchmark_execution_mock --validation-summary outputs/btc_icft/ds005620_real_benchmark_execution_mock/validation_summary.json



ds005620-ci-evidence-report:
	python tools/build_ds005620_ci_evidence_report.py --root outputs/btc_icft/ds005620_real_benchmark_execution_mock --validation-summary outputs/btc_icft/ds005620_real_benchmark_execution_mock/validation_summary.json --contract-summary outputs/btc_icft/ds005620_real_benchmark_execution_mock/contract_validation_summary.json --json-out outputs/btc_icft/ds005620_real_benchmark_execution_mock/ci_evidence_report.json --markdown-out outputs/btc_icft/ds005620_real_benchmark_execution_mock/ci_evidence_report.md

ds005620-e2e-ci:
	python -m governance.validate
	python -m pytest tests/btc_icft/test_ds005620_real_benchmark_executor.py -q
	python -m pytest tests/btc_icft/test_ds005620_e2e_ci_contract.py -q
	$(MAKE) ds005620-e2e-mock
	$(MAKE) validate-ds005620-e2e
	$(MAKE) validate-ds005620-e2e-json
	$(MAKE) validate-ds005620-contracts
	$(MAKE) ds005620-ci-evidence-report

ds005620-build-manifest:
	python tools/build_ds005620_artifact_manifest.py --root outputs/btc_icft/ds005620_real_benchmark_execution_mock --out outputs/btc_icft/ds005620_real_benchmark_execution_mock

ds005620-export-evidence:
	python tools/export_ds005620_evidence_packet.py --manifest outputs/btc_icft/ds005620_real_benchmark_execution_mock/artifact_manifest.json --out outputs/btc_icft/ds005620_real_benchmark_execution_mock --ontology-root outputs/btc_icft/ds005620_ontology_evaluation_mock

ds005620-paper-skeleton:
	python tools/generate_ds005620_paper_skeleton.py --evidence outputs/btc_icft/ds005620_real_benchmark_execution_mock/evidence_packet.json --out outputs/btc_icft/ds005620_real_benchmark_execution_mock --ontology-root outputs/btc_icft/ds005620_ontology_evaluation_mock

ds005620-inspect-runtime:
	python -m sciencer_d.btc_icft.pipelines.inspect_science_runtime --artifact-root outputs/btc_icft/ds005620_real_benchmark_execution_mock --out outputs/btc_icft/science_runtime_inspection

ds005620-preflight:
	python -m sciencer_d.btc_icft.pipelines.preflight_ds005620_real_local --out outputs/btc_icft/ds005620_real_local_preflight; true

ds005620-real-execution-gate:
	python -m sciencer_d.btc_icft.pipelines.prepare_ds005620_real_local_execution --out outputs/btc_icft/ds005620_real_execution_gate

ds005620-real-operator-check:
	$(MAKE) ds005620-preflight
	$(MAKE) ds005620-real-execution-gate

ds005620-test-runtime:
	python -m pytest tests/btc_icft/test_science_runtime_events.py tests/btc_icft/test_science_runtime_event_log.py tests/btc_icft/test_science_runtime_state.py tests/btc_icft/test_science_task_inventory.py tests/btc_icft/test_science_runtime_snapshots.py tests/btc_icft/test_ds005620_artifact_manifest.py tests/btc_icft/test_ds005620_evidence_packet.py tests/btc_icft/test_ds005620_paper_skeleton.py tests/btc_icft/test_ds005620_real_local_preflight.py -v --tb=short

ds005620-autonomy-check:
	$(MAKE) ds005620-e2e-mock
	$(MAKE) validate-ds005620-e2e
	$(MAKE) validate-ds005620-e2e-json
	$(MAKE) validate-ds005620-contracts
	$(MAKE) ds005620-ci-evidence-report
	$(MAKE) ds005620-build-manifest
	$(MAKE) ds005620-ontology-eval-mock
	$(MAKE) ds005620-export-evidence
	$(MAKE) ds005620-paper-skeleton
	$(MAKE) ds005620-inspect-runtime
	$(MAKE) ds005620-test-runtime
	$(MAKE) ds005620-generated-language-check

ds005620-ontology-eval-mock:
	python -m sciencer_d.btc_icft.pipelines.evaluate_ds005620_ontology_claims --execution-root outputs/btc_icft/ds005620_real_benchmark_execution_mock --out outputs/btc_icft/ds005620_ontology_evaluation_mock

ds005620-ontology-check:
	$(MAKE) ds005620-e2e-mock
	$(MAKE) ds005620-build-manifest
	$(MAKE) ds005620-ontology-eval-mock
	$(MAKE) ds005620-export-evidence
	$(MAKE) ds005620-paper-skeleton

ds005620-test-ontology:
	python -m pytest tests/btc_icft/test_ontology_schema.py tests/btc_icft/test_ontology_safe_language.py tests/btc_icft/test_ontology_bridge_registry.py tests/btc_icft/test_ontology_evidence_matrix.py tests/btc_icft/test_ds005620_ontology_evaluator.py -v --tb=short

github-governance-check:
	python -m pytest tests/btc_icft/test_github_workflow_governance.py -q

ontology-governance-docs-check:
	python -m pytest tests/btc_icft/test_ontology_review_governance_docs.py -q

ontology-language-check:
	python tools/validate_ontology_claim_language.py --root . --scan-mode repo --baseline contracts/btc_icft/ontology_claims/claim_language_baseline.json --json-out outputs/btc_icft/ontology_claim_language_validation.json --markdown-out outputs/btc_icft/ontology_claim_language_validation.md

ontology-language-check-strict-outputs:
	python tools/validate_ontology_claim_language.py --root . --scan-mode outputs --strict-outputs --no-baseline --json-out outputs/btc_icft/ontology_claim_language_validation_strict_outputs.json --markdown-out outputs/btc_icft/ontology_claim_language_validation_strict_outputs.md

ontology-language-baseline-candidate:
	python tools/validate_ontology_claim_language.py --root . --scan-mode repo --no-baseline --write-baseline outputs/btc_icft/claim_language_baseline_candidate.json --json-out outputs/btc_icft/ontology_claim_language_validation_unbaselined.json --markdown-out outputs/btc_icft/ontology_claim_language_validation_unbaselined.md || true


ds005620-generated-language-check:
	python tools/validate_ds005620_generated_language.py --root . --json-out outputs/btc_icft/ds005620_generated_language_validation.json --markdown-out outputs/btc_icft/ds005620_generated_language_validation.md

ds005620-generated-artifact-check:
	$(MAKE) ds005620-e2e-mock
	$(MAKE) validate-ds005620-e2e-json
	$(MAKE) validate-ds005620-contracts
	$(MAKE) ds005620-build-manifest
	$(MAKE) ds005620-ontology-eval-mock
	$(MAKE) ds005620-export-evidence
	$(MAKE) ds005620-paper-skeleton
	$(MAKE) ds005620-ci-evidence-report
	$(MAKE) ds005620-generated-language-check

ds005620-real-artifact-plan:
	python -m sciencer_d.btc_icft.pipelines.plan_ds005620_real_artifacts --out outputs/btc_icft/ds005620_real_artifact_operator

ds005620-real-readiness-loop:
	$(MAKE) ds005620-real-artifact-plan
	$(MAKE) ds005620-real-execution-gate

ds005620-autonomous-iteration:
	python -m sciencer_d.btc_icft.pipelines.run_ds005620_autonomous_iteration --out outputs/btc_icft/ds005620_autonomous_iteration

ds005620-autonomous-iteration-dry-run:
	python -m sciencer_d.btc_icft.pipelines.run_ds005620_autonomous_iteration --dry-run --out outputs/btc_icft/ds005620_autonomous_iteration

real-data-source-matrix:
	python -m sciencer_d.btc_icft.pipelines.plan_multi_dataset_real_execution --out outputs/btc_icft/multi_dataset_real_execution

multi-dataset-real-readiness:
	$(MAKE) real-data-source-matrix
	$(MAKE) ds005620-real-artifact-plan
	$(MAKE) ds005620-real-execution-gate

multi-dataset-autonomous-iteration:
	python -m sciencer_d.btc_icft.pipelines.run_multi_dataset_autonomous_iteration --out outputs/btc_icft/multi_dataset_autonomous_iteration

multi-dataset-autonomous-iteration-dry-run:
	python -m sciencer_d.btc_icft.pipelines.run_multi_dataset_autonomous_iteration --dry-run --out outputs/btc_icft/multi_dataset_autonomous_iteration

validate-real-data-source-matrix:
	python tools/validate_multi_dataset_real_execution_matrix.py --root outputs/btc_icft/multi_dataset_real_execution

local-agent-policy-check:
	python -m tools.local_agents.command_guard --policy configs/local_agents/command_policy.json --check-defaults --json-out outputs/local_agents/policy_check.json

local-agent-loop-dry-run:
	python -m tools.local_agents.research_loop --dry-run --out outputs/local_agents --vault $(if $(VAULT),$(VAULT),obsidian)

local-agent-loop-once:
	python -m tools.local_agents.research_loop --once --out outputs/local_agents --vault $(if $(VAULT),$(VAULT),obsidian)

sync-obsidian:
	python -m tools.local_agents.obsidian_sync --root outputs/btc_icft --vault $(if $(VAULT),$(VAULT),obsidian) --out outputs/local_agents/obsidian_sync_result.json

local-agent-status:
	python -m tools.local_agents.status --root outputs/btc_icft --local-agent-root outputs/local_agents --out outputs/local_agents/local_agent_status.json

local-agent-healthcheck:
	python -m tools.local_agents.healthcheck --root outputs/btc_icft --local-agent-root outputs/local_agents --out outputs/local_agents/local_agent_healthcheck.json

local-agent-scheduler-plan:
	python -m tools.local_agents.scheduler_plan --out outputs/local_agents

local-ops-healthcheck:
	python -m tools.local_ops.healthcheck --out outputs/local_ops/local_ops_healthcheck.json --output-root outputs/local_ops --local-agent-root outputs/local_agents --vault $(if $(VAULT),$(VAULT),obsidian)

local-ops-status:
	python -m tools.local_ops.status --out outputs/local_ops/local_ops_status.json --output-root outputs/local_ops --local-agent-root outputs/local_agents --btc-root outputs/btc_icft

local-ops-install-plan:
	python -m tools.local_ops.install_plan --out outputs/local_ops

local-ops-run-once:
	python -m tools.local_ops.runner --mode once --out outputs/local_ops --local-agent-root outputs/local_agents --vault $(if $(VAULT),$(VAULT),obsidian)

local-ops-run-loop-dry-run:
	python -m tools.local_ops.runner --mode dry-run --out outputs/local_ops --local-agent-root outputs/local_agents --vault $(if $(VAULT),$(VAULT),obsidian)

local-ops-run-loop:
	python -m tools.local_ops.runner --mode loop --max-iterations $(if $(MAX_ITERATIONS),$(MAX_ITERATIONS),3) --interval-seconds $(if $(INTERVAL_SECONDS),$(INTERVAL_SECONDS),1800) --out outputs/local_ops --local-agent-root outputs/local_agents --vault $(if $(VAULT),$(VAULT),obsidian)


tol-digest:
	python -m tools.tol_digest.report_writer --input inputs/tol --out outputs/tol_digest

validate-tol-digest:
	python -m tools.tol_digest.validator --root outputs/tol_digest --json-out outputs/tol_digest/tol_digest_validation.json

tol-sync-obsidian:
	python -m tools.tol_digest.obsidian_sync --root outputs/tol_digest --vault $(if $(VAULT),$(VAULT),obsidian) --out outputs/tol_digest/tol_obsidian_sync_result.json

tol-digest-cycle:
	$(MAKE) tol-digest
	$(MAKE) validate-tol-digest
	$(MAKE) tol-sync-obsidian
	$(MAKE) ontology-language-check

tol-book-spine:
	python -m tools.tol_digest.book_spine --root outputs/tol_digest --out outputs/tol_digest

tol-research-roadmap:
	python -m tools.tol_digest.research_roadmap --root outputs/tol_digest --out outputs/tol_digest

tol-public-language-guide:
	python -m tools.tol_digest.public_language_guide --root outputs/tol_digest --out outputs/tol_digest/public_language_rewrite_guide.md

validate-tol-synthesis:
	python -m tools.tol_digest.synthesis_validator --root outputs/tol_digest --json-out outputs/tol_digest/tol_synthesis_validation.json

tol-synthesis-cycle:
	$(MAKE) tol-digest
	-$(MAKE) tol-digest-strict-check
	-$(MAKE) tol-digest-safety-report
	$(MAKE) validate-tol-digest
	$(MAKE) tol-book-spine
	$(MAKE) tol-research-roadmap
	$(MAKE) tol-public-language-guide
	$(MAKE) validate-tol-synthesis
	$(MAKE) tol-sync-obsidian
	$(MAKE) ontology-language-check
	$(MAKE) ds005620-generated-language-check
