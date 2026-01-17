"""
Regime Detection Gate

Pauses or adjusts trading when market conditions are unfavorable:
1. ATR compression (chop incoming)
2. BTC dominance spikes (altcoin correlation breakdown)
3. Extreme funding rates (leverage flush incoming)

TODO-GPT: Implement data fetching for regime indicators
"""

from decimal import Decimal
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum
from datetime import datetime


class RegimeState(Enum):
    """Market regime classifications."""
    FAVORABLE = "favorable"          # Normal conditions, trade normally
    CAUTION = "caution"              # Elevated risk, reduce size
    PAUSE = "pause"                  # Unfavorable, pause new positions
    WIDEN_GRIDS = "widen_grids"      # Low vol, need wider spacing


@dataclass
class RegimeSignal:
    """Individual regime indicator signal."""
    name: str
    value: float
    threshold: float
    triggered: bool
    action: str
    timestamp: datetime


@dataclass
class RegimeGateResult:
    """Combined regime assessment."""
    state: RegimeState
    signals: List[RegimeSignal]
    recommended_actions: List[str]
    can_open_new_positions: bool
    grid_spacing_multiplier: Decimal  # 1.0 = normal, 1.5 = widen 50%, etc.


class RegimeGate:
    """
    Evaluates market regime to determine if trading conditions are favorable.

    Usage:
        gate = RegimeGate()
        result = gate.evaluate(
            current_atr=0.02,
            avg_atr_30d=0.04,
            btc_dominance_change_7d=2.5,
            funding_rate=0.05
        )
        if result.state == RegimeState.PAUSE:
            print("Market unfavorable - pausing")
    """

    def __init__(
        self,
        atr_compression_threshold: float = 0.5,
        btc_dom_spike_threshold: float = 3.0,
        funding_extreme_threshold: float = 0.1
    ):
        """
        Initialize regime gate.

        Args:
            atr_compression_threshold: Trigger if ATR < X% of 30D average
            btc_dom_spike_threshold: Trigger if BTC.D change > X% in 7 days
            funding_extreme_threshold: Trigger if funding rate > X%
        """
        self.atr_compression_threshold = atr_compression_threshold
        self.btc_dom_spike_threshold = btc_dom_spike_threshold
        self.funding_extreme_threshold = funding_extreme_threshold

    def _check_atr_compression(
        self,
        current_atr: float,
        avg_atr_30d: float
    ) -> RegimeSignal:
        """Check if volatility has compressed (chop incoming)."""
        if avg_atr_30d == 0:
            ratio = 1.0
        else:
            ratio = current_atr / avg_atr_30d

        triggered = ratio < self.atr_compression_threshold

        return RegimeSignal(
            name="ATR Compression",
            value=ratio,
            threshold=self.atr_compression_threshold,
            triggered=triggered,
            action="Widen grid spacing or pause - low volatility = fee churn",
            timestamp=datetime.now()
        )

    def _check_btc_dominance(
        self,
        btc_dom_change_7d: float
    ) -> RegimeSignal:
        """Check if BTC dominance is spiking (altcoin selloff)."""
        triggered = abs(btc_dom_change_7d) > self.btc_dom_spike_threshold

        return RegimeSignal(
            name="BTC Dominance Spike",
            value=btc_dom_change_7d,
            threshold=self.btc_dom_spike_threshold,
            triggered=triggered,
            action="Reduce altcoin exposure - correlation breakdown likely",
            timestamp=datetime.now()
        )

    def _check_funding_rate(
        self,
        funding_rate: float
    ) -> RegimeSignal:
        """Check if funding rates are extreme (leverage flush incoming)."""
        triggered = abs(funding_rate) > self.funding_extreme_threshold

        return RegimeSignal(
            name="Extreme Funding Rate",
            value=funding_rate,
            threshold=self.funding_extreme_threshold,
            triggered=triggered,
            action="Expect volatility spike - tighten stops or reduce size",
            timestamp=datetime.now()
        )

    def evaluate(
        self,
        current_atr: Optional[float] = None,
        avg_atr_30d: Optional[float] = None,
        btc_dominance_change_7d: Optional[float] = None,
        funding_rate: Optional[float] = None
    ) -> RegimeGateResult:
        """
        Evaluate current market regime.

        All parameters are optional - only provided indicators are checked.

        Returns:
            RegimeGateResult with state and recommendations
        """
        signals = []
        triggered_count = 0

        # Check ATR compression
        if current_atr is not None and avg_atr_30d is not None:
            signal = self._check_atr_compression(current_atr, avg_atr_30d)
            signals.append(signal)
            if signal.triggered:
                triggered_count += 1

        # Check BTC dominance
        if btc_dominance_change_7d is not None:
            signal = self._check_btc_dominance(btc_dominance_change_7d)
            signals.append(signal)
            if signal.triggered:
                triggered_count += 1

        # Check funding rates
        if funding_rate is not None:
            signal = self._check_funding_rate(funding_rate)
            signals.append(signal)
            if signal.triggered:
                triggered_count += 1

        # Determine overall state
        if triggered_count == 0:
            state = RegimeState.FAVORABLE
            can_open = True
            spacing_mult = Decimal("1.0")
        elif triggered_count == 1:
            # Check which one triggered
            atr_triggered = any(s.name == "ATR Compression" and s.triggered for s in signals)
            if atr_triggered:
                state = RegimeState.WIDEN_GRIDS
                can_open = True
                spacing_mult = Decimal("1.5")
            else:
                state = RegimeState.CAUTION
                can_open = True
                spacing_mult = Decimal("1.25")
        else:
            state = RegimeState.PAUSE
            can_open = False
            spacing_mult = Decimal("2.0")

        # Compile recommendations
        recommendations = []
        for signal in signals:
            if signal.triggered:
                recommendations.append(signal.action)

        if not recommendations:
            recommendations.append("All clear - normal trading conditions")

        return RegimeGateResult(
            state=state,
            signals=signals,
            recommended_actions=recommendations,
            can_open_new_positions=can_open,
            grid_spacing_multiplier=spacing_mult
        )


if __name__ == "__main__":
    # Demo usage
    gate = RegimeGate()

    print("Regime Gate Demo")
    print("=" * 60)

    # Scenario 1: Normal conditions
    result = gate.evaluate(
        current_atr=0.035,
        avg_atr_30d=0.04,
        btc_dominance_change_7d=0.5,
        funding_rate=0.02
    )
    print(f"\nScenario 1 (Normal): {result.state.value}")
    print(f"  Can open positions: {result.can_open_new_positions}")
    print(f"  Grid spacing multiplier: {result.grid_spacing_multiplier}")

    # Scenario 2: Low volatility
    result = gate.evaluate(
        current_atr=0.015,
        avg_atr_30d=0.04,
        btc_dominance_change_7d=0.5,
        funding_rate=0.02
    )
    print(f"\nScenario 2 (Low Vol): {result.state.value}")
    print(f"  Can open positions: {result.can_open_new_positions}")
    print(f"  Grid spacing multiplier: {result.grid_spacing_multiplier}")
    for action in result.recommended_actions:
        print(f"  Action: {action}")

    # Scenario 3: Multiple triggers
    result = gate.evaluate(
        current_atr=0.015,
        avg_atr_30d=0.04,
        btc_dominance_change_7d=4.5,
        funding_rate=0.15
    )
    print(f"\nScenario 3 (Multiple Triggers): {result.state.value}")
    print(f"  Can open positions: {result.can_open_new_positions}")
    for action in result.recommended_actions:
        print(f"  Action: {action}")
