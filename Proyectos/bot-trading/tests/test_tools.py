import os
import stat
import time

import ccxt
import pytest
import yaml

from bot.config import load_config, load_dotenv
from bot.main import main
from bot.preflight import FAIL, OK, WARN, run_checks
from bot.setup_wizard import run_wizard
from bot.state import State, Trade

from .conftest import HOUR_MS, down_then_up, make_candles


class MarketExchange:
    """Exchange falso con mercados, mínimos y precisión, como ccxt."""

    parse_timeframe = staticmethod(ccxt.Exchange.parse_timeframe)

    def __init__(self, min_cost=10.0, fail_connect=False):
        start = int(time.time() * 1000) // HOUR_MS * HOUR_MS - 459 * HOUR_MS
        self.candles = make_candles(down_then_up(), start_ms=start)
        self.markets = {}
        self.min_cost = min_cost
        self.fail_connect = fail_connect

    def load_markets(self):
        if self.fail_connect:
            raise ccxt.NetworkError("sin conexión")
        self.markets = {"BTC/USDT": {"limits": {"amount": {"min": 0.0001}, "cost": {"min": self.min_cost}}}}
        return self.markets

    def market(self, symbol):
        return self.markets[symbol]

    def amount_to_precision(self, symbol, qty):
        return f"{int(qty * 1e4) / 1e4:.4f}"

    def fetch_ohlcv(self, symbol, timeframe, limit=500):
        return self.candles[-limit:]

    def fetch_ticker(self, symbol):
        return {"last": self.candles[-1][4]}


def _answers(*values):
    it = iter(values)
    return lambda prompt="": next(it)


def test_wizard_creates_paper_config_and_env(tmp_path):
    cfg_path, env_path = tmp_path / "config.yaml", tmp_path / ".env"
    # modo, exchange, quote, pares, timeframe, capital, perfil, telegram?, heartbeat
    ask = _answers("", "", "", "BTC/USDT", "4h", "5000", "1", "n", "")
    cfg = run_wizard(str(cfg_path), str(env_path), ask=ask, secret=_answers())
    assert cfg.mode == "paper" and cfg.timeframe == "4h"
    data = yaml.safe_load(cfg_path.read_text())
    assert data["paper_initial_balance"] == 5000 and data["risk"]["risk_per_trade"] == 0.005
    assert "api_key" not in data and "telegram_token" not in data["alerts"]
    assert stat.S_IMODE(os.stat(env_path).st_mode) == 0o600
    load_config(str(cfg_path), env_file=str(env_path))  # el archivo generado se carga sin errores


def test_wizard_live_puts_secrets_only_in_env(tmp_path, monkeypatch):
    for k in ("EXCHANGE_API_KEY", "EXCHANGE_API_SECRET", "BOT_CONFIRM_LIVE"):
        monkeypatch.delenv(k, raising=False)
    cfg_path, env_path = tmp_path / "config.yaml", tmp_path / ".env"
    # modo, exchange, quote, pares, timeframe, testnet?, perfil, confirmar live?, telegram?, heartbeat
    ask = _answers("live", "kraken", "usd", "BTC/USD", "", "s", "2", "n", "n", "")
    run_wizard(str(cfg_path), str(env_path), ask=ask, secret=_answers("KEY123", "SECRET456", ""))
    assert "KEY123" not in cfg_path.read_text() and "SECRET456" not in cfg_path.read_text()
    env = env_path.read_text()
    assert "EXCHANGE_API_KEY=KEY123" in env and "BOT_CONFIRM_LIVE" not in env
    with pytest.raises(ValueError, match="BOT_CONFIRM_LIVE"):  # sin confirmación no arranca en real
        load_config(str(cfg_path), env_file=str(env_path))


def test_wizard_does_not_overwrite_without_confirmation(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("mode: paper\n")
    with pytest.raises(SystemExit):
        run_wizard(str(cfg_path), str(tmp_path / ".env"), ask=_answers("n"), secret=_answers())
    assert cfg_path.read_text() == "mode: paper\n"


def test_dotenv_does_not_override_environment(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comentario\nTELEGRAM_CHAT_ID='123'\nHEARTBEAT_URL=\nEXCHANGE_API_KEY=archivo\n")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("HEARTBEAT_URL", raising=False)
    monkeypatch.setenv("EXCHANGE_API_KEY", "entorno")
    load_dotenv(str(env))
    assert os.environ["TELEGRAM_CHAT_ID"] == "123"
    assert "HEARTBEAT_URL" not in os.environ
    assert os.environ["EXCHANGE_API_KEY"] == "entorno"


def test_preflight_ok(cfg):
    results = run_checks(cfg, MarketExchange())
    assert not [m for lvl, m in results if lvl == FAIL], results
    assert any(lvl == OK and "orden típica" in m for lvl, m in results)
    assert any(lvl == WARN and "Telegram" in m for lvl, m in results)


def test_preflight_detects_capital_below_minimum(cfg):
    cfg.paper_initial_balance = 50
    results = run_checks(cfg, MarketExchange(min_cost=100))
    assert any(lvl == FAIL and "mínimo" in m for lvl, m in results)


def test_preflight_detects_unknown_symbol_and_no_connection(cfg):
    cfg.symbols = ["DOGE/USDT"]
    assert any(lvl == FAIL and "no existe" in m for lvl, m in run_checks(cfg, MarketExchange()))
    assert any(lvl == FAIL and "conectar" in m for lvl, m in run_checks(cfg, MarketExchange(fail_connect=True)))


def test_export_csv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = State("data/bot.db")
    state.record_equity(0, 1)
    state.close_position("BTC/USDT", Trade(1_700_000_000, "BTC/USDT", "sell", 0.1, 100.0, 0.01, 5.5, "test"))
    main(["export", "--output", "ops.csv"])
    lines = (tmp_path / "ops.csv").read_text().splitlines()
    assert lines[0].startswith("fecha_utc") and "5.5" in lines[1]
