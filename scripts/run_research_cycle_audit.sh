#!/usr/bin/env bash
# POSIX/bash entry for the research-cycle operator pack.
# This is not a PowerShell script. Windows operators should use
# scripts/run_research_cycle_audit.ps1 instead.
set -eu

usage() {
  cat <<'EOF'
Usage: scripts/run_research_cycle_audit.sh --output-dir DIR [orchestrator args...]

Read-only by default. Writes only under --output-dir.
Does not download data, install packages, mutate git, or run solvers
unless --allow-solver is passed to the Python orchestrator.

Infrastructure PASS is not a scientific PASS.
Synthetic fixtures are not an empirical PASS.
EOF
}

if [ "$#" -eq 0 ]; then
  usage >&2
  exit 20
fi

OUTPUT_DIR=""
PASSTHRU=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output-dir)
      if [ "$#" -lt 2 ]; then
        echo "error: --output-dir requires a path" >&2
        exit 20
      fi
      OUTPUT_DIR="$2"
      PASSTHRU+=("$1" "$2")
      shift 2
      ;;
    --output-dir=*)
      OUTPUT_DIR="${1#--output-dir=}"
      PASSTHRU+=("$1")
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      PASSTHRU+=("$1")
      shift
      ;;
  esac
done

if [ -z "${OUTPUT_DIR}" ]; then
  echo "error: --output-dir is required; refusing to write elsewhere" >&2
  exit 20
fi

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "error: python3/python not found (NOT_AVAILABLE)" >&2
  exit 40
fi

export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
exec "${PYTHON}" -m ops.research_cycle audit --shell-family posix --python "${PYTHON}" "${PASSTHRU[@]}"
