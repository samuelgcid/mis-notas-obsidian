"""Backtest y validación walk-forward con la MISMA estrategia y el MISMO cálculo de tamaño
que usa el bot en real.

Supuestos realistas:
- La señal se calcula al cierre de una vela y se ejecuta en la apertura de la siguiente.
- Si el mínimo de la vela toca el stop, se sale al stop (o a la apertura si abrió por debajo).
- Comisiones y deslizamiento en cada operación.
"""
from __future__ import annotations

import csv
import itertools
import math
import os
import time
from copy import deepcopy
from dataclasses import dataclass, field

import ccxt

from .config import DataConfig, RiskConfig, StrategyConfig
from .risk import RiskManager
from .strategy import TrendFollowingStrategy


@dataclass
class _Pos:
    qty: float
    entry_price: float
    entry_fee: float
    stop: float


@dataclass
class BacktestResult:
    initial: float
    final: float
    equity_curve: list[float]
    trades: list[dict] = field(default_factory=list)
    bars_per_year: float = 8760

    @property
    def total_return(self) -> float:
        return self.final / self.initial - 1

    @property
    def max_drawdown(self) -> float:
        peak, mdd = -math.inf, 0.0
        for e in self.equity_curve:
            peak = max(peak, e)
            mdd = max(mdd, 1 - e / peak)
        return mdd

    @property
    def sharpe(self) -> float:
        rets = [b / a - 1 for a, b in zip(self.equity_curve, self.equity_curve[1:]) if a > 0]
        if len(rets) < 2:
            return 0.0
        mean = sum(rets) / len(rets)
        std = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
        return mean / std * math.sqrt(self.bars_per_year) if std > 0 else 0.0

    @property
    def win_rate(self) -> float:
        return sum(t["pnl"] > 0 for t in self.trades) / len(self.trades) if self.trades else 0.0

    @property
    def profit_factor(self) -> float:
        gains = sum(t["pnl"] for t in self.trades if t["pnl"] > 0)
        losses = -sum(t["pnl"] for t in self.trades if t["pnl"] < 0)
        return gains / losses if losses > 0 else (math.inf if gains > 0 else 0.0)

    def summary(self) -> dict:
        return {
            "operaciones": len(self.trades),
            "retorno_total": f"{self.total_return:+.2%}",
            "max_drawdown": f"{self.max_drawdown:.2%}",
            "sharpe": round(self.sharpe, 2),
            "aciertos": f"{self.win_rate:.1%}",
            "profit_factor": round(self.profit_factor, 2) if math.isfinite(self.profit_factor) else "inf",
            "capital_final": round(self.final, 2),
        }


def run_backtest(
    candles: list[list[float]],
    strat_cfg: StrategyConfig,
    risk_cfg: RiskConfig,
    window: int = DataConfig.candles,
    initial: float = 10_000.0,
    start: int = 0,
    timeframe: str = "1h",
) -> BacktestResult:
    """Simula desde `start`; las velas anteriores solo sirven de historial (calentamiento)."""
    strat = TrendFollowingStrategy(strat_cfg)
    risk = RiskManager(risk_cfg)
    fee, slip = risk_cfg.fee_rate, risk_cfg.slippage_pct
    cash, pos, pending = initial, None, None
    last_exit_i = -10**9
    trades: list[dict] = []
    curve: list[float] = []

    def close(i: int, price: float, reason: str):
        nonlocal cash, pos, last_exit_i
        exit_fee = pos.qty * price * fee
        cash += pos.qty * price - exit_fee
        pnl = pos.qty * (price - pos.entry_price) - exit_fee - pos.entry_fee
        trades.append({"ts": candles[i][0], "entrada": pos.entry_price, "salida": price, "pnl": pnl, "motivo": reason})
        pos, last_exit_i = None, i

    for i in range(start, len(candles)):
        _, o, h, low, c, _ = candles[i][:6]
        # 1) Ejecutar en la apertura lo decidido al cierre anterior.
        if pending is not None:
            if pending[0] == "buy" and pos is None:
                price = o * (1 + slip)
                stop = pending[1]
                qty = risk.position_size(cash, cash, 0.0, price, stop)
                if qty > 0:
                    entry_fee = qty * price * fee
                    cash -= qty * price + entry_fee
                    pos = _Pos(qty, price, entry_fee, stop)
            elif pending[0] == "sell" and pos is not None:
                close(i, o * (1 - slip), pending[1])
            pending = None
        # 2) Stop dentro de la vela.
        if pos is not None and low <= pos.stop:
            close(i, min(o, pos.stop) * (1 - slip), "stop-loss")
        # 3) Decidir al cierre con la misma ventana de velas que el bot en real.
        hist = candles[max(0, i - window + 1) : i + 1]
        if pos is not None:
            sig = strat.evaluate(hist, pos)
            if sig.action == "sell":
                pending = ("sell", sig.reason)
            elif sig.stop:
                pos.stop = max(pos.stop, sig.stop)
        elif i - last_exit_i >= strat_cfg.cooldown_bars:
            sig = strat.evaluate(hist, None)
            if sig.action == "buy":
                pending = ("buy", sig.stop)
        curve.append(cash + (pos.qty * c if pos else 0.0))

    if pos is not None:  # cerrar al final para medir el resultado real
        close(len(candles) - 1, candles[-1][4] * (1 - slip), "fin del backtest")
        curve[-1] = cash
    bars_per_year = 365 * 24 * 3600 / ccxt.Exchange.parse_timeframe(timeframe)
    return BacktestResult(initial, curve[-1] if curve else initial, curve, trades, bars_per_year)


