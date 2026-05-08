from __future__ import annotations

import numpy as np


class OrderBook:
    """LOB snapshot, updated in-place as trades consume volume between snapshots."""

    __slots__ = ("bids", "asks", "timestamp_us")

    def __init__(self, bids: list[list[float]], asks: list[list[float]], timestamp_us: int = 0):
        self.bids = bids          # [[price, amount], ...] best-first (descending)
        self.asks = asks          # [[price, amount], ...] best-first (ascending)
        self.timestamp_us = timestamp_us

    @classmethod
    def from_arrays(
        cls,
        bid_p: np.ndarray, bid_a: np.ndarray,
        ask_p: np.ndarray, ask_a: np.ndarray,
        timestamp_us: int = 0,
    ) -> "OrderBook":
        """Fast construction from pre-extracted numpy row slices (no dict parsing)."""
        bp = bid_p.tolist(); ba = bid_a.tolist()
        ap = ask_p.tolist(); aa = ask_a.tolist()
        bids = [[bp[k], ba[k]] for k in range(len(bp))]
        asks = [[ap[k], aa[k]] for k in range(len(ap))]
        return cls(bids, asks, int(timestamp_us))

    def refresh(
        self,
        bid_p: np.ndarray, bid_a: np.ndarray,
        ask_p: np.ndarray, ask_a: np.ndarray,
        timestamp_us: int,
    ) -> None:
        """Update bids/asks in-place from numpy row slices — no object allocation."""
        bp = bid_p.tolist(); ba = bid_a.tolist()
        ap = ask_p.tolist(); aa = ask_a.tolist()
        for k in range(len(bp)):
            b = self.bids[k]; b[0] = bp[k]; b[1] = ba[k]
            a = self.asks[k]; a[0] = ap[k]; a[1] = aa[k]
        self.timestamp_us = timestamp_us

    @classmethod
    def from_row(cls, row: dict, n_levels: int = 25) -> "OrderBook":
        bids = [[row[f"bids[{i}].price"], row[f"bids[{i}].amount"]] for i in range(n_levels)]
        asks = [[row[f"asks[{i}].price"], row[f"asks[{i}].amount"]] for i in range(n_levels)]
        return cls(bids, asks, int(row["local_timestamp"]))

    @property
    def best_bid(self) -> float:
        return self.bids[0][0]

    @property
    def best_ask(self) -> float:
        return self.asks[0][0]

    @property
    def mid(self) -> float:
        return 0.5 * (self.bids[0][0] + self.asks[0][0])

    @property
    def spread(self) -> float:
        return self.asks[0][0] - self.bids[0][0]

    def apply_trade(self, trade_side: str, price: float, amount: float) -> None:
        """Consume trade volume from the book in-place."""
        levels = self.bids if trade_side == "sell" else self.asks
        remaining = amount
        for level in levels:
            if remaining <= 0:
                break
            if trade_side == "sell" and level[0] < price:
                break
            if trade_side == "buy" and level[0] > price:
                break
            consumed = min(level[1], remaining)
            level[1] -= consumed
            remaining -= consumed
