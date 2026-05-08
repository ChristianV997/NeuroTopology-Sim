# Simulation artifact documents for Awareness Studio RAG ingestion.
#
# This directory is populated by running:
#   python -m apps.awareness_studio.tools.export_sim_artifacts
#
# Or from repo root:
#   python apps/awareness_studio/tools/export_sim_artifacts.py --out apps/awareness_studio/inputs/sim_artifacts/
#
# Each .md file here corresponds to one hypothesis run record exported from
# the SQLite runs database or from artifacts/ directory summary.json files.
#
# The Awareness Studio indexer automatically includes this directory so the
# RAG can answer questions like:
#   - "What runs support hypothesis HYP-20260506-002?"
#   - "What was the verdict of the latest K-type hypothesis run?"