def walk_forward(
    candles: list[list[float]],
    strat_cfg: StrategyConfig,
    risk_cfg: RiskConfig,
    grid: dict[str, list],
    folds: int = 4,
    train_ratio: float = 0.7,
    window: int = DataConfig.candles,
    timeframe: str = "1h",
    min_trades: int = 3,
) -> list[dict]:
    """Optimiza parámetros en cada tramo de entrenamiento y los evalúa en el tramo siguiente
    que la optimización NO ha visto. Si los resultados fuera de muestra se derrumban,
    la estrategia está sobreajustada."""
    warmup = window
    usable = len(candles) - warmup
    if usable <= folds * 50:
        raise ValueError("no hay suficientes velas para el walk-forward")
    size = usable // folds
    keys = list(grid)
    report = []
    for f in range(folds):
        seg_start = warmup + f * size
        seg_end = warmup + (f + 1) * size if f < folds - 1 else len(candles)
        split = seg_start + int((seg_end - seg_start) * train_ratio)
        best, best_score = None, -math.inf
        for combo in itertools.product(*(grid[k] for k in keys)):
            cfg = deepcopy(strat_cfg)
            for k, v in zip(keys, combo):
                setattr(cfg, k, v)
            if cfg.fast_ema >= cfg.slow_ema:
                continue
            res = run_backtest(candles[:split], cfg, risk_cfg, window, start=seg_start, timeframe=timeframe)
            score = res.sharpe if len(res.trades) >= min_trades else -math.inf
            if score > best_score:
                best, best_score = cfg, score
        if best is None:
            best = strat_cfg
        test = run_backtest(candles[:seg_end], best, risk_cfg, window, start=split, timeframe=timeframe)
        report.append(
            {
                "tramo": f + 1,
                "parametros": {k: getattr(best, k) for k in keys},
                "sharpe_entrenamiento": round(best_score, 2) if math.isfinite(best_score) else None,
                **{f"test_{k}": v for k, v in test.summary().items()},
            }
        )
    return report


# --------------------------------------------------------------------- datos
def fetch_history(exchange, symbol: str, timeframe: str, since_ms: int, cache_dir: str = "data") -> list[list[float]]:
    """Descarga velas históricas paginando, con caché en CSV."""
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"{symbol.replace('/', '_')}_{timeframe}_{since_ms}.csv")
    if os.path.exists(path):
        return load_csv(path)
    tf_ms = exchange.parse_timeframe(timeframe) * 1000
    out: list[list[float]] = []
    cursor = since_ms
    now_ms = int(time.time() * 1000)
    while cursor < now_ms - tf_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe, since=cursor, limit=1000)
        if not batch:
            break
        out.extend(k for k in batch if not out or k[0] > out[-1][0])
        cursor = batch[-1][0] + tf_ms
    out = [k for k in out if k[0] + tf_ms <= now_ms]  # solo velas cerradas
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(out)
    return out


def load_csv(path: str) -> list[list[float]]:
    with open(path, encoding="utf-8") as fh:
        return [[float(x) for x in row[:6]] for row in csv.reader(fh) if row and not row[0].startswith("t")]
