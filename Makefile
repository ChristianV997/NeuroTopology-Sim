.PHONY: validate-governance test-root test-core test-awareness test-all smoke smoke-core eval-awareness check ds005620-e2e-dry-run ds005620-e2e-mock validate-ds005620-e2e validate-ds005620-e2e-json validate-ds005620-contracts ds005620-ci-evidence-report ds005620-e2e-ci github-governance-check ontology-governance-docs-check ds005620-autonomy-check ds005620-build-manifest ds005620-export-evidence ds005620-paper-skeleton ds005620-inspect-runtime ds005620-preflight ds005620-test-runtime ds005620-ontology-eval-mock ds005620-ontology-check ds005620-test-ontology ontology-language-check ontology-language-check-strict-outputs ontology-language-baseline-candidate ds005620-generated-language-check ds005620-generated-artifact-check ds005620-real-execution-gate ds005620-real-operator-check ds005620-real-artifact-plan ds005620-real-readiness-loop ds005620-autonomous-iteration ds005620-autonomous-iteration-dry-run real-data-source-matrix multi-dataset-real-readiness multi-dataset-autonomous-iteration multi-dataset-autonomous-iteration-dry-run validate-real-data-source-matrix local-agent-policy-check local-agent-loop-dry-run local-agent-loop-once sync-obsidian local-agent-status local-agent-healthcheck local-agent-scheduler-plan local-ops-healthcheck local-ops-status local-ops-install-plan local-ops-run-once local-ops-run-loop-dry-run local-ops-run-loop laptop-setup-plan laptop-setup-doctor laptop-smoke laptop-smoke-dry-run laptop-troubleshoot-report laptop-safe-run openai-rag-policy-check openai-rag-manifest openai-rag-dry-run-sync openai-rag-query-mock openai-rag-api-smoke openai-rag-sync openai-rag-query

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
	$(MAKE) ds005620-generated-language-check || true

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
	$(MAKE) ds005620-generated-language-check || true

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
	$(MAKE) ontology-language-check || true

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
	$(MAKE) ontology-language-check || true
	$(MAKE) ds005620-generated-language-check || true


laptop-setup-plan:
	python -m tools.local_setup.setup_plan --out outputs/local_setup/setup_plan.json --markdown-out outputs/local_setup/setup_plan.md

laptop-setup-doctor:
	python -m tools.local_setup.env_probe --out outputs/local_setup/environment_report.json --markdown-out outputs/local_setup/environment_report.md

laptop-smoke:
	python -m tools.local_setup.smoke_runner --mode run --out outputs/local_setup/smoke_results.json --markdown-out outputs/local_setup/smoke_results.md

laptop-smoke-dry-run:
	python -m tools.local_setup.smoke_runner --mode dry-run --out outputs/local_setup/smoke_results.json --markdown-out outputs/local_setup/smoke_results.md

laptop-troubleshoot-report:
	python -m tools.local_setup.troubleshoot --env outputs/local_setup/environment_report.json --smoke outputs/local_setup/smoke_results.json --markdown-out outputs/local_setup/troubleshoot_report.md

laptop-safe-run:
	$(MAKE) laptop-setup-doctor
	$(MAKE) laptop-smoke-dry-run
	$(MAKE) local-agent-healthcheck
	$(MAKE) local-ops-healthcheck
	$(MAKE) local-ops-run-loop-dry-run

openai-rag-policy-check:
	python -m tools.openai_rag.policy --policy configs/openai_rag/rag_policy.json --json-out outputs/openai_rag/rag_policy_check.json

openai-rag-manifest:
	python -m tools.openai_rag.artifact_manifest --config configs/openai_rag/artifact_sources.json --out outputs/openai_rag

openai-rag-dry-run-sync:
	$(MAKE) openai-rag-policy-check
	$(MAKE) openai-rag-manifest
	python -m tools.openai_rag.sync_plan --manifest outputs/openai_rag/artifact_manifest.json --out outputs/openai_rag --mode dry_run

