# Reproducible container for the core sim engine (repo root): numpy/scipy/
# sklearn/mne EEG + topology pipelines. Borrows Neurodesk's recipe pattern
# (declarative build -> single-purpose image -> tested in CI) without
# adopting the Neurodesk platform itself -- this repo's pipelines run in
# minutes on a plain numpy/scipy stack, not on a 100+ tool neuroimaging
# desktop. See apps/awareness_studio/Dockerfile for the separate,
# independently-installable FastAPI/RAG chatbot environment.
FROM python:3.11-slim

# libgomp1: OpenMP runtime needed by scipy/scikit-learn/numba (py-pde) wheels.
# git: sim/run_cards.py::_git_commit() shells out to `git rev-parse` at
# runtime to stamp provenance on every RunRecord artifact.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run the full root test suite. CLAUDE.md's documented local
# command skips test_pci.py/test_stats.py/test_worldlines.py because a bare
# dev environment may lack scipy -- this image installs the full
# requirements.txt (scipy included), so those tests run here too, unlike
# the documented bare-environment command. Override with
# `docker run <image> <cmd>` for anything else (e.g. `python main.py --mode synthetic`).
CMD ["pytest", "tests/", "-q"]
