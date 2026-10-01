"""Carga y validación de la configuración (YAML + variables de entorno)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any

import yaml


@dataclass
class StrategyConfig:
    fast_ema: int = 20
    slow_ema: int = 50
    trend_ema: int = 200
    atr_period: int = 14
    atr_stop_mult: float = 2.0      # stop inicial = entrada - N * ATR
    atr_trail_mult: float = 3.0     # trailing stop = cierre - N * ATR (solo sube)
    entry_window: int = 3           # el escenario alcista debe haberse activado en las últimas N velas
    cooldown_bars: int = 3          # velas de espera tras cerrar una posición


@dataclass
class RiskConfig:
    risk_per_trade: float = 0.01          # 1 % del capital arriesgado por operación
    max_position_pct: float = 0.25        # una posición no supera el 25 % del capital
    max_total_exposure_pct: float = 0.60  # exposición total máxima
    max_open_positions: int = 3
    max_daily_loss_pct: float = 0.03      # pérdida diaria que pausa nuevas entradas
    max_drawdown_pct: float = 0.15        # caída desde máximos que detiene el bot
    fee_rate: float = 0.001
    slippage_pct: float = 0.0005


@dataclass
class DataConfig:
    candles: int = 300               # velas que usa la estrategia (igual en backtest y en real)
    max_staleness_bars: int = 2      # datos más viejos que esto = feed congelado
    max_bar_move_pct: float = 0.20   # movimiento de una vela mayor que esto = dato anómalo


@dataclass
class StorageConfig:
    db_path: str = "data/bot.db"
    log_path: str = "data/bot.log"
    kill_switch_file: str = "data/KILL"
    heartbeat_file: str = "data/heartbeat"


@dataclass
class AlertsConfig:
    dedup_seconds: int = 600
    heartbeat_ping_seconds: int = 300
    # Los secretos llegan por entorno, nunca en el YAML.
    telegram_token: str | None = None
    telegram_chat_id: str | None = None
    heartbeat_url: str | None = None


@dataclass
class Config:
    mode: str = "paper"              # paper | live
    exchange: str = "binance"
    sandbox: bool = True             # en modo live, usar la testnet del exchange
    exchange_stops: bool = True      # intentar dejar el stop-loss colocado en el exchange
    symbols: list[str] = field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    quote_currency: str = "USDT"
    timeframe: str = "1h"
    loop_seconds: int = 60
    max_consecutive_errors: int = 5
    paper_initial_balance: float = 10_000.0
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    data: DataConfig = field(default_factory=DataConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    # Secretos del exchange (solo entorno).
    api_key: str | None = None
    api_secret: str | None = None
    api_password: str | None = None


def _merge(dc: Any, data: dict) -> Any:
    known = {f.name: f for f in fields(dc)}
    for key, value in (data or {}).items():
        if key not in known:
            raise ValueError(f"Clave de configuración desconocida: {key}")
        current = getattr(dc, key)
        if is_dataclass(current):
            _merge(current, value)
        else:
            setattr(dc, key, value)
    return dc


def load_config(path: str | None) -> Config:
    cfg = Config()
    if path:
        with open(path, encoding="utf-8") as fh:
            _merge(cfg, yaml.safe_load(fh) or {})
    env = os.environ
    cfg.api_key = env.get("EXCHANGE_API_KEY")
    cfg.api_secret = env.get("EXCHANGE_API_SECRET")
    cfg.api_password = env.get("EXCHANGE_API_PASSWORD")
    cfg.alerts.telegram_token = env.get("TELEGRAM_BOT_TOKEN")
    cfg.alerts.telegram_chat_id = env.get("TELEGRAM_CHAT_ID")
    cfg.alerts.heartbeat_url = env.get("HEARTBEAT_URL")
    validate(cfg)
    return cfg


def validate(cfg: Config) -> None:
    if cfg.mode not in ("paper", "live"):
        raise ValueError("mode debe ser 'paper' o 'live'")
    for sym in cfg.symbols:
        if "/" not in sym or sym.split("/")[1] != cfg.quote_currency:
            raise ValueError(f"{sym}: todos los símbolos deben cotizar en {cfg.quote_currency}")
    s, r = cfg.strategy, cfg.risk
    if not s.fast_ema < s.slow_ema:
        raise ValueError("fast_ema debe ser menor que slow_ema")
    if cfg.data.candles < max(s.slow_ema, s.trend_ema, s.atr_period) + s.entry_window + 2:
        raise ValueError("data.candles es demasiado pequeño para los periodos de la estrategia")
    if not 0 < r.risk_per_trade <= 0.05:
        raise ValueError("risk_per_trade debe estar entre 0 y 0.05 (5 %)")
    if not 0 < r.max_drawdown_pct < 1 or not 0 < r.max_daily_loss_pct < 1:
        raise ValueError("los límites de pérdida deben estar entre 0 y 1")
    if cfg.mode == "live":
        if not (cfg.api_key and cfg.api_secret):
            raise ValueError("modo live requiere EXCHANGE_API_KEY y EXCHANGE_API_SECRET")
        if os.environ.get("BOT_CONFIRM_LIVE") != "yes":
            raise ValueError(
                "modo live bloqueado: exporta BOT_CONFIRM_LIVE=yes si de verdad quieres operar"
            )
