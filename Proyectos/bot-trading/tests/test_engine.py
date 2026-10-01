import os

from bot.broker import PaperBroker
from bot.engine import Engine
from bot.state import State
from bot.strategy import TrendFollowingStrategy

from .conftest import HOUR_MS, FakeExchange, down_then_up, make_candles


def _first_buy_index(cfg, candles):
    strat = TrendFollowingStrategy(cfg.strategy)
    for i in range(strat.min_bars, len(candles)):
        if strat.evaluate(candles[max(0, i - cfg.data.candles + 1) : i + 1]).action == "buy":
            return i
    raise AssertionError("sin señal de compra")


def _setup(cfg, state, alerter):
    all_candles = make_candles(down_then_up())
    i = _first_buy_index(cfg, all_candles)
    # El exchange devuelve las velas hasta i (cerradas) más la vela en formación i+1.
    ex = FakeExchange(all_candles[: i + 2])
    now = all_candles[i + 1][0] / 1000 + 600  # 10 minutos dentro de la vela en formación
    ex.price = all_candles[i][4]
    broker = PaperBroker(ex, state, "USDT", 10_000, cfg.risk.fee_rate, cfg.risk.slippage_pct)
    clock = {"t": now}
    engine = Engine(cfg, broker, state, alerter, clock=lambda: clock["t"])
    return engine, ex, broker, clock


def test_enters_with_stop_and_survives_restart(cfg, state, alerter):
    engine, ex, broker, clock = _setup(cfg, state, alerter)
    engine.step()
    pos = state.positions()["BTC/USDT"]
    assert pos.stop < pos.entry_price
    risk_taken = pos.qty * (pos.entry_price - pos.stop)
    assert risk_taken <= 10_000 * cfg.risk.risk_per_trade * 1.01
    assert os.path.exists(cfg.storage.heartbeat_file)

    # "Reinicio": un estado nuevo leído del mismo archivo recuerda la posición y el saldo.
    reopened = State(cfg.storage.db_path)
    assert reopened.positions()["BTC/USDT"].qty == pos.qty
    assert reopened.get_json("paper_balances")["BTC"] == pos.qty

    # Una segunda iteración no compra otra vez.
    engine.step()
    assert len([t for t in state.trades() if t.side == "buy"]) == 1


def test_stop_loss_exit(cfg, state, alerter):
    engine, ex, broker, clock = _setup(cfg, state, alerter)
    engine.step()
    pos = state.positions()["BTC/USDT"]
    ex.price = pos.stop * 0.99
    engine.step()
    assert "BTC/USDT" not in state.positions()
    last = state.trades(1)[0]
    assert last.side == "sell" and last.pnl < 0 and "stop" in last.reason


def test_kill_switch_liquidates(cfg, state, alerter):
    engine, ex, broker, clock = _setup(cfg, state, alerter)
    engine.step()
    open(cfg.storage.kill_switch_file, "w").close()
    engine.step()
    assert state.positions() == {}
    assert any("kill switch" in text for _, text in alerter.sent)
    engine.step()  # sigue quieto, sin volver a comprar
    assert state.positions() == {}


def test_reconcile_detects_externally_closed_position(cfg, state, alerter):
    engine, ex, broker, clock = _setup(cfg, state, alerter)
    engine.step()
    bal = broker.balances()
    bal["USDT"] += bal.pop("BTC") * ex.price  # alguien vendió a mano
    state.set("paper_balances", bal)
    engine.step()
    assert "BTC/USDT" not in state.positions()
    assert "fuera del bot" in state.trades(1)[0].reason


def test_stale_data_blocks_entries(cfg, state, alerter):
    engine, ex, broker, clock = _setup(cfg, state, alerter)
    clock["t"] += 5 * HOUR_MS / 1000  # el feed dejó de actualizarse hace horas
    engine.step()
    assert state.positions() == {}
    assert any("datos sospechosos" in text for _, text in alerter.sent)


def test_anomalous_price_blocks_entries(cfg, state, alerter):
    engine, ex, broker, clock = _setup(cfg, state, alerter)
    ex.price *= 1.5
    engine.step()
    assert state.positions() == {}
