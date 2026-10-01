"""Brokers: simulado (paper) y real (ccxt).

Los dos exponen la misma interfaz para que el motor no sepa con cuál opera.
"""
from __future__ import annotations

import logging
import math
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

import ccxt

log = logging.getLogger(__name__)


@dataclass
class Fill:
    qty: float
    price: float
    fee: float          # en moneda de cotización
    order_id: str | None = None


def new_client_id(side: str) -> str:
    # <= 36 caracteres alfanuméricos: compatible con la mayoría de exchanges.
    return f"bot{side[0]}{int(time.time())}{uuid.uuid4().hex[:12]}"


def with_retries(fn, *args, attempts: int = 4, base_delay: float = 2.0, **kwargs):
    """Reintenta errores de red (incluye rate limit y timeouts) con espera exponencial."""
    for i in range(attempts):
        try:
            return fn(*args, **kwargs)
        except ccxt.NetworkError as exc:
            if i == attempts - 1:
                raise
            delay = base_delay * 2**i
            log.warning("Error de red (%s); reintento en %.0fs", exc, delay)
            time.sleep(delay)


def build_exchange(cfg, with_keys: bool):
    klass = getattr(ccxt, cfg.exchange)
    params = {"enableRateLimit": True, "options": {"defaultType": "spot"}}
    if with_keys:
        params.update(apiKey=cfg.api_key, secret=cfg.api_secret)
        if cfg.api_password:
            params["password"] = cfg.api_password
    exchange = klass(params)
    if with_keys and cfg.sandbox:
        exchange.set_sandbox_mode(True)
    return exchange


def normalize_qty(market_data, symbol: str, qty: float, price: float) -> float:
    """Ajusta la cantidad a la precisión y mínimos del mercado; 0 si no llega al mínimo."""
    if qty <= 0:
        return 0.0
    try:
        market = market_data.market(symbol)
        qty = float(market_data.amount_to_precision(symbol, qty))
        limits = market.get("limits", {})
        min_amount = (limits.get("amount") or {}).get("min") or 0
        min_cost = (limits.get("cost") or {}).get("min") or 0
        if qty < min_amount or qty * price < min_cost:
            return 0.0
        return qty
    except ccxt.InvalidOrder:
        return 0.0  # ccxt lanza esto cuando la cantidad redondeada queda por debajo de la precisión
    except (AttributeError, KeyError, ccxt.BadSymbol):
        return math.floor(qty * 1e8) / 1e8


class Broker(ABC):
    quote: str

    def __init__(self, market_data, quote: str):
        self.md = market_data
        self.quote = quote
        self._markets_loaded = False

    # --- datos de mercado (comunes) ---------------------------------------
    def fetch_candles(self, symbol: str, timeframe: str, limit: int) -> list[list[float]]:
        return with_retries(self.md.fetch_ohlcv, symbol, timeframe, limit=limit)

    def fetch_price(self, symbol: str) -> float:
        ticker = with_retries(self.md.fetch_ticker, symbol)
        price = ticker.get("last") or ticker.get("close")
        if not price or price <= 0:
            raise ValueError(f"precio inválido para {symbol}: {price}")
        return float(price)

    def normalize_qty(self, symbol: str, qty: float, price: float) -> float:
        if not self._markets_loaded:
            try:
                with_retries(self.md.load_markets)
            except AttributeError:
                pass
            self._markets_loaded = True
        return normalize_qty(self.md, symbol, qty, price)

    # --- operativa ---------------------------------------------------------
    @abstractmethod
    def balances(self) -> dict[str, float]: ...

    @abstractmethod
    def buy(self, symbol: str, qty: float, client_id: str) -> Fill: ...

    @abstractmethod
    def sell(self, symbol: str, qty: float, client_id: str) -> Fill: ...

    def place_stop(self, symbol: str, qty: float, stop: float) -> str | None:
        return None  # por defecto el stop lo vigila el propio bot

    def cancel_stop(self, symbol: str, order_id: str) -> None:
        return None

    def order_fill(self, symbol: str, order_id: str) -> Fill | None:
        return None


class PaperBroker(Broker):
    """Simula ejecuciones con precios reales, comisiones y deslizamiento.
    El saldo simulado se persiste en el `State` para sobrevivir a reinicios."""

    def __init__(self, market_data, state, quote: str, initial_balance: float, fee_rate: float, slippage_pct: float):
        super().__init__(market_data, quote)
        self.state = state
        self.fee_rate = fee_rate
        self.slippage_pct = slippage_pct
        if self.state.get_json("paper_balances") is None:
            self.state.set("paper_balances", {quote: initial_balance})

    def balances(self) -> dict[str, float]:
        return dict(self.state.get_json("paper_balances", {}))

    def _apply(self, deltas: dict[str, float]) -> None:
        bal = self.balances()
        for asset, delta in deltas.items():
            bal[asset] = bal.get(asset, 0.0) + delta
            if bal[asset] < -1e-9:
                raise ValueError(f"saldo simulado insuficiente de {asset}")
            bal[asset] = max(bal[asset], 0.0)
        self.state.set("paper_balances", bal)

    def buy(self, symbol: str, qty: float, client_id: str) -> Fill:
        base = symbol.split("/")[0]
        price = self.fetch_price(symbol) * (1 + self.slippage_pct)
        fee = qty * price * self.fee_rate
        self._apply({self.quote: -(qty * price + fee), base: qty})
        return Fill(qty, price, fee, client_id)

    def sell(self, symbol: str, qty: float, client_id: str) -> Fill:
        base = symbol.split("/")[0]
        price = self.fetch_price(symbol) * (1 - self.slippage_pct)
        fee = qty * price * self.fee_rate
        self._apply({base: -qty, self.quote: qty * price - fee})
        return Fill(qty, price, fee, client_id)


