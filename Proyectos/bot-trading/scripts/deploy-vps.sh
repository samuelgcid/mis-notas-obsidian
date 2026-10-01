#!/usr/bin/env bash
# Despliegue en un VPS Linux (Debian/Ubuntu) como servicio systemd.
# Uso, desde la carpeta del proyecto en el servidor:  sudo ./scripts/deploy-vps.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Ejecútalo con sudo."; exit 1; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST=/opt/bot-trading

if ! python3 -m venv --help >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq python3 python3-venv >/dev/null
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || { echo "❌ Hace falta Python 3.10+ en el servidor."; exit 1; }

id bot >/dev/null 2>&1 || useradd --system --home "$DEST" --shell /usr/sbin/nologin bot
mkdir -p "$DEST/data"
# Copia el código; conserva config.yaml, .env y data/ si ya existen en el destino.
cp -r "$SRC/bot" "$SRC/requirements.txt" "$DEST/"
for f in config.yaml .env; do
  if [ -f "$SRC/$f" ] && [ ! -f "$DEST/$f" ]; then cp "$SRC/$f" "$DEST/$f"; fi
done
[ -f "$DEST/config.yaml" ] || cp "$SRC/config.example.yaml" "$DEST/config.yaml"

python3 -m venv "$DEST/.venv"
"$DEST/.venv/bin/pip" install -q --upgrade pip
"$DEST/.venv/bin/pip" install -q -r "$DEST/requirements.txt"

chown -R bot:bot "$DEST"
[ -f "$DEST/.env" ] && chmod 600 "$DEST/.env"

echo "→ Comprobación previa"
(cd "$DEST" && sudo -u bot "$DEST/.venv/bin/python" -m bot check) || {
  echo "⚠️  Corrige los problemas (edita $DEST/config.yaml y $DEST/.env) y vuelve a ejecutar este script."
  exit 1
}

cp "$SRC/deploy/bot-trading.service" /etc/systemd/system/bot-trading.service
systemctl daemon-reload
systemctl enable --now bot-trading
systemctl restart bot-trading

cat <<MSG

✅ Bot desplegado como servicio. Comandos útiles:
   systemctl status bot-trading
   journalctl -u bot-trading -f
   cd $DEST && sudo -u bot .venv/bin/python -m bot status
   cd $DEST && sudo -u bot .venv/bin/python -m bot kill     # parada de emergencia
MSG