openai-rag-query-mock:
	$(MAKE) openai-rag-manifest
	python -m tools.openai_rag.query_client --query "Summarize current ScienceR-Dsim system state." --mode mock --out outputs/openai_rag/query_mock_response.json

openai-rag-api-smoke:
	python -m api.rag_server --smoke-test

openai-rag-sync:
	python -m tools.openai_rag.sync_plan --manifest outputs/openai_rag/artifact_manifest.json --out outputs/openai_rag --mode live --live --confirm-upload

openai-rag-query:
	python -m tools.openai_rag.query_client --query "$(QUERY)" --mode live --live --vector-store-id "$(VECTOR_STORE_ID)" --out outputs/openai_rag/query_live_response.json

command-center-status:
	python -m tools.command_center.status_adapter --out outputs/command_center/command_center_status.json

command-center-mock-payloads:
	python -m tools.command_center.mock_payloads --out outputs/command_center/mock_payloads

command-center-openapi:
	python -m tools.command_center.openapi_builder --out outputs/command_center/openapi.json

command-center-frontend-pack:
	python -m tools.command_center.frontend_pack --out outputs/command_center

command-center-guardrails-status:
	python -m tools.command_center.guardrails_status --out outputs/command_center/mock_payloads/guardrails_status.json

command-center-api-smoke:
	python -m api.rag_server --smoke-test
	$(MAKE) command-center-status
	$(MAKE) command-center-mock-payloads
	$(MAKE) command-center-openapi
	$(MAKE) command-center-frontend-pack
	$(MAKE) command-center-guardrails-status

.PHONY: mental-health-bridge validate-mental-health-bridge mental-health-bridge-sync-obsidian mental-health-bridge-command-center-payloads mental-health-bridge-cycle

mental-health-bridge:
	python -m tools.tol_digest.mental_health_bridge.generator --root outputs/tol_digest --out outputs/tol_digest/mental_health_bridge

validate-mental-health-bridge:
	python -m tools.tol_digest.mental_health_bridge.validator --root outputs/tol_digest/mental_health_bridge --json-out outputs/tol_digest/mental_health_bridge/mental_health_bridge_validation.json

mental-health-bridge-sync-obsidian:
	python -m tools.tol_digest.mental_health_bridge.obsidian_sync --root outputs/tol_digest/mental_health_bridge --vault $(if $(VAULT),$(VAULT),obsidian) --out outputs/tol_digest/mental_health_bridge/obsidian_sync_result.json

mental-health-bridge-command-center-payloads:
	python -m tools.tol_digest.mental_health_bridge.command_center_payloads --root outputs/tol_digest/mental_health_bridge --out outputs/command_center/mock_payloads/mental_health_bridge_status.json

mental-health-bridge-cycle:
	$(MAKE) mental-health-bridge
	$(MAKE) validate-mental-health-bridge
	$(MAKE) mental-health-bridge-sync-obsidian
	$(MAKE) mental-health-bridge-command-center-payloads
	$(MAKE) ontology-language-check || true
	$(MAKE) ds005620-generated-language-check || true

literature-senses-plan:
	python -m tools.literature_senses.source_registry --out outputs/literature_senses/source_registry.json
	python -m tools.literature_senses.query_packs --out outputs/literature_senses/query_pack_registry.json
	python -m tools.literature_senses.retrieval_plan --sources outputs/literature_senses/source_registry.json --query-packs outputs/literature_senses/query_pack_registry.json --out outputs/literature_senses/retrieval_plan.json