class CcxtBroker(Broker):
    """Ejecución real vía ccxt, con órdenes idempotentes (clientOrderId) y stops en el exchange."""

    def __init__(self, exchange, quote: str, fee_rate: float, use_exchange_stops: bool):
        super().__init__(exchange, quote)
        self.ex = exchange
        self.fee_rate = fee_rate
        self.use_exchange_stops = use_exchange_stops

    def balances(self) -> dict[str, float]:
        bal = with_retries(self.ex.fetch_balance)
        return {k: float(v or 0) for k, v in (bal.get("total") or {}).items()}

    def buy(self, symbol: str, qty: float, client_id: str) -> Fill:
        return self._market_order(symbol, "buy", qty, client_id)

    def sell(self, symbol: str, qty: float, client_id: str) -> Fill:
        return self._market_order(symbol, "sell", qty, client_id)

    def _market_order(self, symbol: str, side: str, qty: float, client_id: str) -> Fill:
        params = {"clientOrderId": client_id}
        order = None
        for attempt in range(4):
            try:
                order = self.ex.create_order(symbol, "market", side, qty, None, params)
                break
            except ccxt.NetworkError as exc:
                # La orden pudo llegar al exchange aunque la respuesta se perdiera:
                # antes de reenviarla, comprobamos si ya existe (idempotencia).
                log.warning("Error de red creando orden %s (%s)", client_id, exc)
                time.sleep(2 * 2**attempt)
                order = self._find_by_client_id(symbol, client_id)
                if order:
                    break
        if order is None:
            raise RuntimeError(f"no se pudo crear la orden {client_id}")
        order = self._wait_filled(symbol, order)
        return self._to_fill(symbol, order, side)

    def _find_by_client_id(self, symbol: str, client_id: str):
        since = int((time.time() - 3600) * 1000)
        try:
            if self.ex.has.get("fetchOrders"):
                orders = self.ex.fetch_orders(symbol, since)
            else:
                orders = self.ex.fetch_open_orders(symbol, since) + self.ex.fetch_closed_orders(symbol, since)
        except ccxt.BaseError as exc:
            log.warning("No se pudo comprobar la orden %s: %s", client_id, exc)
            return None
        for o in orders:
            if o.get("clientOrderId") == client_id:
                return o
        return None

    def _wait_filled(self, symbol: str, order: dict, attempts: int = 10) -> dict:
        for _ in range(attempts):
            if order.get("status") == "closed" and order.get("filled"):
                return order
            time.sleep(1)
            order = with_retries(self.ex.fetch_order, order["id"], symbol)
        if not order.get("filled"):
            raise RuntimeError(f"la orden {order.get('id')} no se ejecutó")
        return order

    def _to_fill(self, symbol: str, order: dict, side: str) -> Fill:
        base = symbol.split("/")[0]
        filled = float(order["filled"])
        price = float(order.get("average") or order.get("price") or self.fetch_price(symbol))
        fee = filled * price * self.fee_rate
        fee_info = order.get("fee") or {}
        if fee_info.get("cost") is not None:
            if fee_info.get("currency") == self.quote:
                fee = float(fee_info["cost"])
            elif fee_info.get("currency") == base:
                fee = float(fee_info["cost"]) * price
                if side == "buy":
                    filled -= float(fee_info["cost"])  # la comisión se descontó del activo recibido
        return Fill(filled, price, fee, order.get("id"))

    def place_stop(self, symbol: str, qty: float, stop: float) -> str | None:
        if not self.use_exchange_stops or not self.ex.has.get("createStopLossOrder"):
            return None
        stop = float(self.ex.price_to_precision(symbol, stop))
        order = with_retries(self.ex.create_stop_loss_order, symbol, "market", "sell", qty, None, stop)
        return order.get("id")

    def cancel_stop(self, symbol: str, order_id: str) -> None:
        try:
            with_retries(self.ex.cancel_order, order_id, symbol)
        except ccxt.OrderNotFound:
            pass  # ya ejecutada o cancelada

    def order_fill(self, symbol: str, order_id: str) -> Fill | None:
        try:
            order = with_retries(self.ex.fetch_order, order_id, symbol)
        except ccxt.BaseError:
            return None
        if not order.get("filled"):
            return None
        return self._to_fill(symbol, order, "sell")
