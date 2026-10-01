#!/usr/bin/env bash
# Atajo: ./scripts/run.sh [comando] [opciones]  (por defecto: run)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || { echo "Primero ejecuta ./scripts/install.sh"; exit 1; }
# shellcheck disable=SC1091
. .venv/bin/activate
if [ $# -eq 0 ]; then set -- run; fi
exec python -m bot "$@"
