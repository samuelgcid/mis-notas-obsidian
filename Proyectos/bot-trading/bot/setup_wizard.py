"""Asistente interactivo: crea config.yaml y .env haciendo preguntas sencillas."""
from __future__ import annotations

import getpass
import os
from dataclasses import asdict

import yaml

from .config import Config, validate

PROFILES = {
    "1": ("conservador", dict(risk_per_trade=0.005, max_position_pct=0.15, max_total_exposure_pct=0.40,
                              max_daily_loss_pct=0.02, max_drawdown_pct=0.10)),
    "2": ("moderado", dict(risk_per_trade=0.01, max_position_pct=0.25, max_total_exposure_pct=0.60,
                           max_daily_loss_pct=0.03, max_drawdown_pct=0.15)),
    "3": ("agresivo", dict(risk_per_trade=0.02, max_position_pct=0.35, max_total_exposure_pct=0.80,
                           max_daily_loss_pct=0.05, max_drawdown_pct=0.25)),
}


def _ask(question: str, default: str, ask=input) -> str:
    answer = ask(f"{question} [{default}]: ").strip()
    return answer or default


def _yes(question: str, default: bool, ask=input) -> bool:
    answer = _ask(question + " (s/n)", "s" if default else "n", ask).lower()
    return answer.startswith(("s", "y"))


def run_wizard(config_path: str = "config.yaml", env_path: str = ".env", ask=input, secret=getpass.getpass) -> Config:
    print("\n=== Configuración del bot de trading ===\n")
    if os.path.exists(config_path) and not _yes(f"{config_path} ya existe. ¿Sobrescribirlo?", False, ask):
        raise SystemExit("Cancelado: no se ha tocado nada.")

    cfg = Config()
    print("Modo paper = simulado con precios reales (recomendado para empezar).")
    cfg.mode = "live" if _ask("Modo (paper/live)", "paper", ask).lower() == "live" else "paper"
    cfg.exchange = _ask("Exchange (nombre en ccxt: binance, kraken, bybit, okx, kucoin...)", "binance", ask).lower()
    cfg.quote_currency = _ask("Moneda de cotización", "USDT", ask).upper()
    symbols = _ask("Pares separados por comas", f"BTC/{cfg.quote_currency},ETH/{cfg.quote_currency}", ask)
    cfg.symbols = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    cfg.timeframe = _ask("Temporalidad de las velas (15m, 1h, 4h, 1d)", "1h", ask)
    if cfg.mode == "paper":
        cfg.paper_initial_balance = float(_ask("Capital simulado inicial", "10000", ask))
    else:
        cfg.sandbox = _yes("¿Usar la TESTNET del exchange? (muy recomendable la primera vez)", True, ask)

    print("\nPerfil de riesgo:")
    for key, (name, p) in PROFILES.items():
        print(f"  {key}) {name}: {p['risk_per_trade']:.1%} por operación, "
              f"pausa diaria al -{p['max_daily_loss_pct']:.0%}, parada total al -{p['max_drawdown_pct']:.0%}")
    _, profile = PROFILES.get(_ask("Elige 1, 2 o 3", "2", ask), PROFILES["2"])
    for k, v in profile.items():
        setattr(cfg.risk, k, v)

    env: dict[str, str] = {}
    if cfg.mode == "live":
        print("\nClaves de API: créalas SIN permiso de retirada y, si puedes, limitadas a la IP del servidor.")
        env["EXCHANGE_API_KEY"] = secret("API key: ").strip()
        env["EXCHANGE_API_SECRET"] = secret("API secret: ").strip()
        password = secret("API password/passphrase (Enter si tu exchange no la usa): ").strip()
        if password:
            env["EXCHANGE_API_PASSWORD"] = password
        if _yes("¿Confirmas que quieres operar con dinero real cuando arranques el bot?", False, ask):
            env["BOT_CONFIRM_LIVE"] = "yes"
    if _yes("\n¿Quieres alertas por Telegram?", False, ask):
        print("Crea un bot con @BotFather y escribe a @userinfobot para saber tu chat_id.")
        env["TELEGRAM_BOT_TOKEN"] = secret("Token del bot: ").strip()
        env["TELEGRAM_CHAT_ID"] = _ask("Chat ID", "", ask)
    hb = _ask("URL de heartbeat externo (p. ej. healthchecks.io; Enter para omitir)", "", ask)
    if hb:
        env["HEARTBEAT_URL"] = hb

    # Validar con los secretos cargados, como hará el bot al arrancar.
    cfg.api_key, cfg.api_secret = env.get("EXCHANGE_API_KEY"), env.get("EXCHANGE_API_SECRET")
    validate(cfg, require_live_confirmation=False)  # la confirmación se exige al arrancar

    data = asdict(cfg)
    for secret_key in ("api_key", "api_secret", "api_password"):
        data.pop(secret_key)
    data["alerts"] = {k: v for k, v in data["alerts"].items() if k in ("dedup_seconds", "heartbeat_ping_seconds")}
    with open(config_path, "w", encoding="utf-8") as fh:
        fh.write("# Generado por `python -m bot setup`. Los secretos están en .env.\n")
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)

    if env or not os.path.exists(env_path):
        fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # solo legible por ti
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("# Generado por `python -m bot setup`. NUNCA lo subas a git.\n")
            for k, v in env.items():
                fh.write(f"{k}={v}\n")

    print(f"\n✅ Guardado {config_path}" + (f" y {env_path}" if env else ""))
    print("Siguiente paso: `python -m bot check` para comprobar que todo funciona.\n")
    return cfg