literature-senses-fixture-run:
	$(MAKE) literature-senses-plan
	python -m tools.literature_senses.retrieval --mode fixture --query-packs outputs/literature_senses/query_pack_registry.json --out outputs/literature_senses/fixture_retrieved_papers.json
	python -m tools.literature_senses.normalize --input outputs/literature_senses/fixture_retrieved_papers.json --out outputs/literature_senses/normalized_papers.json
	python -m tools.literature_senses.dedupe --input outputs/literature_senses/normalized_papers.json --out outputs/literature_senses/deduped_papers.json
	python -m tools.literature_senses.scoring --input outputs/literature_senses/deduped_papers.json --query-packs outputs/literature_senses/query_pack_registry.json --out outputs/literature_senses/scored_papers.json
	python -m tools.literature_senses.claim_extractor --input outputs/literature_senses/scored_papers.json --out outputs/literature_senses/claim_extraction_report.json
	python -m tools.literature_senses.evidence_tiering --input outputs/literature_senses/claim_extraction_report.json --out outputs/literature_senses/evidence_tier_matrix.json
	python -m tools.literature_senses.theory_mapper --claims outputs/literature_senses/claim_extraction_report.json --tiers outputs/literature_senses/evidence_tier_matrix.json --out outputs/literature_senses/construct_mapping_matrix.json
	python -m tools.literature_senses.falsifier_detector --claims outputs/literature_senses/claim_extraction_report.json --mapping outputs/literature_senses/construct_mapping_matrix.json --out outputs/literature_senses/falsifier_watchlist.json
	python -m tools.literature_senses.synthesis_engine --scored outputs/literature_senses/scored_papers.json --claims outputs/literature_senses/claim_extraction_report.json --tiers outputs/literature_senses/evidence_tier_matrix.json --mapping outputs/literature_senses/construct_mapping_matrix.json --falsifiers outputs/literature_senses/falsifier_watchlist.json --out outputs/literature_senses

validate-literature-senses:
	python -m tools.literature_senses.validator --root outputs/literature_senses --json-out outputs/literature_senses/literature_senses_validation.json
literature-senses-sync-obsidian:
	python -m tools.literature_senses.obsidian_sync --root outputs/literature_senses --vault $(if $(VAULT),$(VAULT),obsidian) --out outputs/literature_senses/obsidian_sync_result.json
literature-senses-command-center-payloads:
	python -m tools.literature_senses.command_center_payloads --root outputs/literature_senses --out outputs/command_center/mock_payloads
literature-senses-rag-pack:
	python -m tools.literature_senses.rag_pack --root outputs/literature_senses --out outputs/literature_senses/rag_pack
literature-senses-cycle:
	$(MAKE) literature-senses-fixture-run
	$(MAKE) validate-literature-senses
	$(MAKE) literature-senses-sync-obsidian
	$(MAKE) literature-senses-command-center-payloads
	$(MAKE) literature-senses-rag-pack
	$(MAKE) ontology-language-check || true
	$(MAKE) ds005620-generated-language-check || true
	$(MAKE) command-center-api-smoke || true

.PHONY: project-corpus-inventory project-corpus-digest validate-project-corpus-digest project-corpus-sync-obsidian project-corpus-command-center-payloads project-corpus-rag-pack project-corpus-cycle

project-corpus-inventory:
	python -m tools.project_corpus_digest.inventory --roots . --out outputs/project_corpus_digest

project-corpus-digest:
	python -m tools.project_corpus_digest.digestor --root outputs/project_corpus_digest --out outputs/project_corpus_digest

validate-project-corpus-digest:
	python -m tools.project_corpus_digest.validator --root outputs/project_corpus_digest --json-out outputs/project_corpus_digest/project_corpus_validation.json

project-corpus-sync-obsidian:
	python -m tools.project_corpus_digest.obsidian_sync --root outputs/project_corpus_digest --vault obsidian/10_Project_Corpus --out outputs/project_corpus_digest/obsidian_sync_result.json

project-corpus-command-center-payloads:
	python -m tools.project_corpus_digest.command_center_payloads --root outputs/project_corpus_digest --out outputs/command_center/mock_payloads

project-corpus-rag-pack:
	python -m tools.project_corpus_digest.rag_pack --root outputs/project_corpus_digest --out outputs/project_corpus_digest

