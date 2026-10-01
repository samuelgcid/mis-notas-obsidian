import pytest

from bot.backtest import run_backtest, walk_forward
from bot.config import Config, RiskConfig, StrategyConfig, validate
from bot.indicators import atr, ema
from bot.risk import RiskManager
from bot.strategy import TrendFollowingStrategy

from .conftest import down_then_up, make_candles


def test_ema_known_values():
    out = ema([1, 2, 3, 4, 5], 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)
    assert out[3] == pytest.approx(3.0)
    assert out[4] == pytest.approx(4.0)


def test_atr_constant_range():
    n = 30
    out = atr([11.0] * n, [9.0] * n, [10.0] * n, 14)
    assert out[13] is None
    assert out[-1] == pytest.approx(2.0)


def test_position_size_risks_one_percent():
    r = RiskManager(RiskConfig(fee_rate=0, slippage_pct=0, max_position_pct=1, max_total_exposure_pct=1))
    qty = r.position_size(equity=10_000, cash=10_000, exposure=0, entry=100, stop=95)
    assert qty * 5 == pytest.approx(100)  # perder hasta el stop = 1 % de 10 000


def test_position_size_respects_caps():
    r = RiskManager(RiskConfig())
    assert r.position_size(10_000, 10_000, 0, 100, 99.9) * 100 <= 2_500 + 1e-6  # tope 25 %
    assert r.position_size(10_000, 10_000, 6_000, 100, 95) == 0  # exposición total agotada
    assert r.position_size(10_000, 50, 0, 100, 95) * 100 < 50  # sin efectivo suficiente
    assert r.position_size(10_000, 10_000, 0, 100, 101) == 0  # stop por encima del precio


def test_drawdown_halts_and_persists(state):
    r = RiskManager(RiskConfig(max_drawdown_pct=0.10))
    assert r.check(state, 10_000, 0, False).can_open
    status = r.check(state, 8_900, 60, False)
    assert status.must_liquidate and "drawdown" in status.reason
    assert r.check(state, 10_000, 120, False).must_liquidate  # sigue parado aunque se recupere


def test_daily_loss_pauses_entries_until_next_day(state):
    r = RiskManager(RiskConfig(max_daily_loss_pct=0.03, max_drawdown_pct=0.5))
    r.check(state, 10_000, 0, False)
    status = r.check(state, 9_600, 3600, False)
    assert not status.can_open and not status.must_liquidate
    assert r.check(state, 9_600, 86_400 + 10, False).can_open  # nuevo día UTC


def test_kill_switch(state):
    assert RiskManager(RiskConfig()).check(state, 10_000, 0, True).must_liquidate


def test_strategy_buys_when_trend_turns_with_stop_below_price():
    strat = TrendFollowingStrategy(StrategyConfig())
    candles = make_candles(down_then_up())
    buys = [i for i in range(strat.min_bars, len(candles)) if strat.evaluate(candles[: i + 1]).action == "buy"]
    assert buys, "debería aparecer una señal de compra en la subida"
    sig = strat.evaluate(candles[: buys[0] + 1])
    assert 0 < sig.stop < candles[buys[0]][4]


def test_backtest_profits_in_clear_trend_and_is_deterministic():
    candles = make_candles(down_then_up(260, 400))
    a = run_backtest(candles, StrategyConfig(), RiskConfig())
    b = run_backtest(candles, StrategyConfig(), RiskConfig())
    assert a.trades and a.total_return > 0
    assert a.equity_curve == b.equity_curve
    assert a.max_drawdown < 0.15


def test_walk_forward_runs():
    closes = down_then_up(260, 300) + down_then_up(200, 300, start=200)
    report = walk_forward(make_candles(closes), StrategyConfig(), RiskConfig(), {"fast_ema": [10, 20]}, folds=2)
    assert len(report) == 2 and "test_retorno_total" in report[0]


def test_config_blocks_live_without_confirmation(monkeypatch):
    c = Config(mode="live", api_key="k", api_secret="s")
    monkeypatch.delenv("BOT_CONFIRM_LIVE", raising=False)
    with pytest.raises(ValueError, match="BOT_CONFIRM_LIVE"):
        validate(c)
    monkeypatch.setenv("BOT_CONFIRM_LIVE", "yes")
    validate(c)


def test_config_rejects_wrong_quote():
    with pytest.raises(ValueError):
        validate(Config(symbols=["BTC/EUR"]))
