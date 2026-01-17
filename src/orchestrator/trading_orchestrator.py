"""
Trading System Orchestrator
===========================
Ties together all modules into a cohesive trading system:
- Kraken client (market data)
- Fee gate (cost validation)
- Regime gate (market conditions)
- Asset ranker (opportunity identification)
- Position sizer (risk-based sizing)
- Capital allocator (portfolio management)

This orchestrator runs the analysis loop but does NOT execute trades.
It produces signals that can be acted upon manually or by a separate
execution module.
"""

import logging
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from datetime import datetime
from enum import Enum
import json
from pathlib import Path

from ..exchange.kraken_client import KrakenClient, TickerData
from ..gates.fee_gate import FeeGate, FeeGateResult
from ..gates.regime_gate import RegimeGate, RegimeGateResult, RegimeState
from ..rotation.asset_ranker import AssetRanker, AssetScore
from ..sizing.position_sizer import VolatilityPositionSizer, PositionSize
from ..core.capital_allocator import CapitalAllocator, AllocationBucket, AllocationCheck

log = logging.getLogger(__name__)


class SignalType(Enum):
    """Type of trading signal."""
    ENTRY = "entry"           # New position opportunity
    EXIT = "exit"             # Close existing position
    ADJUST = "adjust"         # Modify position size
    SKIP = "skip"             # Opportunity rejected
    PAUSE = "pause"           # System paused


@dataclass
class TradingSignal:
    """A trading signal produced by the orchestrator."""
    signal_type: SignalType
    pair: str
    side: str  # "buy" or "sell"
    size_usd: Decimal
    size_units: Decimal
    price: Decimal
    stop_pct: Decimal
    reason: str
    confidence: str  # "high", "medium", "low"
    checks_passed: Dict[str, bool]
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "signal_type": self.signal_type.value,
            "pair": self.pair,
            "side": self.side,
            "size_usd": str(self.size_usd),
            "size_units": str(self.size_units),
            "price": str(self.price),
            "stop_pct": str(self.stop_pct),
            "reason": self.reason,
            "confidence": self.confidence,
            "checks_passed": self.checks_passed,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class SystemState:
    """Current state of the trading system."""
    regime: RegimeState
    active_pairs: List[str]
    signals_generated: int
    signals_executed: int
    last_scan_time: datetime
    errors: List[str]
    warnings: List[str]

    # Detailed state
    tickers: Dict[str, TickerData] = field(default_factory=dict)
    fee_checks: Dict[str, FeeGateResult] = field(default_factory=dict)
    ranked_assets: List[AssetScore] = field(default_factory=list)
    capital_summary: str = ""


