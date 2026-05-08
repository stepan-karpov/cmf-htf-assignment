from __future__ import annotations

import numpy as np
import pandas as pd

from .execution import ExecutionModel, Fill, Order, PessimisticExecution
from .orderbook import OrderBook
from .result import BacktestResult
from .strategy import Strategy

_N_LEVELS = 25
_BID_P_COLS  = [f"bids[{i}].price"  for i in range(_N_LEVELS)]
_BID_A_COLS  = [f"bids[{i}].amount" for i in range(_N_LEVELS)]
_ASK_P_COLS  = [f"asks[{i}].price"  for i in range(_N_LEVELS)]
_ASK_A_COLS  = [f"asks[{i}].amount" for i in range(_N_LEVELS)]


class Backtester:
    """Pure replay engine. Streams LOB + trade events in time order,
    delegates quote logic to Strategy and fill logic to ExecutionModel."""

    def __init__(
        self,
        lob_path: str,
        trades_path: str,
        execution_model: ExecutionModel | None = None,
        latency_ns: int = 0,
        log_interval_sec: float = 10.0,
        quote_log_stride: int = 50,
        capital: float = 1000.0,
    ):
        self.lob_path = lob_path
        self.trades_path = trades_path
        self.execution_model = execution_model or PessimisticExecution()
        self._latency_us = latency_ns // 1000
        self.log_interval_us = int(log_interval_sec * 1_000_000)
        self.quote_log_stride = max(1, int(quote_log_stride))
        self.capital = capital

    def run(self, strategy: Strategy) -> BacktestResult:
        lob = (
            pd.read_csv(self.lob_path)
            .sort_values("local_timestamp", kind="mergesort")
            .reset_index(drop=True)
        )
        trades = (
            pd.read_csv(self.trades_path, usecols=["local_timestamp", "side", "price", "amount"])
            .sort_values("local_timestamp", kind="mergesort")
            .reset_index(drop=True)
        )
        result = BacktestResult(capital=self.capital)
        self._run_loop(strategy, lob, trades, result)
        result._finalize()
        return result

    def _run_loop(
        self,
        strategy: Strategy,
        lob_df: pd.DataFrame,
        trades_df: pd.DataFrame,
        result: BacktestResult,
    ) -> None:
        lob_t = lob_df["local_timestamp"].to_numpy(np.int64)

        # Pre-extract all LOB levels as (n_lob, 25) arrays — avoids to_dict + per-row parsing
        lob_bid_p = lob_df[_BID_P_COLS].to_numpy(np.float64)
        lob_bid_a = lob_df[_BID_A_COLS].to_numpy(np.float64)
        lob_ask_p = lob_df[_ASK_P_COLS].to_numpy(np.float64)
        lob_ask_a = lob_df[_ASK_A_COLS].to_numpy(np.float64)

        tr_t      = trades_df["local_timestamp"].to_numpy(np.int64)
        tr_side   = trades_df["side"].to_numpy()
        tr_price  = trades_df["price"].to_numpy(np.float64)
        tr_amount = trades_df["amount"].to_numpy(np.float64)

        n_lob, n_tr = len(lob_t), len(tr_t)
        if n_lob == 0:
            raise ValueError("empty LOB data")

        cash              = 0.0
        inventory         = 0.0
        order_book        = OrderBook.from_arrays(
            lob_bid_p[0], lob_bid_a[0], lob_ask_p[0], lob_ask_a[0], lob_t[0]
        )
        active_orders: list[Order] = []
        pending_orders: list[Order] | None = None
        pending_active_at = 0
        last_log_us       = int(lob_t[0])
        lob_counter       = 0
        i = j = 0
        t_us = int(lob_t[0])

        while i < n_lob or j < n_tr:
            take_lob = (j >= n_tr) or (i < n_lob and lob_t[i] < tr_t[j])

            if take_lob:
                t_us = int(lob_t[i])
                order_book.refresh(lob_bid_p[i], lob_bid_a[i], lob_ask_p[i], lob_ask_a[i], t_us)
                new_orders = strategy.on_lob(order_book, inventory) or []
                if self._latency_us == 0:
                    active_orders = new_orders
                else:
                    pending_orders    = new_orders
                    pending_active_at = t_us + self._latency_us
                if lob_counter % self.quote_log_stride == 0:
                    result.add_quote(t_us, active_orders, order_book.mid)
                lob_counter += 1
                i += 1

            else:
                t_us = int(tr_t[j])
                if pending_orders is not None and t_us >= pending_active_at:
                    active_orders  = pending_orders
                    pending_orders = None
                fills, active_orders, order_book = self.execution_model.match(
                    active_orders, order_book,
                    tr_side[j], float(tr_price[j]), float(tr_amount[j]),
                )
                for fill in fills:
                    if fill.side == "bid":
                        cash      -= fill.price * fill.size
                        inventory += fill.size
                    else:
                        cash      += fill.price * fill.size
                        inventory -= fill.size
                    result.add_fill(t_us, fill, inventory)
                    strategy.on_fill(t_us, fill)
                j += 1

            if t_us - last_log_us >= self.log_interval_us:
                result.add_pnl_snapshot(t_us, cash + inventory * order_book.mid, inventory)
                last_log_us = t_us

        # Final markout
        cash += inventory * order_book.mid
        result.add_fill(t_us, Fill("markout", order_book.mid, -inventory), 0.0)
        result.add_pnl_snapshot(t_us, cash, 0.0)
