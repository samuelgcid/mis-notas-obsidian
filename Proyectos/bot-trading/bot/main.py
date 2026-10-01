"""Línea de comandos: run, backtest, walkforward, status, kill, resume, reset-halt."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from .alerts import Alerter
from .backtest import fetch_history, load_csv, run_backtest, walk_forward
from .broker import CcxtBroker, PaperBroker, build_exchange
from .config import load_config
from .engine import Engine
from .state import State


def setup_logging(path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    stream_handler = logging.StreamHandler(sys.stdout)
    for h in (file_handler, stream_handler):
        h.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])


def cmd_run(cfg) -> None:
    setup_logging(cfg.storage.log_path)
    state = State(cfg.storage.db_path)
    if cfg.mode == "live":
        exchange = build_exchange(cfg, with_keys=True)
        broker = CcxtBroker(exchange, cfg.quote_currency, cfg.risk.fee_rate, cfg.exchange_stops)
    else:
        exchange = build_exchange(cfg, with_keys=False)  # solo datos públicos
        broker = PaperBroker(
            exchange, state, cfg.quote_currency, cfg.paper_initial_balance, cfg.risk.fee_rate, cfg.risk.slippage_pct
        )
    Engine(cfg, broker, state, Alerter(cfg.alerts)).run_forever()


def _load_candles(cfg, args):
    if args.csv:
        return load_csv(args.csv)
    since = int(datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc).timestamp() * 1000)
    return fetch_history(build_exchange(cfg, with_keys=False), args.symbol, cfg.timeframe, since)


def cmd_backtest(cfg, args) -> None:
    candles = _load_candles(cfg, args)
    res = run_backtest(candles, cfg.strategy, cfg.risk, cfg.data.candles, timeframe=cfg.timeframe)
    hold = candles[-1][4] / candles[0][4] - 1
    print(json.dumps({**res.summary(), "comprar_y_mantener": f"{hold:+.2%}"}, indent=2, ensure_ascii=False))


def cmd_walkforward(cfg, args) -> None:
    candles = _load_candles(cfg, args)
    grid = json.loads(args.grid)
    report = walk_forward(candles, cfg.strategy, cfg.risk, grid, args.folds, window=cfg.data.candles, timeframe=cfg.timeframe)
    print(json.dumps(report, indent=2, ensure_ascii=False))


def cmd_status(cfg) -> None:
    state = State(cfg.storage.db_path)
    hb = cfg.storage.heartbeat_file
    age = time.time() - float(open(hb).read()) if os.path.exists(hb) else None
    print(f"Modo: {cfg.mode} | Último latido: {'nunca' if age is None else f'hace {age:.0f}s'}")
    print(f"Kill switch: {'ACTIVO' if os.path.exists(cfg.storage.kill_switch_file) else 'no'}")
    print(f"Detenido: {state.get('halted') or 'no'} | Riesgo: {state.get('last_risk_reason') or '-'}")
    print(f"Equity máx.: {state.get('peak_equity')} | Equity inicio del día: {state.get('day_start_equity')}")
    if cfg.mode == "paper":
        print(f"Saldo simulado: {state.get_json('paper_balances')}")
    print("\nPosiciones abiertas:")
    for p in state.positions().values():
        print(f"  {p.symbol}: {p.qty:.6g} @ {p.entry_price:.6g}, stop {p.stop:.6g}")
    print("\nÚltimas operaciones:")
    for t in state.trades(10):
        when = datetime.fromtimestamp(t.ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        pnl = f" PnL {t.pnl:+.2f}" if t.pnl is not None else ""
        print(f"  {when} {t.side.upper()} {t.symbol} {t.qty:.6g} @ {t.price:.6g}{pnl} — {t.reason}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="bot", description="Bot de trading autosuficiente")
    p.add_argument("--config", default=os.environ.get("BOT_CONFIG", "config.yaml"))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="arranca el bucle de trading")
    for name in ("backtest", "walkforward"):
        sp = sub.add_parser(name)
        sp.add_argument("--symbol", default="BTC/USDT")
        sp.add_argument("--since", default="2023-01-01")
        sp.add_argument("--csv", help="CSV con velas: timestamp_ms,open,high,low,close,volume")
        if name == "walkforward":
            sp.add_argument("--folds", type=int, default=4)
            sp.add_argument(
                "--grid", default='{"fast_ema": [10, 20], "slow_ema": [50, 100], "atr_stop_mult": [2.0, 3.0]}'
            )
    sub.add_parser("status", help="estado, posiciones y últimas operaciones")
    sub.add_parser("kill", help="activa el kill switch: cierra todo y deja de operar")
    sub.add_parser("resume", help="desactiva el kill switch")
    sub.add_parser("reset-halt", help="reanuda tras una parada por drawdown (revisa antes qué pasó)")
    args = p.parse_args(argv)

    cfg = load_config(args.config if os.path.exists(args.config) else None)
    if args.cmd == "run":
        cmd_run(cfg)
    elif args.cmd == "backtest":
        cmd_backtest(cfg, args)
    elif args.cmd == "walkforward":
        cmd_walkforward(cfg, args)
    elif args.cmd == "status":
        cmd_status(cfg)
    elif args.cmd == "kill":
        os.makedirs(os.path.dirname(os.path.abspath(cfg.storage.kill_switch_file)), exist_ok=True)
        open(cfg.storage.kill_switch_file, "w").close()
        print("Kill switch activado: el bot cerrará posiciones y dejará de operar en la próxima iteración.")
    elif args.cmd == "resume":
        if os.path.exists(cfg.storage.kill_switch_file):
            os.remove(cfg.storage.kill_switch_file)
        print("Kill switch desactivado.")
    elif args.cmd == "reset-halt":
        state = State(cfg.storage.db_path)
        state.delete("halted")
        state.delete("peak_equity")  # el drawdown se mide desde el capital actual
        print("Parada por drawdown reiniciada.")


if __name__ == "__main__":
    main()