project-corpus-cycle:
	$(MAKE) project-corpus-inventory
	$(MAKE) project-corpus-digest
	$(MAKE) validate-project-corpus-digest
	$(MAKE) project-corpus-sync-obsidian
	$(MAKE) project-corpus-command-center-payloads
	$(MAKE) project-corpus-rag-pack

.PHONY: public-repo-harvest-plan public-repo-harvest-fixture-run validate-public-repo-harvest public-repo-harvest-sync-obsidian public-repo-harvest-command-center-payloads public-repo-harvest-rag-pack public-repo-harvest-cycle

public-repo-harvest-plan:
	python -m tools.public_repo_harvest.source_repo_registry --out outputs/public_repo_harvest/source_repo_registry.json
	python -m tools.public_repo_harvest.query_packs --out outputs/public_repo_harvest/repo_search_query_pack.json

public-repo-harvest-fixture-run:
	$(MAKE) public-repo-harvest-plan
	python -m tools.public_repo_harvest.fixture_candidates --registry outputs/public_repo_harvest/source_repo_registry.json --query-packs outputs/public_repo_harvest/repo_search_query_pack.json --out outputs/public_repo_harvest/candidate_repo_matrix.json
	python -m tools.public_repo_harvest.license_scanner --candidates outputs/public_repo_harvest/candidate_repo_matrix.json --out outputs/public_repo_harvest/license_compatibility_matrix.json
	python -m tools.public_repo_harvest.pattern_classifier --candidates outputs/public_repo_harvest/candidate_repo_matrix.json --licenses outputs/public_repo_harvest/license_compatibility_matrix.json --out outputs/public_repo_harvest/reusable_pattern_registry.json
	python -m tools.public_repo_harvest.subsystem_mapper --patterns outputs/public_repo_harvest/reusable_pattern_registry.json --out outputs/public_repo_harvest/subsystem_integration_blueprint.json
	python -m tools.public_repo_harvest.compatibility_patch_plan --blueprint outputs/public_repo_harvest/subsystem_integration_blueprint.json --out outputs/public_repo_harvest/compatibility_patch_plan.json
	python -m tools.public_repo_harvest.external_systems_scorecard --candidates outputs/public_repo_harvest/candidate_repo_matrix.json --out outputs/public_repo_harvest/external_systems_scorecard.json
	python -m tools.public_repo_harvest.priority_queue --scorecard outputs/public_repo_harvest/external_systems_scorecard.json --out outputs/public_repo_harvest/integration_priority_queue.json
	python -m tools.public_repo_harvest.reporting --root outputs/public_repo_harvest

validate-public-repo-harvest:
	python -m tools.public_repo_harvest.validator --root outputs/public_repo_harvest --json-out outputs/public_repo_harvest/public_repo_harvest_validation.json

public-repo-harvest-sync-obsidian:
	python -m tools.public_repo_harvest.obsidian_sync --root outputs/public_repo_harvest --vault obsidian --out outputs/public_repo_harvest/obsidian_sync_result.json

public-repo-harvest-command-center-payloads:
	python -m tools.public_repo_harvest.command_center_payloads --root outputs/public_repo_harvest --out outputs/command_center/mock_payloads

public-repo-harvest-rag-pack:
	python -m tools.public_repo_harvest.rag_pack --root outputs/public_repo_harvest --out outputs/public_repo_harvest/rag_pack

public-repo-harvest-cycle:
	$(MAKE) public-repo-harvest-fixture-run
	$(MAKE) validate-public-repo-harvest
	$(MAKE) public-repo-harvest-sync-obsidian
	$(MAKE) public-repo-harvest-command-center-payloads
	$(MAKE) public-repo-harvest-rag-pack

