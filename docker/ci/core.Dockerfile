# CI-only CPU image. The production-root Dockerfile intentionally describes
# the full optional environment; ordinary CI must not build that environment.
FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLBACKEND=Agg \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 git make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-base.txt ./
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r requirements-base.txt

COPY . .

# Keep this image aligned with the required CPU/base contract. Optional
# MNE/GUDHI/Cripser/Torch/Cloud/QPU suites have separate explicit profiles.
CMD ["python", "scripts/run_tests_isolated.py", "--batch-size", "1", "--timeout-s", "120", "--report", "/tmp/core-test-report.json", "tests/test_run_record.py", "tests/test_run_records.py", "tests/test_benchmarks_registry.py", "tests/test_pipeline_job_schema.py", "tests/test_transitions_governance.py", "tests/test_transitions_features.py", "tests/btc_icft/test_report_guardrails.py", "tests/btc_icft/test_ontology_schema.py", "tests/runner/test_runner_isolation.py"]