class TradingOrchestrator:
    """
    Main orchestrator that coordinates all trading modules.

    Usage:
        orchestrator = TradingOrchestrator()
        signals = orchestrator.scan_for_opportunities()
        for signal in signals:
            if signal.signal_type == SignalType.ENTRY:
                # Act on signal (manually or via execution module)
                pass
    """

    # Default trading universe
    DEFAULT_PAIRS = [
        "BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD",
        "ADA/USD", "DOT/USD", "LINK/USD", "AVAX/USD"
    ]

    def __init__(
        self,
        total_equity: Decimal = Decimal("4100"),
        risk_budget_pct: Decimal = Decimal("0.5"),
        pairs: Optional[List[str]] = None,
        config_dir: Optional[Path] = None
    ):
        """
        Initialize the trading orchestrator.

        Args:
            total_equity: Total account equity in USD
            risk_budget_pct: Risk per trade as percentage (0.5 = 0.5%)
            pairs: List of pairs to trade (or use default)
            config_dir: Directory containing config files
        """
        self.total_equity = Decimal(str(total_equity))
        self.risk_budget_pct = Decimal(str(risk_budget_pct))
        self.pairs = pairs or self.DEFAULT_PAIRS

        # Load config if provided
        self.config_dir = config_dir or Path(__file__).parent.parent.parent / "config"
        self._load_config()

        # Initialize modules
        self.kraken = KrakenClient()
        self.fee_gate = FeeGate(k_factor=Decimal("3"))
        self.regime_gate = RegimeGate()
        self.asset_ranker = AssetRanker()
        self.position_sizer = VolatilityPositionSizer(
            equity=self.total_equity,
            risk_budget_pct=self.risk_budget_pct,
            max_position_pct=Decimal("20"),
            min_position_usd=Decimal("100")
        )
        self.capital_allocator = CapitalAllocator(total_equity=self.total_equity)

        # State tracking
        self.state = SystemState(
            regime=RegimeState.FAVORABLE,
            active_pairs=[],
            signals_generated=0,
            signals_executed=0,
            last_scan_time=datetime.now(),
            errors=[],
            warnings=[]
        )

        # Signal history
        self.signals: List[TradingSignal] = []

    def _load_config(self):
        """Load configuration from JSON files."""
        try:
            # Load capital allocation config
            cap_file = self.config_dir / "capital_allocation.json"
            if cap_file.exists():
                with open(cap_file) as f:
                    cap_config = json.load(f)
                    self.total_equity = Decimal(str(cap_config.get("total_equity", self.total_equity)))

            # Load risk parameters
            risk_file = self.config_dir / "risk_parameters.json"
            if risk_file.exists():
                with open(risk_file) as f:
                    risk_config = json.load(f)
                    sizing = risk_config.get("position_sizing", {})
                    self.risk_budget_pct = Decimal(str(
                        sizing.get("recommended", self.risk_budget_pct) * 100
                    ))

        except Exception as e:
            log.warning(f"Could not load config: {e}")

    def check_system_health(self) -> bool:
        """
        Verify all system components are working.

        Returns:
            True if system is healthy, False otherwise
        """
        self.state.errors = []

        # Check Kraken API
        if not self.kraken.health_check():
            self.state.errors.append("Kraken API unavailable")
            return False

        # Check we have capital allocated
        core_available = self.capital_allocator.get_available(AllocationBucket.CORE_BOT)
        if core_available <= 0:
            self.state.errors.append("No capital available in core bucket")
            return False

        return True

    def assess_regime(self) -> RegimeGateResult:
        """
        Assess current market regime.

        Returns:
            RegimeGateResult with current conditions
        """
        # Get BTC data for regime assessment
        btc_bars = self.kraken.get_ohlcv("BTC/USD", interval=1440, limit=31)

        if len(btc_bars) < 15:
            log.warning("Insufficient data for regime assessment")
            return self.regime_gate.evaluate()

        # Calculate ATR
        current_atr = None
        avg_atr_30d = None

        if len(btc_bars) >= 15:
            # Calculate recent ATR (14 periods)
            true_ranges = []
            for i in range(1, min(15, len(btc_bars))):
                high = btc_bars[i].high
                low = btc_bars[i].low
                prev_close = btc_bars[i-1].close
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                true_ranges.append(float(tr))
            current_atr = sum(true_ranges) / len(true_ranges)

        if len(btc_bars) >= 31:
            # Calculate 30D average ATR
            true_ranges_30d = []
            for i in range(1, 31):
                high = btc_bars[i].high
                low = btc_bars[i].low
                prev_close = btc_bars[i-1].close
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                true_ranges_30d.append(float(tr))
            avg_atr_30d = sum(true_ranges_30d) / len(true_ranges_30d)

        # Evaluate regime
        result = self.regime_gate.evaluate(
            current_atr=current_atr,
            avg_atr_30d=avg_atr_30d
        )

        self.state.regime = result.state
        return result

    def scan_pairs(self, pairs: Optional[List[str]] = None) -> Dict[str, TickerData]:
        """
        Scan all pairs and get current market data.

        Returns:
            Dict of pair -> TickerData
        """
        tickers = {}

        pairs_to_scan = pairs or self.pairs
        for pair in pairs_to_scan:
            ticker = self.kraken.get_ticker(pair)
            if ticker:
                tickers[pair] = ticker
            else:
                log.warning(f"Could not get ticker for {pair}")

        self.state.tickers = tickers
        return tickers

    def evaluate_fee_gates(
        self,
        tickers: Dict[str, TickerData],
        grid_step: Decimal = Decimal("0.01")  # 1% default
    ) -> Dict[str, FeeGateResult]:
        """
        Evaluate fee gate for all pairs.

        Args:
            tickers: Dict of ticker data
            grid_step: Proposed grid step (default 1%)

        Returns:
            Dict of pair -> FeeGateResult
        """
        results = {}

        for pair, ticker in tickers.items():
            # Use actual spread from ticker if available
            result = self.fee_gate.evaluate(pair, grid_step)
            results[pair] = result

            if not result.passed:
                self.state.warnings.append(
                    f"{pair}: Grid step too tight ({result.proposed_step:.2%} < {result.minimum_step:.2%})"
                )

        self.state.fee_checks = results
        return results

    def rank_opportunities(self) -> List[AssetScore]:
        """
        Rank assets for rotation opportunities.

        Returns:
            List of AssetScore objects (best opportunities first)
        """
        # Gather historical data for ranking
        btc_prices = self.kraken.get_historical_prices("BTC/USD", days=65)

        if len(btc_prices) < 60:
            log.warning("Insufficient BTC price history for ranking")
            return []

        asset_data = {}

        for pair in self.pairs:
            if pair == "BTC/USD":
                continue  # BTC is the benchmark, not ranked

            prices = self.kraken.get_historical_prices(pair, days=65)
            volumes = self.kraken.get_historical_volumes(pair, days=65)

            if len(prices) >= 60 and len(volumes) >= 60:
                asset_data[pair] = {
                    "prices": prices,
                    "volumes": volumes
                }
            else:
                log.warning(f"Insufficient data for {pair}")

        if not asset_data:
            return []

        ranked = self.asset_ranker.rank(asset_data, btc_prices)
        self.state.ranked_assets = ranked
        return ranked

    def calculate_position_size(
        self,
        pair: str,
        current_price: Decimal
    ) -> PositionSize:
        """
        Calculate position size for a pair.

        Args:
            pair: Trading pair
            current_price: Current price

        Returns:
            PositionSize with size and stop info
        """
        # Get volatility for the pair
        volatility = self.kraken.calculate_volatility_pct(pair)

        if volatility is None:
            volatility = Decimal("5")  # Default to 5% if can't calculate
            self.state.warnings.append(f"Using default volatility for {pair}")

        return self.position_sizer.calculate(
            asset_volatility_pct=volatility,
            current_price=current_price
        )

    def check_capital_allocation(
        self,
        size_usd: Decimal,
        bucket: AllocationBucket = AllocationBucket.CORE_BOT
    ) -> AllocationCheck:
        """
        Check if capital allocation allows the position.

        Args:
            size_usd: Position size in USD
            bucket: Which bucket to deploy from

        Returns:
            AllocationCheck with approval status
        """
        return self.capital_allocator.can_deploy(bucket, size_usd)

    def generate_signal(
        self,
        pair: str,
        ticker: TickerData,
        ranked_score: Optional[AssetScore],
        position_size: PositionSize,
        fee_check: FeeGateResult,
        allocation_check: AllocationCheck,
        regime: RegimeGateResult
    ) -> TradingSignal:
        """
        Generate a trading signal based on all checks.

        Args:
            pair: Trading pair
            ticker: Current ticker data
            ranked_score: Asset ranking (if applicable)
            position_size: Calculated position size
            fee_check: Fee gate result
            allocation_check: Capital allocation result
            regime: Current regime

        Returns:
            TradingSignal with action and details
        """
        checks = {
            "fee_gate": fee_check.passed,
            "regime_favorable": regime.can_open_new_positions,
            "capital_available": allocation_check.allowed,
            "size_valid": position_size.skip_reason is None,
            "ranked_entry": ranked_score is not None
        }

        all_passed = all(checks.values())

        if not all_passed:
            # Determine skip reason
            if not checks["regime_favorable"]:
                reason = f"Regime unfavorable: {regime.state.value}"
            elif not checks["fee_gate"]:
                reason = f"Fee gate failed: step {fee_check.proposed_step:.2%} < min {fee_check.minimum_step:.2%}"
            elif not checks["capital_available"]:
                reason = f"Capital unavailable: {allocation_check.message}"
            elif not checks["size_valid"]:
                reason = f"Position too small: {position_size.skip_reason}"
            else:
                reason = "No entry signal"

            return TradingSignal(
                signal_type=SignalType.SKIP,
                pair=pair,
                side="none",
                size_usd=Decimal("0"),
                size_units=Decimal("0"),
                price=ticker.last,
                stop_pct=position_size.stop_pct,
                reason=reason,
                confidence="none",
                checks_passed=checks
            )

        # All checks passed - generate entry signal
        confidence = "high" if ranked_score and ranked_score.entry_signal == "PULLBACK_ENTRY" else "medium"

        return TradingSignal(
            signal_type=SignalType.ENTRY,
            pair=pair,
            side="buy",
            size_usd=position_size.size_usd,
            size_units=position_size.units,
            price=ticker.last,
            stop_pct=position_size.stop_pct,
            reason=f"Entry signal: {ranked_score.entry_signal if ranked_score else 'fee-positive'}",
            confidence=confidence,
            checks_passed=checks,
            metadata={
                "momentum_vs_btc": str(ranked_score.momentum_vs_btc) if ranked_score else None,
                "volume_expansion": str(ranked_score.volume_expansion) if ranked_score else None,
                "regime": regime.state.value,
                "spread_pct": str(ticker.spread_pct)
            }
        )

    def scan_for_opportunities(
        self,
        pairs: Optional[List[str]] = None,
        top_n: Optional[int] = None
    ) -> List[TradingSignal]:
        """
        Main scanning loop - find all trading opportunities.

        Args:
            pairs: Optional subset of pairs to scan (defaults to configured list).
            top_n: Optional cap on the number of entry signals returned.

        Returns:
            List of TradingSignal objects
        """
        signals = []
        self.state.errors = []
        self.state.warnings = []
        self.state.last_scan_time = datetime.now()

        # Step 1: Health check
        if not self.check_system_health():
            log.error("System health check failed")
            return []

        # Step 2: Assess regime
        regime = self.assess_regime()
        log.info(f"Regime: {regime.state.value}")

        if regime.state == RegimeState.PAUSE:
            log.warning("Trading paused due to unfavorable regime")
            signals.append(TradingSignal(
                signal_type=SignalType.PAUSE,
                pair="ALL",
                side="none",
                size_usd=Decimal("0"),
                size_units=Decimal("0"),
                price=Decimal("0"),
                stop_pct=Decimal("0"),
                reason="Market regime unfavorable",
                confidence="high",
                checks_passed={"regime_favorable": False}
            ))
            return signals

        # Step 3: Scan pairs
        tickers = self.scan_pairs(pairs)
        log.info(f"Scanned {len(tickers)} pairs")

        # Step 4: Fee gate evaluation
        fee_checks = self.evaluate_fee_gates(tickers)

        # Step 5: Rank opportunities
        ranked = self.rank_opportunities()
        ranked_dict = {score.symbol: score for score in ranked}
        log.info(f"Ranked {len(ranked)} opportunities")

        # Step 6: Generate signals for each pair
        for pair, ticker in tickers.items():
            # Calculate position size
            position_size = self.calculate_position_size(pair, ticker.last)

            # Check capital allocation
            allocation_check = self.check_capital_allocation(position_size.size_usd)

            # Get ranking if available
            ranked_score = ranked_dict.get(pair)

            # Generate signal
            signal = self.generate_signal(
                pair=pair,
                ticker=ticker,
                ranked_score=ranked_score,
                position_size=position_size,
                fee_check=fee_checks.get(pair, self.fee_gate.evaluate(pair, Decimal("0.01"))),
                allocation_check=allocation_check,
                regime=regime
            )

            signals.append(signal)
            self.state.signals_generated += 1

        # Sort: entries first, then by confidence
        signals.sort(key=lambda s: (
            0 if s.signal_type == SignalType.ENTRY else 1,
            0 if s.confidence == "high" else 1
        ))

        if top_n is not None:
            entry_signals = [s for s in signals if s.signal_type == SignalType.ENTRY]
            non_entries = [s for s in signals if s.signal_type != SignalType.ENTRY]
            signals = entry_signals[:top_n] + non_entries

        self.signals = signals
        self.state.capital_summary = self.capital_allocator.get_summary()

        return signals

    def get_summary(self) -> str:
        """Get human-readable summary of current state."""
        lines = [
            "=" * 60,
            "TRADING SYSTEM STATUS",
            "=" * 60,
            f"Last Scan: {self.state.last_scan_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Regime: {self.state.regime.value}",
            f"Pairs Tracked: {len(self.pairs)}",
            f"Signals Generated: {self.state.signals_generated}",
            "",
        ]

        # Capital summary
        lines.append("--- CAPITAL ---")
        lines.append(self.state.capital_summary)
        lines.append("")

        # Entry signals
        entries = [s for s in self.signals if s.signal_type == SignalType.ENTRY]
        if entries:
            lines.append("--- ENTRY SIGNALS ---")
            for s in entries:
                lines.append(f"  {s.pair}: {s.side.upper()} ${s.size_usd:.2f} @ ${s.price:.2f}")
                lines.append(f"    Stop: {s.stop_pct:.1f}% | Confidence: {s.confidence}")
        else:
            lines.append("--- NO ENTRY SIGNALS ---")

        lines.append("")

        # Warnings
        if self.state.warnings:
            lines.append("--- WARNINGS ---")
            for w in self.state.warnings:
                lines.append(f"  ⚠ {w}")

        # Errors
        if self.state.errors:
            lines.append("--- ERRORS ---")
            for e in self.state.errors:
                lines.append(f"  ❌ {e}")

        return "\n".join(lines)


if __name__ == "__main__":
    # Demo usage
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Trading System Orchestrator Demo")
    print("=" * 60)

    orchestrator = TradingOrchestrator(
        total_equity=Decimal("4100"),
        risk_budget_pct=Decimal("0.5")
    )

    print("\nScanning for opportunities...")
    signals = orchestrator.scan_for_opportunities()

    print(orchestrator.get_summary())

    # Export signals to JSON
    print("\n--- SIGNALS JSON ---")
    for signal in signals[:3]:  # Show first 3
        print(json.dumps(signal.to_dict(), indent=2))
