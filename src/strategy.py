from __future__ import annotations

from .execution import Fill, Order
from .orderbook import OrderBook


class Strategy:
    def on_lob(self, order_book: OrderBook, inventory: float) -> list[Order]:
        """Called on every LOB snapshot.

        Args:
            order_book: current book state (updated by trades since last snapshot).
            inventory:  current signed position.

        Returns:
            List of Orders to keep active until the next LOB event.
            Return [] to pull all quotes.
        """
        raise NotImplementedError

    def on_fill(self, t_us: int, fill: Fill) -> None:
        """Called after each fill."""
