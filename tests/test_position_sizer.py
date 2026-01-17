from decimal import Decimal

import pytest

from src.sizing.position_sizer import PositionSize, VolatilityPositionSizer


def test_position_sizer_calculates_size_and_units() -> None:
    sizer = VolatilityPositionSizer(
        equity=Decimal("2500"),
        risk_budget_pct=Decimal("0.5"),
        max_position_pct=Decimal("20"),
        min_position_usd=Decimal("100"),
    )

    result = sizer.calculate(asset_volatility_pct=Decimal("2"), current_price=Decimal("50"))

    assert isinstance(result, PositionSize)
    assert result.stop_pct == Decimal("3")
    assert result.size_usd.quantize(Decimal("0.0001")) == Decimal("416.6667")
    assert result.units.quantize(Decimal("0.0001")) == Decimal("8.3333")
    assert result.skip_reason is None


def test_position_sizer_applies_max_position_cap() -> None:
    sizer = VolatilityPositionSizer(
        equity=Decimal("2500"),
        risk_budget_pct=Decimal("0.5"),
        max_position_pct=Decimal("20"),
        min_position_usd=Decimal("100"),
    )

    result = sizer.calculate(asset_volatility_pct=Decimal("0.1"), current_price=Decimal("50"))

    assert result.size_usd == Decimal("500")
    assert result.units == Decimal("10")
    assert result.skip_reason is None


def test_position_sizer_skips_below_minimum() -> None:
    sizer = VolatilityPositionSizer(
        equity=Decimal("2500"),
        risk_budget_pct=Decimal("0.5"),
        max_position_pct=Decimal("20"),
        min_position_usd=Decimal("100"),
    )

    result = sizer.calculate(asset_volatility_pct=Decimal("50"), current_price=Decimal("100"))

    assert result.size_usd == Decimal("0")
    assert result.units == Decimal("0")
    assert result.skip_reason == "below_minimum"


def test_position_sizer_requires_positive_stop_pct() -> None:
    sizer = VolatilityPositionSizer()

    with pytest.raises(ValueError):
        sizer.calculate(asset_volatility_pct=Decimal("0"), current_price=Decimal("100"))
