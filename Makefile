.PHONY: validate-governance test-root test-core test-awareness test-all smoke smoke-core eval-awareness check

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
