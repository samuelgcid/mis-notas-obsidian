#!/usr/bin/env bash
# Instalación local en Linux / macOS: entorno virtual, dependencias, tests y configuración.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null || { echo "❌ No encuentro $PY. Instala Python 3.10 o superior."; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || { echo "❌ Hace falta Python 3.10 o superior (tienes $("$PY" --version))."; exit 1; }

echo "→ Creando entorno virtual en .venv"
"$PY" -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install -q --upgrade pip
echo "→ Instalando dependencias"
pip install -q -r requirements-dev.txt

echo "→ Ejecutando tests"
python -m pytest -q

mkdir -p data
if [ ! -f config.yaml ]; then
  echo "→ No hay config.yaml: lanzo el asistente"
  python -m bot setup
fi

echo "→ Comprobación previa"
python -m bot check || echo "⚠️  Revisa los avisos de arriba antes de arrancar."

cat <<'MSG'

✅ Instalación terminada. Comandos útiles:
   ./scripts/run.sh            # arrancar el bot
   ./scripts/run.sh status     # ver estado
   ./scripts/run.sh backtest --symbol BTC/USDT --since 2022-01-01
MSG
