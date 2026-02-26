#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQ_FILE="${1:-${ROOT_DIR}/requirements.txt}"
OUT_DIR="${2:-${ROOT_DIR}/wheels}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
EXTRA_PIP_ARGS=${PIP_ARGS:-}

mkdir -p "${OUT_DIR}"

# Use PIP_ARGS to target a specific Blender/Python build, for example:
# PIP_ARGS="--platform manylinux2014_x86_64 --python-version 39 --implementation cp --abi cp39"
"${PYTHON_BIN}" -m pip download -r "${REQ_FILE}" -d "${OUT_DIR}" --only-binary=:all: ${EXTRA_PIP_ARGS}

echo "Wheels downloaded to ${OUT_DIR}"
