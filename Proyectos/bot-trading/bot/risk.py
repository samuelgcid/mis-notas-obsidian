"""Gestión de riesgo: tamaño de posición y límites globales (pérdida diaria, drawdown, kill switch)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .config import RiskConfig


@dataclass
class RiskStatus:
    can_open: bool          # se permiten nuevas entradas
    must_liquidate: bool    # hay que cerrar todo y quedarse quieto
    reason: str


class RiskManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg

    def position_size(self, equity: float, cash: float, exposure: float, entry: float, stop: float) -> float:
        """Cantidad a comprar para arriesgar `risk_per_trade` del capital hasta el stop,
        recortada por los límites de posición, exposición total y efectivo disponible."""
        c = self.cfg
        if equity <= 0 or entry <= 0 or stop <= 0 or stop >= entry:
            return 0.0
        # La pérdida real al tocar el stop incluye comisiones y deslizamiento de ida y vuelta.
        per_unit_loss = (entry - stop) + entry * 2 * (c.fee_rate + c.slippage_pct)
        qty = equity * c.risk_per_trade / per_unit_loss
        qty = min(qty, equity * c.max_position_pct / entry)
        qty = min(qty, max(0.0, equity * c.max_total_exposure_pct - exposure) / entry)
        qty = min(qty, max(0.0, cash) / (entry * (1 + c.fee_rate + c.slippage_pct)))
        return max(qty, 0.0)

    def check(self, state, equity: float, now: float, kill_switch: bool) -> RiskStatus:
        """Actualiza máximos y equity de inicio del día en `state` y decide si se puede operar."""
        day = datetime.fromtimestamp(now, tz=timezone.utc).date().isoformat()
        if state.get("day") != day:
            state.set("day", day)
            state.set("day_start_equity", equity)
        peak = max(state.get_float("peak_equity", equity), equity)
        state.set("peak_equity", peak)

        if kill_switch:
            return RiskStatus(False, True, "kill switch activado")
        halted = state.get("halted")
        if halted:
            return RiskStatus(False, True, f"bot detenido: {halted}")

        drawdown = 1 - equity / peak if peak > 0 else 0.0
        if drawdown >= self.cfg.max_drawdown_pct:
            reason = f"drawdown {drawdown:.1%} >= límite {self.cfg.max_drawdown_pct:.1%}"
            state.set("halted", reason)
            return RiskStatus(False, True, f"bot detenido: {reason}")

        day_start = state.get_float("day_start_equity", equity)
        daily_loss = 1 - equity / day_start if day_start > 0 else 0.0
        if daily_loss >= self.cfg.max_daily_loss_pct:
            return RiskStatus(False, False, f"pérdida diaria {daily_loss:.1%}: sin nuevas entradas hasta mañana (UTC)")
        return RiskStatus(True, False, "ok")
