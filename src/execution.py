from __future__ import annotations

from dataclasses import dataclass

from .orderbook import OrderBook


@dataclass
class Order:
    side: str    # 'bid' | 'ask'
    price: float
    size: float


@dataclass
class Fill:
    side: str
    price: float
    size: float


class ExecutionModel:
    def match(
        self,
        active_orders: list[Order],
        order_book: OrderBook,
        trade_side: str,
        trade_price: float,
        trade_amount: float,
    ) -> tuple[list[Fill], list[Order], OrderBook]:
        raise NotImplementedError


class PessimisticExecution(ExecutionModel):
    """We are last in queue at our price level.

    Looks up the current LOB volume at our price to determine queue size.
    Fill happens only if the trade volume exceeds that queue.
    The order book is updated in-place after matching.
    """

    def match(self, active_orders, order_book, trade_side, trade_price, trade_amount):
        fills = []
        remaining_orders = []

        our_bid = next((o for o in active_orders if o.side == "bid"), None)
        our_ask = next((o for o in active_orders if o.side == "ask"), None)

        if our_bid and trade_side == "sell" and trade_price <= our_bid.price:
            queue = next((lvl[1] for lvl in order_book.bids if lvl[0] == our_bid.price), 0.0)
            leftover = trade_amount - queue
            if leftover > 0:
                fills.append(Fill("bid", our_bid.price, min(our_bid.size, leftover)))
            else:
                remaining_orders.append(our_bid)
        elif our_bid:
            remaining_orders.append(our_bid)

        if our_ask and trade_side == "buy" and trade_price >= our_ask.price:
            queue = next((lvl[1] for lvl in order_book.asks if lvl[0] == our_ask.price), 0.0)
            leftover = trade_amount - queue
            if leftover > 0:
                fills.append(Fill("ask", our_ask.price, min(our_ask.size, leftover)))
            else:
                remaining_orders.append(our_ask)
        elif our_ask:
            remaining_orders.append(our_ask)

        order_book.apply_trade(trade_side, trade_price, trade_amount)
        return fills, remaining_orders, order_book
