"""
Fee-Positivity Gate

The CRITICAL component that prevents death-by-chop.

Rule: grid_step >= k * C
Where: C = 2*fee + spread + slippage_buffer

This gate MUST pass before any grid is deployed.
"""

from decimal import Decimal, ROUND_UP
from dataclasses import dataclass
from typing import Optional
import json
from pathlib import Path


@dataclass
class FeeStructure:
    """Exchange fee structure for a trading pair."""
    maker_fee: Decimal  # Negative = rebate
    taker_fee: Decimal
    typical_spread: Decimal
    slippage_buffer: Decimal

    @property
    def round_trip_cost_maker_only(self) -> Decimal:
        """Cost when all orders are maker (post-only)."""
        # Maker rebate on both sides + spread + slippage
        return (self.maker_fee * 2) + self.typical_spread + self.slippage_buffer

    @property
    def round_trip_cost_mixed(self) -> Decimal:
        """Cost when entry is maker, exit is taker (common scenario)."""
        return self.maker_fee + self.taker_fee + self.typical_spread + self.slippage_buffer

    @property
    def round_trip_cost_taker_only(self) -> Decimal:
        """Worst case: both sides are taker."""
        return (self.taker_fee * 2) + self.typical_spread + self.slippage_buffer


@dataclass
class FeeGateResult:
    """Result of fee gate evaluation."""
    passed: bool
    proposed_step: Decimal
    minimum_step: Decimal
    round_trip_cost: Decimal
    k_factor: Decimal
    message: str
    recommendation: Optional[str] = None


class FeeGate:
    """
    Enforces fee-positivity for grid trading.

    Usage:
        gate = FeeGate(k_factor=3)
        result = gate.evaluate("ETH/USD", proposed_grid_step=Decimal("0.002"))
        if not result.passed:
            print(result.recommendation)
    """

    # Default fee structures by pair type
    DEFAULT_STRUCTURES = {
        "BTC/USD": FeeStructure(
            maker_fee=Decimal("-0.0002"),
            taker_fee=Decimal("0.0004"),
            typical_spread=Decimal("0.0005"),
            slippage_buffer=Decimal("0.0002")
        ),
        "ETH/USD": FeeStructure(
            maker_fee=Decimal("-0.0002"),
            taker_fee=Decimal("0.0004"),
            typical_spread=Decimal("0.0006"),
            slippage_buffer=Decimal("0.0002")
        ),
        "SOL/USD": FeeStructure(
            maker_fee=Decimal("-0.0002"),
            taker_fee=Decimal("0.0004"),
            typical_spread=Decimal("0.0010"),
            slippage_buffer=Decimal("0.0005")
        ),
        "DEFAULT": FeeStructure(
            maker_fee=Decimal("-0.0002"),
            taker_fee=Decimal("0.0004"),
            typical_spread=Decimal("0.0020"),
            slippage_buffer=Decimal("0.0010")
        )
    }

    def __init__(self, k_factor: Decimal = Decimal("3"), assume_mixed: bool = True):
        """
        Initialize fee gate.

        Args:
            k_factor: Multiplier for minimum step (2=aggressive, 3=moderate, 4=conservative)
            assume_mixed: If True, assume mixed maker/taker; if False, assume maker-only
        """
        self.k_factor = Decimal(str(k_factor))
        self.assume_mixed = assume_mixed
        self.fee_structures = self.DEFAULT_STRUCTURES.copy()

    def get_fee_structure(self, pair: str) -> FeeStructure:
        """Get fee structure for a pair, falling back to default."""
        return self.fee_structures.get(pair, self.fee_structures["DEFAULT"])

    def calculate_minimum_step(self, pair: str) -> Decimal:
        """Calculate minimum profitable grid step for a pair."""
        structure = self.get_fee_structure(pair)

        if self.assume_mixed:
            cost = structure.round_trip_cost_mixed
        else:
            cost = structure.round_trip_cost_maker_only

        return (cost * self.k_factor).quantize(Decimal("0.0001"), rounding=ROUND_UP)

    def evaluate(self, pair: str, proposed_step: Decimal) -> FeeGateResult:
        """
        Evaluate if a proposed grid step is fee-positive.

        Args:
            pair: Trading pair (e.g., "ETH/USD")
            proposed_step: Proposed grid step as decimal (e.g., 0.005 for 0.5%)

        Returns:
            FeeGateResult with pass/fail and recommendations
        """
        proposed_step = Decimal(str(proposed_step))
        structure = self.get_fee_structure(pair)

        if self.assume_mixed:
            cost = structure.round_trip_cost_mixed
        else:
            cost = structure.round_trip_cost_maker_only

        min_step = self.calculate_minimum_step(pair)
        passed = proposed_step >= min_step

        if passed:
            message = f"PASS: {pair} grid step {proposed_step:.4%} >= minimum {min_step:.4%}"
            recommendation = None
        else:
            message = f"FAIL: {pair} grid step {proposed_step:.4%} < minimum {min_step:.4%}"
            recommendation = (
                f"Options:\n"
                f"  1. Widen grid step to at least {min_step:.4%}\n"
                f"  2. Use maker-only orders (post-only) to reduce costs\n"
                f"  3. Skip this pair - insufficient edge vs fees"
            )

        return FeeGateResult(
            passed=passed,
            proposed_step=proposed_step,
            minimum_step=min_step,
            round_trip_cost=cost,
            k_factor=self.k_factor,
            message=message,
            recommendation=recommendation
        )

    def evaluate_all(self, grid_config: dict) -> dict:
        """
        Evaluate fee-positivity for all pairs in a grid config.

        Args:
            grid_config: Dict of {pair: {"step": Decimal, ...}}

        Returns:
            Dict of {pair: FeeGateResult}
        """
        results = {}
        for pair, config in grid_config.items():
            step = Decimal(str(config.get("step", config.get("grid_step", 0))))
            results[pair] = self.evaluate(pair, step)
        return results


# Convenience function for quick checks
def check_fee_positive(pair: str, grid_step: float, k: int = 3) -> bool:
    """Quick check if a grid step is fee-positive."""
    gate = FeeGate(k_factor=Decimal(str(k)))
    result = gate.evaluate(pair, Decimal(str(grid_step)))
    return result.passed


if __name__ == "__main__":
    # Demo usage
    gate = FeeGate(k_factor=Decimal("3"))

    test_cases = [
        ("BTC/USD", Decimal("0.002")),   # 0.2% step
        ("BTC/USD", Decimal("0.005")),   # 0.5% step
        ("ETH/USD", Decimal("0.003")),   # 0.3% step
        ("SOL/USD", Decimal("0.004")),   # 0.4% step
        ("PEPE/USD", Decimal("0.005")),  # 0.5% step on illiquid alt
    ]

    print("Fee Gate Evaluation Results")
    print("=" * 60)

    for pair, step in test_cases:
        result = gate.evaluate(pair, step)
        status = "PASS" if result.passed else "FAIL"
        print(f"\n{pair} @ {step:.2%} step: {status}")
        print(f"  Round-trip cost: {result.round_trip_cost:.4%}")
        print(f"  Minimum step (k={result.k_factor}): {result.minimum_step:.4%}")
        if result.recommendation:
            print(f"  Recommendation: {result.recommendation}")
