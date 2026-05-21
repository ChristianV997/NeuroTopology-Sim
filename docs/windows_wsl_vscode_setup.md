# Windows + WSL2 + VS Code Setup

## Install WSL2 Ubuntu
Install WSL2 and Ubuntu, then reboot if prompted.

## Open Ubuntu terminal
Launch Ubuntu and complete first-time user creation.

## Install system packages
`sudo apt update && sudo apt install -y git make build-essential python3 python3-venv python3-pip`

## Clone repo into WSL home
`mkdir -p ~/projects && cd ~/projects && git clone <repo-url> ScienceR-Dsim`

## Create .venv
`cd ScienceR-Dsim && python3 -m venv .venv`

## Install Python deps
`source .venv/bin/activate && pip install -r requirements.txt`

## Open VS Code from WSL
Run `code .` from repo root in Ubuntu terminal.

## Select interpreter
Choose `.venv/bin/python` in VS Code.

## Run smoke test
`make laptop-setup-doctor && make laptop-smoke-dry-run`

## Path caution
Do not keep repo under `/mnt/c` if performance/path issues appear.

## Secrets caution
Do not put API keys in frontend code.

## Troubleshooting
Use `make laptop-troubleshoot-report` and share files under `outputs/local_setup/`.
