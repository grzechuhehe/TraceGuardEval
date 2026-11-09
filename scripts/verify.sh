#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --locked
uv run pytest -q
uv run traceguard validate --dataset data/gsn-v1
uv run traceguard validate --dataset data/gsn-v2
uv run python -m compileall -q src
uv build
git diff --check
