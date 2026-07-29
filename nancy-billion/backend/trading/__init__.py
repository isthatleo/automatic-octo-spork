"""Trading package initialization"""

from trading.forex_engine import (
    ForexDataAggregator,
    TechnicalAnalysisEngine,
    StrategyAdvisor,
    RiskMonitor,
    MarketSnapshot,
    TechnicalAnalysis,
    run_forex_backtest,
)
from trading.manager import TradingManager, Trade
from trading.crypto_data import CryptoDataAggregator, CryptoSnapshot, crypto_data
from trading.strategy_library import list_strategies, run_strategy
from trading.backtest_engine import run_backtest, monte_carlo_permutation_test, walk_forward_validation, run_full_validation

__all__ = [
    "ForexDataAggregator",
    "TechnicalAnalysisEngine",
    "StrategyAdvisor",
    "RiskMonitor",
    "TradingManager",
    "MarketSnapshot",
    "TechnicalAnalysis",
    "Trade",
    "run_forex_backtest",
    "CryptoDataAggregator",
    "CryptoSnapshot",
    "crypto_data",
    "list_strategies",
    "run_strategy",
    "run_backtest",
    "monte_carlo_permutation_test",
    "walk_forward_validation",
    "run_full_validation",
]

