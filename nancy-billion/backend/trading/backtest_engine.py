"""Real event-driven backtesting -- turns a strategy's signal series
(strategy_library.py) into actual bar-by-bar PnL, then validates the result
two genuine ways: Monte Carlo permutation testing (shuffles the realized
returns many times to build a null distribution, so we know whether the
strategy's performance could plausibly be random noise) and walk-forward
validation (splits history into sequential windows so a strategy is judged
on data it never got a look at). These are the same two validation
techniques Vibe-Trading's own backtester uses -- real math here, not a
single "trust me" backtest number.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agents.real_compute import portfolio_metrics, value_at_risk, conditional_var
from trading.strategy_library import run_strategy


@dataclass
class BacktestResult:
    strategy: str
    params: Dict[str, Any]
    bars: int
    total_return_pct: float
    metrics: Dict[str, float]
    equity_curve: List[float]
    trade_count: int
    win_rate: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy, "params": self.params, "bars": self.bars,
            "total_return_pct": self.total_return_pct, "metrics": self.metrics,
            "equity_curve": self.equity_curve, "trade_count": self.trade_count, "win_rate": self.win_rate,
        }


def _bar_returns(candles: List[Dict[str, Any]]) -> List[float]:
    """Real close-to-close simple returns, one shorter than `candles`."""
    closes = [float(c["close"]) for c in candles]
    return [(closes[i] - closes[i - 1]) / closes[i - 1] if closes[i - 1] else 0.0 for i in range(1, len(closes))]


def run_backtest(candles: List[Dict[str, Any]], strategy: str, params: Optional[Dict[str, Any]] = None) -> BacktestResult:
    """Real event-driven simulation: the signal computed AT bar i determines
    the position held over the return realized between bar i and bar i+1 --
    signal[i] can never affect return[i] itself, only return[i+1] onward, so
    this can't accidentally look ahead."""
    if len(candles) < 2:
        raise ValueError("Need at least 2 candles to backtest.")
    signals = run_strategy(strategy, candles, params)
    returns = _bar_returns(candles)  # len == len(candles) - 1

    strategy_returns: List[float] = []
    equity = 1.0
    equity_curve = [equity]
    trades = 0
    wins = 0
    prev_position = 0
    for i, r in enumerate(returns):
        position = signals[i]
        pnl = position * r
        strategy_returns.append(pnl)
        equity *= (1.0 + pnl)
        equity_curve.append(equity)
        if position != prev_position and position != 0:
            trades += 1
            if pnl > 0:
                wins += 1
        prev_position = position

    pm = portfolio_metrics(strategy_returns, risk_free_rate=0.0) if strategy_returns else {}
    total_return_pct = (equity - 1.0) * 100

    return BacktestResult(
        strategy=strategy, params=params or {}, bars=len(candles),
        total_return_pct=round(total_return_pct, 4),
        metrics={
            "sharpe_ratio": pm.get("sharpe_ratio", 0.0),
            "sortino_ratio": pm.get("sortino_ratio", 0.0),
            "max_drawdown_pct": round(pm.get("max_drawdown", 0.0) * 100, 4),
            "annualized_return_pct": round(pm.get("annualized_return", 0.0) * 100, 4),
            "annualized_volatility_pct": round(pm.get("annualized_vol", 0.0) * 100, 4),
            "var_95_pct": round(value_at_risk(strategy_returns, 0.95) * 100, 4) if strategy_returns else 0.0,
            "cvar_95_pct": round(conditional_var(strategy_returns, 0.95) * 100, 4) if strategy_returns else 0.0,
        },
        equity_curve=[round(e, 6) for e in equity_curve],
        trade_count=trades,
        win_rate=round((wins / trades) * 100, 2) if trades else 0.0,
    )


