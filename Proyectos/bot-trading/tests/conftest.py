import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.alerts import Alerter  # noqa: E402
from bot.config import Config  # noqa: E402
from bot.state import State  # noqa: E402

HOUR_MS = 3_600_000
T0 = 1_700_000_000_000 - (1_700_000_000_000 % HOUR_MS)


def make_candles(closes, start_ms=T0, spread=0.004):
    out = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        h = max(o, c) * (1 + spread)
        lo = min(o, c) * (1 - spread)
        out.append([start_ms + i * HOUR_MS, o, h, lo, c, 1.0])
        prev = c
    return out


def down_then_up(n_down=260, n_up=200, start=100.0):
    closes, p = [], start
    for i in range(n_down):
        p *= 1 - 0.002 + 0.003 * math.sin(i / 5)
        closes.append(p)
    for i in range(n_up):
        p *= 1 + 0.004 + 0.003 * math.sin(i / 5)
        closes.append(p)
    return closes


class FakeExchange:
    """Imita la parte de ccxt que usa el bot."""

    def __init__(self, candles):
        self.candles = candles
        self.price = candles[-1][4]

    def fetch_ohlcv(self, symbol, timeframe, limit=500):
        return [list(k) for k in self.candles[-limit:]]

    def fetch_ticker(self, symbol):
        return {"last": self.price}


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.symbols = ["BTC/USDT"]
    c.storage.db_path = str(tmp_path / "bot.db")
    c.storage.kill_switch_file = str(tmp_path / "KILL")
    c.storage.heartbeat_file = str(tmp_path / "heartbeat")
    return c


@pytest.fixture
def state(cfg):
    return State(cfg.storage.db_path)


@pytest.fixture
def alerter(cfg):
    return Alerter(cfg.alerts)
