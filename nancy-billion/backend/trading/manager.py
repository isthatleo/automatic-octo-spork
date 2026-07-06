"""
Trading Manager - Integration layer for trading intelligence

Handles:
- Trade execution tracking
- Trading history analysis
- Performance metrics
- Integration with memory system
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """A single trade record"""
    pair: str
    direction: str  # "BUY" or "SELL"
    entry_price: float
    exit_price: Optional[float] = None
    quantity: float = 1.0
    profit_loss: Optional[float] = None
    status: str = "open"  # "open", "closed", "pending"
    entry_time: str = None
    exit_time: Optional[str] = None
    notes: str = ""

    def __post_init__(self):
        if self.entry_time is None:
            self.entry_time = datetime.now().isoformat()

        if self.exit_price is not None and self.status == "open":
            self._calculate_pnl()

    def _calculate_pnl(self):
        """Calculate profit/loss for closed trade"""
        if self.direction == "BUY":
            self.profit_loss = (self.exit_price - self.entry_price) * self.quantity
        else:  # SELL
            self.profit_loss = (self.entry_price - self.exit_price) * self.quantity

        self.status = "closed"
        self.exit_time = datetime.now().isoformat()


class TradingManager:
    """
    Manages trading operations and history.

    Tracks:
    - Individual trades
    - Performance metrics
    - Trading statistics
    - Integration with memory
    """

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.trades: List[Trade] = []
        self.equity = 100000.0  # Starting equity

    def record_trade(
        self,
        pair: str,
        direction: str,
        entry_price: float,
        quantity: float = 1.0,
        notes: str = ""
    ) -> Trade:
        """
        Record a new trade.

        Args:
            pair: Forex pair (e.g., "EUR/USD")
            direction: "BUY" or "SELL"
            entry_price: Entry price
            quantity: Trade size
            notes: Optional notes

        Returns:
            Trade object
        """
        trade = Trade(
            pair=pair,
            direction=direction,
            entry_price=entry_price,
            quantity=quantity,
            notes=notes
        )

        self.trades.append(trade)
        logger.info(f"Recorded trade: {pair} {direction} @ {entry_price}")

        return trade

    def close_trade(self, trade_id: int, exit_price: float) -> Trade:
        """Close an open trade"""
        if 0 <= trade_id < len(self.trades):
            trade = self.trades[trade_id]
            trade.exit_price = exit_price
            trade._calculate_pnl()

            # Update equity
            self.equity += trade.profit_loss

            logger.info(f"Closed trade: {trade.pair} P&L: {trade.profit_loss}")
            return trade

        return None

    def get_trade_history(self, pair: Optional[str] = None, limit: int = 50) -> List[Trade]:
        """Get trade history, optionally filtered by pair"""
        trades = self.trades

        if pair:
            trades = [t for t in trades if t.pair == pair]

        return trades[-limit:]

    def get_performance_metrics(self) -> Dict:
        """
        Calculate overall trading performance metrics.

        Returns:
            Dictionary with performance statistics
        """
        if not self.trades:
            return {
                "total_trades": 0,
                "closed_trades": 0,
                "open_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "average_win": 0.0,
                "average_loss": 0.0,
                "profit_factor": 0.0,
                "max_drawdown": 0.0,
            }

        closed_trades = [t for t in self.trades if t.status == "closed"]
        open_trades = [t for t in self.trades if t.status == "open"]

        if not closed_trades:
            return {
                "total_trades": len(self.trades),
                "closed_trades": 0,
                "open_trades": len(open_trades),
                "win_rate": 0.0,
                "total_pnl": 0.0,
            }

        # Calculate metrics
        winning_trades = [t for t in closed_trades if t.profit_loss > 0]
        losing_trades = [t for t in closed_trades if t.profit_loss <= 0]

        win_rate = (len(winning_trades) / len(closed_trades)) * 100
        total_pnl = sum(t.profit_loss for t in closed_trades)
        avg_win = (sum(t.profit_loss for t in winning_trades) / len(winning_trades)) if winning_trades else 0
        avg_loss = (sum(t.profit_loss for t in losing_trades) / len(losing_trades)) if losing_trades else 0
        profit_factor = avg_win / abs(avg_loss) if avg_loss != 0 else 0

        return {
            "total_trades": len(self.trades),
            "closed_trades": len(closed_trades),
            "open_trades": len(open_trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "average_win": avg_win,
            "average_loss": avg_loss,
            "profit_factor": profit_factor,
            "current_equity": self.equity,
        }

    def get_pair_stats(self, pair: str) -> Dict:
        """Get statistics for a specific forex pair"""
        pair_trades = [t for t in self.trades if t.pair == pair]
        closed = [t for t in pair_trades if t.status == "closed"]

        if not closed:
            return {
                "pair": pair,
                "total_trades": len(pair_trades),
                "closed_trades": 0,
            }

        wins = len([t for t in closed if t.profit_loss > 0])
        total_pnl = sum(t.profit_loss for t in closed)

        return {
            "pair": pair,
            "total_trades": len(pair_trades),
            "closed_trades": len(closed),
            "wins": wins,
            "losses": len(closed) - wins,
            "win_rate": (wins / len(closed)) * 100,
            "total_pnl": total_pnl,
        }

    def generate_trading_report(self) -> Dict:
        """Generate comprehensive trading report"""
        metrics = self.get_performance_metrics()
        pairs = set(t.pair for t in self.trades)
        pair_stats = [self.get_pair_stats(pair) for pair in pairs]

        return {
            "user_id": self.user_id,
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics,
            "pair_statistics": pair_stats,
            "recommendation": self._get_trading_recommendation(metrics),
        }

    def _get_trading_recommendation(self, metrics: Dict) -> str:
        """Get trading recommendation based on performance"""
        if metrics["closed_trades"] < 5:
            return "Insufficient data for recommendation (need 5+ trades)"

        if metrics["win_rate"] < 40:
            return "Consider reviewing strategy - win rate below 40%"
        elif metrics["win_rate"] < 50:
            return "Focus on improving win rate"
        elif metrics["win_rate"] > 70:
            return "Excellent win rate - consider scaling position sizes"
        else:
            return "Performance within normal range - maintain current approach"


# Example usage
if __name__ == "__main__":
    manager = TradingManager()

    # Record some trades
    manager.record_trade("EUR/USD", "BUY", 1.0850)
    manager.record_trade("EUR/USD", "BUY", 1.0870)
    manager.record_trade("GBP/USD", "SELL", 1.2750)

    # Close trades
    manager.close_trade(0, 1.0900)  # Win
    manager.close_trade(1, 1.0820)  # Loss
    manager.close_trade(2, 1.2700)  # Win

    # Get metrics
    metrics = manager.get_performance_metrics()
    print(f"Performance: {metrics}")

    # Get report
    report = manager.generate_trading_report()
    print(f"Report: {report}")

