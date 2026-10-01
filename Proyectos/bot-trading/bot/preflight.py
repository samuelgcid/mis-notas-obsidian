"""Comprobación previa: verifica que todo está listo antes de arrancar el bot."""
from __future__ import annotations

import os
import time

from .broker import normalize_qty
from .config import Config
from .indicators import atr
from .risk import RiskManager
from .strategy import TrendFollowingStrategy

OK, WARN, FAIL = "✅", "⚠️ ", "❌"


def run_checks(cfg: Config, exchange, alerter=None, send_test_alert: bool = False) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def add(level: str, msg: str) -> None:
        results.append((level, msg))

    add(OK, f"Configuración válida — modo {cfg.mode.upper()}, {cfg.exchange}, {cfg.timeframe}, {', '.join(cfg.symbols)}")
    if cfg.mode == "live":
        add(WARN if not cfg.sandbox else OK,
            "Dinero REAL (sandbox desactivado)" if not cfg.sandbox else "Live en TESTNET del exchange")

    # Carpeta de datos escribible (estado, logs, latido).
    data_dir = os.path.dirname(os.path.abspath(cfg.storage.db_path))
    try:
        os.makedirs(data_dir, exist_ok=True)
        probe = os.path.join(data_dir, ".write_test")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        add(OK, f"Carpeta de datos escribible: {data_dir}")
    except OSError as exc:
        add(FAIL, f"No se puede escribir en {data_dir}: {exc}")

    if os.path.exists(cfg.storage.kill_switch_file):
        add(WARN, "El kill switch está ACTIVO: el bot no operará (usa `python -m bot resume`)")

    # Conexión y mercados.
    try:
        exchange.load_markets()
        add(OK, f"Conexión con {cfg.exchange} correcta")
    except Exception as exc:  # noqa: BLE001
        add(FAIL, f"No se pudo conectar con {cfg.exchange}: {exc}")
        return results

    # Saldo.
    equity = cfg.paper_initial_balance
    if cfg.mode == "live":
        try:
            bal = exchange.fetch_balance()
            equity = float((bal.get("total") or {}).get(cfg.quote_currency) or 0)
            add(OK if equity > 0 else FAIL, f"Claves de API válidas — saldo {equity:.2f} {cfg.quote_currency}")
        except Exception as exc:  # noqa: BLE001
            add(FAIL, f"Las claves de API no funcionan: {exc}")
            return results

    strat = TrendFollowingStrategy(cfg.strategy)
    risk = RiskManager(cfg.risk)

    for sym in cfg.symbols:
        if sym not in (getattr(exchange, "markets", None) or {}):
            add(FAIL, f"{sym}: no existe en {cfg.exchange}")
            continue
        try:
            candles = exchange.fetch_ohlcv(sym, cfg.timeframe, limit=cfg.data.candles + 1)
            price = float(exchange.fetch_ticker(sym)["last"])
        except Exception as exc:  # noqa: BLE001
            add(FAIL, f"{sym}: no se pudieron leer datos ({exc})")
            continue
        if len(candles) < strat.min_bars + 1:
            add(FAIL, f"{sym}: solo {len(candles)} velas; hacen falta {strat.min_bars + 1}")
            continue
        tf = exchange.parse_timeframe(cfg.timeframe)
        age_bars = (time.time() - candles[-1][0] / 1000) / tf
        if age_bars > cfg.data.max_staleness_bars + 1:
            add(WARN, f"{sym}: la última vela tiene {age_bars:.0f} velas de antigüedad (¿mercado parado?)")
        # ¿Llega el capital al mínimo de orden con el riesgo configurado?
        closed = candles[:-1]
        a = atr([k[2] for k in closed], [k[3] for k in closed], [k[4] for k in closed], cfg.strategy.atr_period)[-1]
        stop = price - cfg.strategy.atr_stop_mult * (a or price * 0.02)
        qty = risk.position_size(equity, equity, 0.0, price, stop)
        norm = normalize_qty(exchange, sym, qty, price)
        if norm <= 0:
            add(FAIL, f"{sym}: con {equity:.2f} {cfg.quote_currency} la orden típica ({qty * price:.2f}) "
                      "queda por debajo del mínimo del exchange; sube el capital o el riesgo")
        else:
            add(OK, f"{sym}: precio {price:.6g}, orden típica ≈ {norm * price:.2f} {cfg.quote_currency} "
                    f"con stop a {(price - stop) / price:.1%}")

    # Alertas.
    if cfg.alerts.telegram_token and cfg.alerts.telegram_chat_id:
        if send_test_alert and alerter:
            alerter.send("info", "Mensaje de prueba del bot: las alertas funcionan.")
            add(OK, "Alerta de prueba enviada a Telegram (revisa tu móvil)")
        else:
            add(OK, "Telegram configurado")
    else:
        add(WARN, "Sin alertas de Telegram: no te enterarás de los problemas si no miras los logs")
    add(OK if cfg.alerts.heartbeat_url else WARN,
        "Heartbeat externo configurado" if cfg.alerts.heartbeat_url
        else "Sin heartbeat externo: si el servidor se apaga, nadie te avisará")
    return results


def print_report(results: list[tuple[str, str]]) -> bool:
    print("\n=== Comprobación previa ===\n")
    for level, msg in results:
        print(f"{level} {msg}")
    failed = any(level == FAIL for level, _ in results)
    print("\n" + ("❌ Hay problemas que resolver antes de arrancar." if failed else "✅ Listo para arrancar: `python -m bot run`"))
    return not failed