toe-literature-bridge:
	python -m tools.toe_research.literature_bridge.generator --roots outputs/literature_senses outputs/project_corpus_digest outputs/public_repo_harvest outputs/tol_digest outputs/tol_digest/mental_health_bridge --out outputs/toe_research/literature_bridge
	python -m tools.toe_research.literature_bridge.topology_telemetry_digest --out outputs/toe_research/literature_bridge/topology_telemetry_upgrade_digest.md
	python -m tools.toe_research.literature_bridge.active_inference_digest --out outputs/toe_research/literature_bridge/active_inference_allostasis_digest.md
	python -m tools.toe_research.literature_bridge.computational_psychiatry_digest --out outputs/toe_research/literature_bridge/computational_psychiatry_digest.md
	python -m tools.toe_research.literature_bridge.bioelectric_digest --out outputs/toe_research/literature_bridge/bioelectric_basal_cognition_digest.md
	python -m tools.toe_research.literature_bridge.cosmology_constraints --out outputs/toe_research/literature_bridge/cosmology_constraint_matrix.json
	python -m tools.toe_research.literature_bridge.gravitational_wave_constraints --out outputs/toe_research/literature_bridge/gravitational_wave_constraint_matrix.json
	python -m tools.toe_research.literature_bridge.adversarial_consciousness_matrix --out outputs/toe_research/literature_bridge/consciousness_theory_adversarial_matrix.json
	python -m tools.toe_research.literature_bridge.equation_registry --out outputs/toe_research/literature_bridge/equation_candidate_registry.json
	python -m tools.toe_research.literature_bridge.falsifier_registry --out outputs/toe_research/literature_bridge/toe_falsifier_watchlist.json
	python -m tools.toe_research.literature_bridge.reporting --root outputs/toe_research/literature_bridge --out outputs/toe_research/literature_bridge/toe_literature_bridge_report.md

validate-toe-literature-bridge:
	python -m tools.toe_research.literature_bridge.validator --root outputs/toe_research/literature_bridge --json-out outputs/toe_research/literature_bridge/toe_literature_bridge_validation.json

toe-literature-bridge-sync-obsidian:
	python -m tools.toe_research.literature_bridge.obsidian_sync --root outputs/toe_research/literature_bridge --vault $(if $(VAULT),$(VAULT),obsidian) --out outputs/toe_research/literature_bridge/obsidian_sync_result.json

toe-literature-bridge-command-center-payloads:
	python -m tools.toe_research.literature_bridge.command_center_payloads --root outputs/toe_research/literature_bridge --out outputs/command_center/mock_payloads

toe-literature-bridge-rag-pack:
	python -m tools.toe_research.literature_bridge.rag_pack --root outputs/toe_research/literature_bridge --out outputs/toe_research/literature_bridge/rag_pack

toe-literature-bridge-cycle:
	$(MAKE) toe-literature-bridge
	$(MAKE) validate-toe-literature-bridge
	$(MAKE) toe-literature-bridge-sync-obsidian
	$(MAKE) toe-literature-bridge-command-center-payloads
	$(MAKE) toe-literature-bridge-rag-pack
	$(MAKE) ontology-language-check || true
	$(MAKE) ds005620-generated-language-check || true
	$(MAKE) command-center-api-smoke || true

codex-goal:
	python -m tools.codex_goals.goal_builder --preset toe_research --out outputs/codex_goals
	python -m tools.codex_goals.reporting --root outputs/codex_goals --out outputs/codex_goals/goal_pack_report.md

validate-codex-goal:
	python -m tools.codex_goals.goal_validator --root outputs/codex_goals --json-out outputs/codex_goals/goal_policy_validation.json

codex-goal-render:
	python -m tools.codex_goals.prompt_renderer --root outputs/codex_goals --out outputs/codex_goals/generated_codex_prompt.md

codex-goal-scorecard:
	python -m tools.codex_goals.scorecard --root outputs/codex_goals --out outputs/codex_goals/contribution_scorecard.json

codex-goal-sync-obsidian:
	python -m tools.codex_goals.obsidian_sync --root outputs/codex_goals --vault $(if $(VAULT),$(VAULT),obsidian) --out outputs/codex_goals/obsidian_sync_result.json

codex-goal-command-center-payloads:
	python -m tools.codex_goals.command_center_payloads --root outputs/codex_goals --out outputs/command_center/mock_payloads

