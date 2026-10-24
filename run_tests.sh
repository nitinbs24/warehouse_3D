#!/usr/bin/env bash
# Kept for convenience on Linux: the real runner is run_tests.py (works on Windows too).
# Usage: ./run_tests.sh [test-tags]   e.g. ./run_tests.sh /warehouse_3d:TestLocationGenerator
exec "${WH3D_PYTHON:-/mnt/CODE/Workspace/odoo/venv19/bin/python}" "$(dirname "$0")/run_tests.py" "$@"
