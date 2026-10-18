# Isolated test image for Awareness Studio. Keep the repository-relative
# layout required by its integration tests without copying VCS metadata or data.
FROM python:3.11-slim

WORKDIR /repo

COPY apps/awareness_studio/pyproject.toml apps/awareness_studio/pyproject.toml
COPY apps/awareness_studio/src/ apps/awareness_studio/src/
COPY apps/awareness_studio/tests/ apps/awareness_studio/tests/
COPY apps/awareness_studio/tools/ apps/awareness_studio/tools/
COPY apps/awareness_studio/inputs/ apps/awareness_studio/inputs/

# Root packages imported by the app's offline integration tests.
COPY tools/__init__.py tools/__init__.py
COPY tools/literature_evidence/ tools/literature_evidence/
COPY tools/simulation_artifacts/ tools/simulation_artifacts/
COPY tools/simulation_execution/ tools/simulation_execution/
COPY scripts/build_awareness_evidence_graph.py scripts/build_awareness_evidence_graph.py

# repo_paths.find_repository_root requires a .git marker plus the root tools
# package. This empty test-image marker is not Git metadata; .git is excluded
# from the build context and no repository history is copied into the image.
RUN mkdir -p /repo/.git

WORKDIR /repo/apps/awareness_studio
ENV PYTHONPATH=/repo

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e ".[dev,web]"

# Run the complete app test suite offline, including repository integrations.
CMD ["pytest", "-q"]
