"""Indicadores técnicos en Python puro (sin dependencias)."""
from __future__ import annotations


def ema(values: list[float], period: int) -> list[float | None]:
    """Media móvil exponencial, sembrada con la media simple de las primeras `period` velas."""
    n = len(values)
    if period <= 0 or n < period:
        return [None] * n
    k = 2 / (period + 1)
    out: list[float | None] = [None] * (period - 1)
    prev = sum(values[:period]) / period
    out.append(prev)
    for v in values[period:]:
        prev = prev + k * (v - prev)
        out.append(prev)
    return out


def atr(highs: list[float], lows: list[float], closes: list[float], period: int) -> list[float | None]:
    """Average True Range con el suavizado de Wilder."""
    n = len(closes)
    out: list[float | None] = [None] * n
    if period <= 0 or n <= period:
        return out
    tr = [highs[0] - lows[0]]
    for i in range(1, n):
        prev_close = closes[i - 1]
        tr.append(max(highs[i] - lows[i], abs(highs[i] - prev_close), abs(lows[i] - prev_close)))
    value = sum(tr[1 : period + 1]) / period
    out[period] = value
    for i in range(period + 1, n):
        value = (value * (period - 1) + tr[i]) / period
        out[i] = value
    return out
