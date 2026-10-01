"""Estrategia de seguimiento de tendencia (solo largos, sin apalancamiento).

Reglas:
- Entrada: el escenario alcista (EMA rápida > EMA lenta Y cierre > EMA de tendencia)
  se ha activado en las últimas `entry_window` velas y sigue activo.
- Stop inicial: cierre - atr_stop_mult * ATR.
- Trailing stop: cierre - atr_trail_mult * ATR; solo puede subir.
- Salida: cruce bajista de las EMAs o cierre por debajo de la EMA de tendencia.

Recibe únicamente velas CERRADAS: la misma función se usa en backtest y en real.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .config import StrategyConfig
from .indicators import atr, ema


class HasStop(Protocol):
    stop: float


@dataclass
class Signal:
    action: str  # "buy" | "sell" | "hold"
    stop: float | None = None
    reason: str = ""


class TrendFollowingStrategy:
    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg

    @property
    def min_bars(self) -> int:
        c = self.cfg
        return max(c.slow_ema, c.trend_ema, c.atr_period) + c.entry_window + 2

    def evaluate(self, candles: list[list[float]], position: HasStop | None = None) -> Signal:
        c = self.cfg
        if len(candles) < self.min_bars:
            return Signal("hold", reason="datos insuficientes")
        highs = [k[2] for k in candles]
        lows = [k[3] for k in candles]
        closes = [k[4] for k in candles]
        fast = ema(closes, c.fast_ema)
        slow = ema(closes, c.slow_ema)
        trend = ema(closes, c.trend_ema)
        vol = atr(highs, lows, closes, c.atr_period)
        close, atr_v = closes[-1], vol[-1]
        if None in (fast[-1], slow[-1], trend[-1], atr_v) or atr_v <= 0:
            return Signal("hold", reason="indicadores no disponibles")

        if position is not None:
            if fast[-1] < slow[-1]:
                return Signal("sell", reason="cruce bajista de EMAs")
            if close < trend[-1]:
                return Signal("sell", reason="cierre bajo la EMA de tendencia")
            trailed = max(position.stop, close - c.atr_trail_mult * atr_v)
            return Signal("hold", stop=trailed, reason="trailing stop")

        def bullish(j: int) -> bool:
            return (
                fast[j] is not None and slow[j] is not None and trend[j] is not None
                and fast[j] > slow[j] and closes[j] > trend[j]
            )

        # Entrar solo cuando el escenario alcista ACABA de activarse (en cualquier orden:
        # cruce de EMAs o ruptura de la EMA de tendencia), no a mitad de un movimiento viejo.
        just_turned = any(bullish(-i) and not bullish(-i - 1) for i in range(1, c.entry_window + 1))
        if just_turned and bullish(-1):
            stop = close - c.atr_stop_mult * atr_v
            if stop > 0:
                return Signal("buy", stop=stop, reason="tendencia alcista recién confirmada")
        return Signal("hold", reason="sin señal")
