"""
Volatility-Based Position Sizing

TODO-GPT: This file needs implementation.

Core formula:
    position_size = (equity * risk_budget) / stop_distance

Requirements:
1. VolatilityPositionSizer class
2. Input: equity, risk_budget_pct, asset_volatility (ATR%)
3. Output: position size in USD and units
4. Must enforce max position as % of equity
5. Use Decimal for all financial calculations

Example calculations:
    equity = $4100
    risk_budget = 0.5% = 0.005

    High vol asset (20% stop):
        position = 4100 * 0.005 / 0.20 = $102.50

    Low vol asset (5% stop):
        position = 4100 * 0.005 / 0.05 = $410.00

Additional requirements:
- Minimum position size floor (don't create dust positions)
- Maximum position as % of equity cap
- Scale down for very high volatility assets
- Return both USD amount and unit count given current price
"""

from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass
from typing import Optional


@dataclass
class PositionSizeResult:
    """Result of position size calculation."""
    size_usd: Decimal
    size_units: Decimal
    risk_per_trade_usd: Decimal
    effective_stop_pct: Decimal
    capped: bool  # True if position was reduced due to max position limit
    skip_reason: Optional[str]  # If position should be skipped entirely


class VolatilityPositionSizer:
    """
    TODO-GPT: Implement this class.

    Calculate position sizes based on volatility and risk budget.

    Usage:
        sizer = VolatilityPositionSizer(
            equity=Decimal("4100"),
            risk_budget_pct=Decimal("0.005"),
            max_position_pct=Decimal("0.25")
        )
        result = sizer.calculate(
            asset_volatility_pct=Decimal("0.15"),
            current_price=Decimal("3500")
        )
    """

    def __init__(
        self,
        equity: Decimal,
        risk_budget_pct: Decimal = Decimal("0.005"),
        max_position_pct: Decimal = Decimal("0.25"),
        min_position_usd: Decimal = Decimal("50")
    ):
        """
        Initialize position sizer.

        Args:
            equity: Total account equity in USD
            risk_budget_pct: Max risk per trade as decimal (0.005 = 0.5%)
            max_position_pct: Max single position as % of equity (0.25 = 25%)
            min_position_usd: Minimum position size (skip if below)
        """
        # TODO-GPT: Store parameters
        raise NotImplementedError("TODO-GPT: Implement __init__")

    def calculate(
        self,
        asset_volatility_pct: Decimal,
        current_price: Decimal,
        custom_stop_pct: Optional[Decimal] = None
    ) -> PositionSizeResult:
        """
        Calculate position size for an asset.

        Args:
            asset_volatility_pct: Asset's ATR% or typical move size
            current_price: Current asset price in USD
            custom_stop_pct: Override stop distance (default: use volatility)

        Returns:
            PositionSizeResult with size in USD and units
        """
        # TODO-GPT: Implement calculation
        # 1. Determine stop distance (custom or 1.5x volatility)
        # 2. Calculate raw position size: (equity * risk_budget) / stop_distance
        # 3. Apply max position cap
        # 4. Apply min position floor (return skip if below)
        # 5. Calculate units from USD size and price
        raise NotImplementedError("TODO-GPT: Implement calculate")

    def calculate_for_grid(
        self,
        grid_range_pct: Decimal,
        current_price: Decimal,
        num_grid_levels: int
    ) -> PositionSizeResult:
        """
        Calculate position size specifically for grid trading.

        For grids, the "stop" is effectively the full grid range,
        but capital is distributed across levels.

        Args:
            grid_range_pct: Total grid range (e.g., 0.10 for 10% range)
            current_price: Current asset price
            num_grid_levels: Number of grid levels

        Returns:
            PositionSizeResult for total grid allocation
        """
        # TODO-GPT: Implement grid-specific sizing
        raise NotImplementedError("TODO-GPT: Implement calculate_for_grid")


# Convenience function
def quick_size(
    equity: float,
    risk_pct: float,
    stop_pct: float,
    price: float
) -> tuple[float, float]:
    """
    Quick position size calculation.

    Returns:
        (size_usd, size_units)
    """
    # TODO-GPT: Implement quick calculation
    size_usd = (equity * risk_pct) / stop_pct
    size_units = size_usd / price
    return (size_usd, size_units)


if __name__ == "__main__":
    # Demo - will fail until implemented
    print("Position Sizer - TODO-GPT Implementation Required")
    print("=" * 60)

    # Show expected behavior
    equity = 4100
    risk = 0.005

    scenarios = [
        ("High vol (20% stop)", 0.20, 3500),
        ("Med vol (10% stop)", 0.10, 150),
        ("Low vol (5% stop)", 0.05, 100),
    ]

    print("\nExpected outputs:")
    for name, stop, price in scenarios:
        size_usd = (equity * risk) / stop
        size_units = size_usd / price
        print(f"  {name}: ${size_usd:.2f} = {size_units:.4f} units @ ${price}")
