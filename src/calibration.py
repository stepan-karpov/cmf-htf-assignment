from __future__ import annotations

import itertools
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd
from tqdm.auto import tqdm

from .backtester import Backtester
from .strategy import Strategy


def _grid_worker(item: tuple) -> dict:
    strategy_cls, kw, backtester = item
    result = backtester.run(strategy_cls(**kw))
    row = dict(kw)
    row.update(result.summary())
    return row


def grid_search(
    strategy_cls: type[Strategy],
    param_grid: dict[str, list],
    backtester: Backtester,
    fixed_params: dict | None = None,
    n_jobs: int = 1,
) -> pd.DataFrame:
    """Full-factorial grid search over strategy parameters.

    Args:
        strategy_cls: Strategy subclass to instantiate for each combo.
        param_grid:   {param_name: [v1, v2, ...]} — axes of the grid.
        backtester:   Backtester instance (paths + execution model are reused).
        fixed_params: Parameters passed to every instantiation unchanged.
        n_jobs:       Worker processes. 1 = sequential (default); None = os.cpu_count().

    Returns:
        DataFrame with one row per parameter combination.
        Columns: grid parameter names + all keys from BacktestResult.summary().
        If param_grid has exactly one key, that key becomes the index.
    """
    fixed = fixed_params or {}
    keys = list(param_grid.keys())
    combos = [dict(zip(keys, c)) for c in itertools.product(*param_grid.values())]
    items = [(strategy_cls, {**fixed, **kw}, backtester) for kw in combos]

    if n_jobs == 1:
        rows = [_grid_worker(item) for item in tqdm(items, desc="grid_search")]
    else:
        ctx = mp.get_context("fork")
        with ProcessPoolExecutor(max_workers=n_jobs, mp_context=ctx) as ex:
            futures = [ex.submit(_grid_worker, item) for item in items]
            rows = []
            for fut in tqdm(as_completed(futures), total=len(futures), desc="grid_search"):
                rows.append(fut.result())

    df = pd.DataFrame(rows)
    if len(keys) == 1:
        df = df.set_index(keys[0])
    return df
