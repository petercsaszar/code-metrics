#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH=${CONFIG_PATH:-/app/bulk_analyzer/config.yml}
PYTHON=${PYTHON_BIN:-python}

echo "public_project_analyzer.py now orchestrates per-analysis Docker containers from the host."
echo "Please run it outside the container: python bulk_analyzer/public_project_analyzer.py"
exit 1