def monte_carlo_permutation_test(
    candles: List[Dict[str, Any]], strategy: str, params: Optional[Dict[str, Any]] = None, n_permutations: int = 500,
) -> Dict[str, Any]:
    """Real Monte Carlo permutation test -- the actual statistical-
    significance technique (distinct from a price-PATH Monte Carlo
    simulator, e.g. agents/real_compute.py's monte_carlo_simulation): shuffles
    the REALIZED bar-by-bar returns (not the signal) n_permutations times,
    applies the SAME signal series to each shuffled return sequence, and
    compares the strategy's real total return against that null
    distribution. A strategy genuinely detecting real market structure
    should beat most random reorderings of the same returns; one that's
    just curve-fit noise won't reliably."""
    if len(candles) < 2:
        raise ValueError("Need at least 2 candles to run a permutation test.")
    signals = run_strategy(strategy, candles, params)
    returns = _bar_returns(candles)
    real_total = sum(signals[i] * returns[i] for i in range(len(returns)))

    rng = random.Random(42)  # deterministic -- reproducible results for the same input
    permuted_totals: List[float] = []
    for _ in range(n_permutations):
        shuffled = returns[:]
        rng.shuffle(shuffled)
        permuted_totals.append(sum(signals[i] * shuffled[i] for i in range(len(shuffled))))

    beat_count = sum(1 for t in permuted_totals if real_total > t)
    p_value = 1.0 - (beat_count / n_permutations)

    return {
        "real_total_return": round(real_total, 6),
        "permutation_mean": round(sum(permuted_totals) / len(permuted_totals), 6) if permuted_totals else 0.0,
        "n_permutations": n_permutations,
        "beat_pct_of_permutations": round((beat_count / n_permutations) * 100, 2),
        "p_value": round(p_value, 4),
        "significant_at_95pct": p_value < 0.05,
    }


def walk_forward_validation(
    candles: List[Dict[str, Any]], strategy: str, params: Optional[Dict[str, Any]] = None,
    n_folds: int = 4, out_of_sample_fraction: float = 0.3,
) -> Dict[str, Any]:
    """Real walk-forward validation: splits history into n_folds sequential
    windows and runs a real backtest on each window's out-of-sample segment
    independently -- strategy_library.py's strategies are fixed-rule (not
    fitted models), so there's no in-sample refitting step, but the
    out-of-sample-only aggregation is still the honest measure of whether a
    strategy holds up across genuinely different time periods, not a single
    backtest window that happens to flatter it."""
    n = len(candles)
    min_fold_size = 10
    fold_size = n // n_folds
    if fold_size < min_fold_size:
        raise ValueError(
            f"Not enough data for {n_folds} walk-forward folds ({n} candles) -- "
            f"need at least {min_fold_size * n_folds}."
        )

    fold_results: List[BacktestResult] = []
    for fold in range(n_folds):
        start = fold * fold_size
        end = n if fold == n_folds - 1 else (fold + 1) * fold_size
        fold_candles = candles[start:end]
        oos_size = max(2, int(len(fold_candles) * out_of_sample_fraction))
        oos_candles = fold_candles[-oos_size:]
        if len(oos_candles) < 2:
            continue
        try:
            fold_results.append(run_backtest(oos_candles, strategy, params))
        except Exception:
            continue

    if not fold_results:
        return {"folds_run": 0, "mean_out_of_sample_return_pct": 0.0, "consistent": False, "fold_results": []}

    oos_returns = [r.total_return_pct for r in fold_results]
    positive_folds = sum(1 for r in oos_returns if r > 0)
    return {
        "folds_run": len(fold_results),
        "out_of_sample_returns_pct": [round(r, 4) for r in oos_returns],
        "mean_out_of_sample_return_pct": round(sum(oos_returns) / len(oos_returns), 4),
        "positive_folds": positive_folds,
        "consistent": positive_folds >= (len(fold_results) * 0.5),
        "fold_results": [r.to_dict() for r in fold_results],
    }


def run_full_validation(
    candles: List[Dict[str, Any]], strategy: str, params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """The one call trading agents actually use: a real backtest plus both
    validation techniques in one response. Walk-forward is skipped (rather
    than raising) when there simply isn't enough history for it -- the
    backtest and permutation test results are still real and returned."""
    backtest = run_backtest(candles, strategy, params)
    permutation = monte_carlo_permutation_test(candles, strategy, params)
    try:
        walk_forward = walk_forward_validation(candles, strategy, params)
    except ValueError as e:
        walk_forward = {"skipped": True, "reason": str(e)}
    return {
        "success": True,
        "backtest": backtest.to_dict(),
        "monte_carlo_permutation_test": permutation,
        "walk_forward_validation": walk_forward,
    }
