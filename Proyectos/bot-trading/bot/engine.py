"""Motor principal: el bucle que opera, se protege y se recupera solo.

Cada iteración:
  1. Latido (archivo local + ping externo).
  2. Precios, saldos y reconciliación del estado interno con el exchange.
  3. Equity, límites de riesgo y kill switch.
  4. Por símbolo: comprobación de datos, stops, señales de salida y de entrada.
"""
from __future__ import annotations

import logging
import os
import signal
import time

import ccxt

from .broker import Broker, new_client_id
from .config import Config
from .risk import RiskManager
from .state import Position, State, Trade
from .strategy import TrendFollowingStrategy

log = logging.getLogger("bot.engine")

STOP_MOVE_MIN_PCT = 0.002  # no reemplazar el stop del exchange por cambios menores al 0,2 %


class Engine:
    def __init__(self, cfg: Config, broker: Broker, state: State, alerter, clock=time.time):
        self.cfg = cfg
        self.broker = broker
        self.state = state
        self.alerter = alerter
        self.clock = clock
        self.strategy = TrendFollowingStrategy(cfg.strategy)
        self.risk = RiskManager(cfg.risk)
        self.tf_seconds = ccxt.Exchange.parse_timeframe(cfg.timeframe)
        self.running = True
        self.consecutive_errors = 0

    # ------------------------------------------------------------------ bucle
    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)
        self.alerter.send("info", f"Bot iniciado en modo {self.cfg.mode.upper()} — {', '.join(self.cfg.symbols)}")
        self._startup_check()
        while self.running:
            started = time.time()
            try:
                self.step()
                self.consecutive_errors = 0
            except Exception as exc:  # noqa: BLE001 - el bucle nunca debe morir por un error puntual
                self.consecutive_errors += 1
                log.exception("Error en la iteración")
                if self.consecutive_errors == self.cfg.max_consecutive_errors:
                    self.alerter.send(
                        "critical",
                        f"{self.consecutive_errors} errores seguidos ({exc}). Modo seguro: sin nuevas entradas.",
                    )
            while self.running and time.time() - started < self.cfg.loop_seconds:
                time.sleep(1)
        self.alerter.send("info", "Bot detenido de forma ordenada. Las posiciones abiertas se conservan.")

    def _stop(self, *_):
        log.info("Señal de parada recibida")
        self.running = False

    def step(self) -> None:
        now = self.clock()
        self._heartbeat(now)

        positions = self.state.positions()
        symbols = list(dict.fromkeys(self.cfg.symbols + list(positions)))
        prices = {s: self.broker.fetch_price(s) for s in symbols}
        balances = self.broker.balances()
        self._reconcile(positions, balances, prices, now)
        positions = self.state.positions()

        equity = balances.get(self.cfg.quote_currency, 0.0) + sum(p.qty * prices[s] for s, p in positions.items())
        self.state.record_equity(now, equity)
        self._daily_report(now, equity, positions)

        status = self.risk.check(self.state, equity, now, os.path.exists(self.cfg.storage.kill_switch_file))
        if self.state.get("last_risk_reason") != status.reason:
            self.state.set("last_risk_reason", status.reason)
            if status.reason != "ok":
                self.alerter.send("critical" if status.must_liquidate else "warning", f"Riesgo: {status.reason}")
            else:
                self.alerter.send("info", "Riesgo: vuelve a estar todo en orden, se permiten entradas")
        if status.must_liquidate:
            for pos in positions.values():
                self._exit(pos, prices[pos.symbol], now, status.reason)
            return

        can_open = status.can_open and self.consecutive_errors < self.cfg.max_consecutive_errors
        failures = []
        for sym in symbols:
            try:
                self._process_symbol(sym, prices[sym], equity, can_open, now)
            except Exception as exc:  # noqa: BLE001 - un símbolo con problemas no frena a los demás
                log.exception("Error procesando %s", sym)
                failures.append(f"{sym}: {exc}")
        if failures:
            raise RuntimeError("; ".join(failures))

    # ------------------------------------------------------------- por símbolo
    def _process_symbol(self, sym: str, price: float, equity: float, can_open: bool, now: float) -> None:
        pos = self.state.positions().get(sym)

        # El stop se vigila con el precio actual, aunque los datos de velas fallen.
        if pos and price <= pos.stop:
            self._exit(pos, price, now, f"stop-loss ({pos.stop:.6g})")
            return

        candles = self.broker.fetch_candles(sym, self.cfg.timeframe, self.cfg.data.candles + 1)
        closed = self._closed_candles(candles, now)
        ok, why = self._data_ok(closed, price, now)
        if not ok:
            self.alerter.send("warning", f"{sym}: datos sospechosos ({why}); no se toman decisiones nuevas")
            return

        if pos:
            sig = self.strategy.evaluate(closed, pos)
            if sig.action == "sell":
                self._exit(pos, price, now, sig.reason)
            elif sig.stop and sig.stop > pos.stop:
                self._move_stop(pos, sig.stop)
            return

        if sym not in self.cfg.symbols or not can_open:
            return
        if len(self.state.positions()) >= self.cfg.risk.max_open_positions:
            return
        last_exit = self.state.get_float(f"last_exit:{sym}", 0.0)
        if now - last_exit < self.cfg.strategy.cooldown_bars * self.tf_seconds:
            return
        sig = self.strategy.evaluate(closed, None)
        if sig.action == "buy":
            self._enter(sym, price, sig.stop, equity, now, sig.reason)

    def _closed_candles(self, candles: list, now: float) -> list:
        """Descarta la vela en formación: la estrategia solo ve velas cerradas."""
        if candles and (candles[-1][0] / 1000 + self.tf_seconds) > now:
            candles = candles[:-1]
        return candles[-self.cfg.data.candles :]

    def _data_ok(self, closed: list, price: float, now: float) -> tuple[bool, str]:
        if len(closed) < self.strategy.min_bars:
            return False, f"solo {len(closed)} velas"
        if any(k[4] is None or k[4] <= 0 for k in closed[-5:]):
            return False, "precios no positivos"
        age = now - (closed[-1][0] / 1000 + self.tf_seconds)
        if age > self.cfg.data.max_staleness_bars * self.tf_seconds:
            return False, f"última vela cerrada hace {age / 60:.0f} min (feed congelado)"
        max_move = self.cfg.data.max_bar_move_pct
        last, prev = closed[-1][4], closed[-2][4]
        if abs(last / prev - 1) > max_move:
            return False, f"movimiento anómalo de {last / prev - 1:+.1%} en una vela"
        if abs(price / last - 1) > max_move:
            return False, f"precio actual {price} lejos del último cierre {last}"
        return True, ""

    # --------------------------------------------------------------- órdenes
    def _enter(self, sym: str, price: float, stop: float, equity: float, now: float, reason: str) -> None:
        if stop >= price * 0.999:
            return
        positions = self.state.positions()
        balances = self.broker.balances()
        exposure = sum(
            p.qty * (price if s == sym else p.entry_price) for s, p in positions.items()
        )
        qty = self.risk.position_size(equity, balances.get(self.cfg.quote_currency, 0.0), exposure, price, stop)
        qty = self.broker.normalize_qty(sym, qty, price)
        if qty <= 0:
            log.info("%s: señal de compra pero el tamaño queda por debajo del mínimo", sym)
            return
        client_id = new_client_id("buy")
        fill = self.broker.buy(sym, qty, client_id)
        pos = Position(sym, fill.qty, fill.price, fill.fee, stop, now)
        self.state.open_position(pos, Trade(now, sym, "buy", fill.qty, fill.price, fill.fee, None, reason, client_id))
        try:
            pos.stop_order_id = self.broker.place_stop(sym, fill.qty, stop)
            if pos.stop_order_id:
                self.state.save_position(pos)
        except Exception as exc:  # noqa: BLE001
            self.alerter.send("warning", f"{sym}: no se pudo colocar el stop en el exchange ({exc}); lo vigila el bot")
        risk_amt = fill.qty * (fill.price - stop)
        self.alerter.send(
            "info",
            f"COMPRA {sym}: {fill.qty:.6g} @ {fill.price:.6g} | stop {stop:.6g} | riesgo {risk_amt:.2f} "
            f"{self.cfg.quote_currency} ({reason})",
        )

    def _exit(self, pos: Position, price: float, now: float, reason: str) -> None:
        sym, base = pos.symbol, pos.symbol.split("/")[0]
        if pos.stop_order_id:
            self.broker.cancel_stop(sym, pos.stop_order_id)
        held = self.broker.balances().get(base, 0.0)
        qty = self.broker.normalize_qty(sym, min(pos.qty, held), price)
        if qty <= 0:
            if held < pos.qty * 0.5:
                # El stop del exchange ya saltó (o se vendió a mano): la reconciliación lo registra.
                self._reconcile({sym: pos}, {base: held}, {sym: price}, now)
            else:
                # Queda una cantidad por debajo del mínimo negociable: se deja de gestionar.
                self.state.close_position(sym, Trade(now, sym, "sell", 0.0, price, 0.0, None, f"{reason}; resto bajo el mínimo"))
                self.state.set(f"last_exit:{sym}", now)
                self.alerter.send("warning", f"{sym}: posición demasiado pequeña para venderse; se deja de gestionar")
            return
        client_id = new_client_id("sell")
        fill = self.broker.sell(sym, qty, client_id)
        pnl = fill.qty * (fill.price - pos.entry_price) - fill.fee - pos.entry_fee * (fill.qty / pos.qty)
        self.state.close_position(sym, Trade(now, sym, "sell", fill.qty, fill.price, fill.fee, pnl, reason, client_id))
        self.state.set(f"last_exit:{sym}", now)
        self.alerter.send(
            "info", f"VENTA {sym}: {fill.qty:.6g} @ {fill.price:.6g} | PnL {pnl:+.2f} {self.cfg.quote_currency} ({reason})"
        )

    def _move_stop(self, pos: Position, new_stop: float) -> None:
        if pos.stop_order_id:
            if new_stop < pos.stop * (1 + STOP_MOVE_MIN_PCT):
                return
            self.broker.cancel_stop(pos.symbol, pos.stop_order_id)
            pos.stop_order_id = None
            pos.stop = new_stop
            self.state.save_position(pos)  # guardar antes de colocar: si falla, el bot sigue vigilando
            try:
                pos.stop_order_id = self.broker.place_stop(pos.symbol, pos.qty, new_stop)
            except Exception as exc:  # noqa: BLE001
                self.alerter.send("warning", f"{pos.symbol}: no se pudo mover el stop en el exchange ({exc})")
        pos.stop = new_stop
        self.state.save_position(pos)

    # -------------------------------------------------------- reconciliación
    def _reconcile(self, positions: dict, balances: dict, prices: dict, now: float) -> None:
        """Compara lo que el bot cree tener con lo que hay realmente en la cuenta."""
        for sym, pos in positions.items():
            held = balances.get(sym.split("/")[0], 0.0)
            if held < pos.qty * 0.5:
                fill = self.broker.order_fill(sym, pos.stop_order_id) if pos.stop_order_id else None
                exit_price = fill.price if fill else min(pos.stop, prices.get(sym, pos.stop))
                fee = fill.fee if fill else pos.qty * exit_price * self.cfg.risk.fee_rate
                pnl = pos.qty * (exit_price - pos.entry_price) - fee - pos.entry_fee
                self.state.close_position(
                    sym, Trade(now, sym, "sell", pos.qty, exit_price, fee, pnl, "cerrada fuera del bot (stop del exchange o manual)")
                )
                self.state.set(f"last_exit:{sym}", now)
                self.alerter.send(
                    "warning", f"{sym}: la posición ya no está en la cuenta; registrada como cerrada (PnL aprox. {pnl:+.2f})"
                )
            elif held < pos.qty:
                pos.qty = held  # p. ej. comisiones cobradas en el activo base
                self.state.save_position(pos)

    def _startup_check(self) -> None:
        positions = self.state.positions()
        if positions:
            self.alerter.send("info", f"Retomando {len(positions)} posición(es) guardada(s): {', '.join(positions)}")
        if self.state.get("halted"):
            self.alerter.send("critical", f"El bot sigue detenido ({self.state.get('halted')}). Usa `reset-halt` para reanudar.")

    # ------------------------------------------------------------ monitoreo
    def _heartbeat(self, now: float) -> None:
        path = self.cfg.storage.heartbeat_file
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(str(now))
        self.alerter.ping_heartbeat()

    def _daily_report(self, now: float, equity: float, positions: dict) -> None:
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        if self.state.get("last_report_day") == day:
            return
        first = self.state.get("last_report_day") is None
        self.state.set("last_report_day", day)
        if first:
            return
        start = self.state.get_float("day_start_equity", equity)
        peak = self.state.get_float("peak_equity", equity)
        self.alerter.send(
            "info",
            f"Resumen diario — equity {equity:.2f} {self.cfg.quote_currency} "
            f"(ayer {equity - start:+.2f}), drawdown {1 - equity / peak:.1%}, posiciones: "
            f"{', '.join(positions) or 'ninguna'}",
        )
