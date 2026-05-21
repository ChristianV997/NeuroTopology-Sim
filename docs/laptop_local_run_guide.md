# Laptop Local Run Guide

## Purpose
Provide deterministic local setup and diagnosis for safe laptop execution without real data.

## Recommended laptop architecture
Windows laptop + WSL2 Ubuntu + VS Code Remote WSL + Python virtual environment.

## Why WSL2 is recommended
WSL2 gives Linux-compatible paths/tools and avoids Windows path/performance mismatch.

## First install
Install WSL2 Ubuntu, git, make, build-essential, python3, python3-venv, python3-pip.

## Clone repo
Clone into `~/projects/ScienceR-Dsim` (not `/mnt/c/...`).

## Create virtual environment
`python3 -m venv .venv && source .venv/bin/activate`

## Install requirements
`pip install -r requirements.txt`

## Run first smoke test
`make laptop-setup-doctor && make laptop-smoke-dry-run`

## Run local ops safely
`make local-ops-healthcheck && make local-ops-run-loop-dry-run`

## Run ToL pipeline
`make tol-digest-cycle`

## Run OpenAI RAG mock mode
Use mock/dry-run commands only; no key is required for local setup checks.

## Where outputs go
`outputs/local_setup/` for setup/diagnostic artifacts.

## Common failures
Missing make, inactive venv, Python too old, running under `/mnt/c/`, missing dependencies.

## What remains manual
System package installation, dataset placement, and optional API key provisioning for live services.