codex-goal-cycle:
	$(MAKE) codex-goal
	$(MAKE) validate-codex-goal
	$(MAKE) codex-goal-render
	$(MAKE) codex-goal-scorecard
	$(MAKE) codex-goal-sync-obsidian
	$(MAKE) codex-goal-command-center-payloads


ds005620-real-runbook:
	python -m tools.ds005620_real_runbook.readiness_report --out outputs/btc_icft/ds005620_real_runbook

validate-ds005620-real-runbook:
	python -m tools.ds005620_real_runbook.validator --root outputs/btc_icft/ds005620_real_runbook

ds005620-real-runbook-sync-obsidian:
	python -m tools.ds005620_real_runbook.obsidian_sync --root outputs/btc_icft/ds005620_real_runbook --out outputs/obsidian/ds005620_real_runbook

ds005620-real-runbook-command-center-payloads:
	python -m tools.ds005620_real_runbook.command_center_payloads --root outputs/btc_icft/ds005620_real_runbook --out outputs/command_center/mock_payloads

ds005620-real-runbook-cycle:
	$(MAKE) ds005620-real-runbook
	$(MAKE) validate-ds005620-real-runbook
	$(MAKE) ds005620-real-runbook-sync-obsidian
	$(MAKE) ds005620-real-runbook-command-center-payloads

ds005620-post-execution-controls:
	python -m tools.ds005620_post_execution_controls.execution_artifact_audit --execution-root outputs/btc_icft/ds005620_real_benchmark_execution --runbook-root outputs/btc_icft/ds005620_real_runbook --out outputs/btc_icft/ds005620_post_execution_controls
	python -m tools.ds005620_post_execution_controls.null_controls_plan --out outputs/btc_icft/ds005620_post_execution_controls
	python -m tools.ds005620_post_execution_controls.ablation_plan --out outputs/btc_icft/ds005620_post_execution_controls
	python -m tools.ds005620_post_execution_controls.leakage_report --out outputs/btc_icft/ds005620_post_execution_controls
	python -m tools.ds005620_post_execution_controls.artifact_report --out outputs/btc_icft/ds005620_post_execution_controls
	python -m tools.ds005620_post_execution_controls.statistical_report --out outputs/btc_icft/ds005620_post_execution_controls
	python -m tools.ds005620_post_execution_controls.empirical_claim_gate --root outputs/btc_icft/ds005620_post_execution_controls --json-out outputs/btc_icft/ds005620_post_execution_controls/empirical_claim_gate.json
	python -m tools.ds005620_post_execution_controls.publication_readiness --root outputs/btc_icft/ds005620_post_execution_controls
	python -m tools.ds005620_post_execution_controls.control_runbook --root outputs/btc_icft/ds005620_post_execution_controls
	python -m tools.ds005620_post_execution_controls.reporting --root outputs/btc_icft/ds005620_post_execution_controls

validate-ds005620-post-execution-controls:
	python -m tools.ds005620_post_execution_controls.validator --root outputs/btc_icft/ds005620_post_execution_controls

ds005620-post-execution-controls-sync-obsidian:
	python -m tools.ds005620_post_execution_controls.obsidian_sync --root outputs/btc_icft/ds005620_post_execution_controls --obsidian-root obsidian/15_DS005620_Post_Execution_Controls

ds005620-post-execution-controls-command-center-payloads:
	python -m tools.ds005620_post_execution_controls.command_center_payloads --out outputs/command_center/mock_payloads

ds005620-post-execution-controls-rag-pack:
	python -m tools.ds005620_post_execution_controls.rag_pack --root outputs/btc_icft/ds005620_post_execution_controls/rag_pack

ds005620-post-execution-controls-cycle:
	$(MAKE) ds005620-post-execution-controls
	$(MAKE) validate-ds005620-post-execution-controls
	$(MAKE) ds005620-post-execution-controls-sync-obsidian
	$(MAKE) ds005620-post-execution-controls-command-center-payloads
	$(MAKE) ds005620-post-execution-controls-rag-pack
