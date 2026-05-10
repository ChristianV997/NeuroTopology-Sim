test-root:
	pytest tests/ -v --tb=short

test-awareness:
	cd apps/awareness_studio && python -m pytest -v --tb=short

smoke:
	python main.py --mode synthetic

eval-awareness:
	cd apps/awareness_studio && python -m awareness_studio.eval_runner --no-llm --quiet

check:
	$(MAKE) test-root
	$(MAKE) smoke
