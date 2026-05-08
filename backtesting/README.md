# backtesting

C++ market-making backtester exposed to Python via pybind11.

The hot loop (CSV parsing, order matching, PnL accounting) runs entirely in C++.
Python is only used to define the strategy and read results.

---

## Build

```bash
cd backtesting
make          # produces _engine.<suffix>.so
make clean    # remove the .so
```

Requires: `clang++` with C++17, `pybind11`, Python headers.

---

## Usage

```python
from backtesting import Strategy, Backtester, OrderBook
from backtesting.visualize import BacktestResult

class MyStrategy(Strategy):
    def on_lob(self, ob: OrderBook, inventory: float) -> list[tuple]:
        ...
        return [("bid", bid_price, size), ("ask", ask_price, size)]

    def on_fill(self, t_us: int, side: str, price: float, size: float) -> None:
        pass  # optional

bt = Backtester("data/lob_train.csv", "data/trades_train.csv")
prefix = bt.run(MyStrategy(), output_path="results/my_run")

r = BacktestResult(prefix, capital=1000.0)
display(r.summary_df())
r.plot(tick_size=1e-7).show()
```

---

## Strategy API

### `on_lob(ob, inventory) → list[tuple]`

Called on every LOB snapshot. Return a list of `("bid"|"ask", price, size)` tuples.
Return `[]` to cancel all quotes (e.g. during warm-up).

`OrderBook` fields available from Python:

| Field | Type | Description |
|---|---|---|
| `ob.mid` | float | `(best_bid + best_ask) / 2` |
| `ob.best_bid` | float | top bid price |
| `ob.best_ask` | float | top ask price |
| `ob.spread` | float | `best_ask − best_bid` |
| `ob.timestamp_us` | int | event timestamp in microseconds |
| `ob.bids` | list[list] | 25 levels `[price, amount]`, descending |
| `ob.asks` | list[list] | 25 levels `[price, amount]`, ascending |

### `on_fill(t_us, side, price, size)`

Called after each fill. `side` is `"bid"`, `"ask"`, or `"markout"` (final position close).

---

## Backtester API

```python
Backtester(
    lob_path: str,
    trades_path: str,
    latency_ns: int = 0,          # order submission latency
    log_interval_sec: float = 10.0,
    quote_log_stride: int = 50,    # log quotes every N LOB events
)
prefix = bt.run(strategy, output_path="results/my_run")
```

`run()` writes three CSV files and returns the prefix:

| File | Columns | Logged when |
|---|---|---|
| `{prefix}_pnl.csv` | `t_us, pnl, inventory` | every `log_interval_sec` |
| `{prefix}_quotes.csv` | `t_us, bid, ask, mid` | every `quote_log_stride` LOB events |
| `{prefix}_fills.csv` | `t_us, side, price, size, inventory` | on each fill |

---

## BacktestResult API

```python
r = BacktestResult(prefix, capital=1000.0)
r.summary()      # dict: total_pnl, sharpe_annualized, max_drawdown, n_fills, ...
r.summary_df()   # MultiIndex DataFrame (PnL / Fills / Inventory)
r.plot(tick_size=1e-7)  # 4-panel Plotly figure
```

Plot panels: quote offsets from mid · PnL decomposition (spread capture vs inventory drift) · inventory · cumulative fill imbalance.

---

## File Structure

```
backtesting/
  __init__.py        # exports: Strategy, Backtester, OrderBook
  strategy.py        # Strategy base class (Python)
  backtester.py      # Thin wrapper: calls _engine.run(), returns prefix
  bindings.cpp       # THE ONLY file with pybind11 — PyStrategy + run()
  Makefile           # clang++ -O3 -std=c++17 → _engine*.so
  engine/
    orderbook.hpp    # OrderBook: refresh(), apply_trade(), queue_at()
    execution.hpp    # Order, Fill, PessimisticExecution
    strategy.hpp     # StrategyBase abstract class (pure C++)
    reader.hpp       # LobReader, TradeReader — streaming CSV parsers
    backtester.hpp   # Two-pointer merge loop
    result.hpp       # RunData accumulator + save_csv(prefix)
  visualize/
    __init__.py      # exports: BacktestResult
    result.py        # BacktestResult: reads CSVs → summary_df() + plot()
```

---

## Architecture

**Single seam.** `bindings.cpp` is the only file that includes pybind11.
`PyStrategy` wraps the Python strategy object and calls `on_lob` / `on_fill` across the boundary.
All other C++ files (`engine/`) are Python-free.

**Simulation loop** (`engine/backtester.hpp`): two-pointer merge of `LobReader` and `TradeReader`.
At each step the earlier event is consumed. Ties go to trades first (the LOB snapshot already reflects a post-trade state).

**Execution model** (`PessimisticExecution`): the strategy is assumed last-in-queue at its price level.
A fill triggers only when the incoming trade volume exceeds the LOB queue ahead of the order.
`apply_trade()` depletes the LOB in-place; `advance()` overwrites it on the next snapshot.

**CSV parsing** (`engine/reader.hpp`): header parsed once to build column index arrays.
Each row is read into a `std::string`, split into `string_view`s with no heap allocation,
then `strtod`/`strtoll` used directly on the view data pointers.
