.PHONY: validate-governance test-root test-core test-awareness test-all smoke smoke-core eval-awareness check ds005620-e2e-dry-run ds005620-e2e-mock validate-ds005620-e2e validate-ds005620-e2e-json validate-ds005620-contracts ds005620-e2e-ci github-governance-check ds005620-autonomy-check ds005620-build-manifest ds005620-export-evidence ds005620-paper-skeleton ds005620-inspect-runtime ds005620-preflight ds005620-test-runtime

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

ds005620-e2e-ci:
	python -m governance.validate
	python -m pytest tests/btc_icft/test_ds005620_real_benchmark_executor.py -q
	python -m pytest tests/btc_icft/test_ds005620_e2e_ci_contract.py -q
	$(MAKE) ds005620-e2e-mock
	$(MAKE) validate-ds005620-e2e
	$(MAKE) validate-ds005620-e2e-json
	$(MAKE) validate-ds005620-contracts

ds005620-build-manifest:
	python tools/build_ds005620_artifact_manifest.py --root outputs/btc_icft/ds005620_real_benchmark_execution_mock --out outputs/btc_icft/ds005620_real_benchmark_execution_mock

ds005620-export-evidence:
	python tools/export_ds005620_evidence_packet.py --manifest outputs/btc_icft/ds005620_real_benchmark_execution_mock/artifact_manifest.json --out outputs/btc_icft/ds005620_real_benchmark_execution_mock

ds005620-paper-skeleton:
	python tools/generate_ds005620_paper_skeleton.py --evidence outputs/btc_icft/ds005620_real_benchmark_execution_mock/evidence_packet.json --out outputs/btc_icft/ds005620_real_benchmark_execution_mock

ds005620-inspect-runtime:
	python -m sciencer_d.btc_icft.pipelines.inspect_science_runtime --artifact-root outputs/btc_icft/ds005620_real_benchmark_execution_mock --out outputs/btc_icft/science_runtime_inspection

ds005620-preflight:
	python -m sciencer_d.btc_icft.pipelines.preflight_ds005620_real_local --out outputs/btc_icft/ds005620_real_local_preflight

ds005620-test-runtime:
	python -m pytest tests/btc_icft/test_science_runtime_events.py tests/btc_icft/test_science_runtime_event_log.py tests/btc_icft/test_science_runtime_state.py tests/btc_icft/test_science_task_inventory.py tests/btc_icft/test_science_runtime_snapshots.py tests/btc_icft/test_ds005620_artifact_manifest.py tests/btc_icft/test_ds005620_evidence_packet.py tests/btc_icft/test_ds005620_paper_skeleton.py tests/btc_icft/test_ds005620_real_local_preflight.py -v --tb=short

ds005620-autonomy-check:
	$(MAKE) ds005620-e2e-mock
	$(MAKE) validate-ds005620-e2e
	$(MAKE) validate-ds005620-e2e-json
	$(MAKE) validate-ds005620-contracts
	$(MAKE) ds005620-build-manifest
	$(MAKE) ds005620-export-evidence
	$(MAKE) ds005620-paper-skeleton
	$(MAKE) ds005620-inspect-runtime
	$(MAKE) ds005620-test-runtime

github-governance-check:
	python -m pytest tests/btc_icft/test_github_workflow_governance.py -q
