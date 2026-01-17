"""Position sizing based on volatility-adjusted risk."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


def _to_decimal(value: Decimal | float | int | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class PositionSize:
    size_usd: Decimal
    units: Decimal
    stop_pct: Decimal
    skip_reason: Optional[str]


class VolatilityPositionSizer:
    """Calculates position size based on volatility and risk budget."""

    def __init__(
        self,
        equity: Decimal | float | int | str = Decimal("2500"),
        risk_budget_pct: Decimal | float | int | str = Decimal("0.5"),
        max_position_pct: Decimal | float | int | str = Decimal("20"),
        min_position_usd: Decimal | float | int | str = Decimal("100"),
    ) -> None:
        self.equity = _to_decimal(equity)
        self.risk_budget_pct = _to_decimal(risk_budget_pct) / Decimal("100")
        self.max_position_pct = _to_decimal(max_position_pct) / Decimal("100")
        self.min_position_usd = _to_decimal(min_position_usd)

    def calculate(
        self,
        asset_volatility_pct: Decimal | float | int | str,
        current_price: Decimal | float | int | str,
        custom_stop_pct: Optional[Decimal | float | int | str] = None,
    ) -> PositionSize:
        """
        Core formula: position_size = (equity * risk_budget) / stop_distance

        Steps:
        1. stop_distance = custom_stop_pct or (asset_volatility_pct * 1.5)
        2. raw_size = (equity * risk_budget_pct) / stop_distance
        3. Apply max_position_pct cap
        4. Apply min_position_usd floor (skip if below)
        5. Calculate units: size_usd / current_price

        Return: PositionSize dataclass with size_usd, units, stop_pct, skip_reason
        """
        asset_volatility_pct = _to_decimal(asset_volatility_pct)
        current_price = _to_decimal(current_price)
        if custom_stop_pct is None:
            stop_pct = asset_volatility_pct * Decimal("1.5")
        else:
            stop_pct = _to_decimal(custom_stop_pct)

        if stop_pct <= 0:
            raise ValueError("Stop percentage must be positive.")

        stop_distance = stop_pct / Decimal("100")
        raw_size = (self.equity * self.risk_budget_pct) / stop_distance
        max_size = self.equity * self.max_position_pct
        size_usd = raw_size if raw_size <= max_size else max_size

        if size_usd < self.min_position_usd:
            return PositionSize(
                size_usd=Decimal("0"),
                units=Decimal("0"),
                stop_pct=stop_pct,
                skip_reason="below_minimum",
            )

        units = size_usd / current_price
        return PositionSize(
            size_usd=size_usd,
            units=units,
            stop_pct=stop_pct,
            skip_reason=None,
        )
