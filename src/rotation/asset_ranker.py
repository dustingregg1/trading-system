"""Asset ranking logic for rotation-based trading."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping, Optional, Sequence


def _to_decimal(value: Decimal | float | int | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _average(values: Iterable[Decimal]) -> Decimal:
    values_list = list(values)
    if not values_list:
        raise ValueError("Values must not be empty.")
    return sum(values_list, Decimal("0")) / Decimal(len(values_list))


@dataclass(frozen=True)
class AssetScore:
    symbol: str
    momentum_vs_btc: Decimal
    volume_expansion: Decimal
    entry_signal: str
    score: Decimal


class AssetRanker:
    """Ranks assets by momentum, volume expansion, and entry readiness."""

    NO_SIGNAL = "NO_SIGNAL"
    WAIT_CONFIRMATION = "WAIT_CONFIRMATION"
    PULLBACK_ENTRY = "PULLBACK_ENTRY"
    RETEST_ENTRY = "RETEST_ENTRY"

    def __init__(
        self,
        momentum_days: int = 14,
        volume_short_days: int = 14,
        volume_long_days: int = 60,
        retest_tolerance_pct: Decimal | float | int | str = Decimal("2"),
    ) -> None:
        self.momentum_days = momentum_days
        self.volume_short_days = volume_short_days
        self.volume_long_days = volume_long_days
        self.retest_tolerance_pct = _to_decimal(retest_tolerance_pct)

    def _calculate_momentum_vs_btc(
        self,
        asset_prices: Sequence[Decimal | float | int | str],
        btc_prices: Sequence[Decimal | float | int | str],
    ) -> Decimal:
        asset_return = self._calculate_return(asset_prices, self.momentum_days)
        btc_return = self._calculate_return(btc_prices, self.momentum_days)
        return asset_return - btc_return

    def _calculate_volume_expansion(
        self,
        volumes: Sequence[Decimal | float | int | str],
    ) -> Decimal:
        if len(volumes) < self.volume_long_days:
            raise ValueError("Not enough volume data for long lookback.")
        decimal_volumes = [_to_decimal(value) for value in volumes]
        short_window = decimal_volumes[-self.volume_short_days :]
        long_window = decimal_volumes[-self.volume_long_days :]
        short_avg = _average(short_window)
        long_avg = _average(long_window)
        if long_avg == 0:
            raise ValueError("Long-term average volume cannot be zero.")
        return short_avg / long_avg

    def _check_entry_signal(
        self,
        current_price: Decimal | float | int | str,
        recent_high: Decimal | float | int | str,
        breakout_level: Optional[Decimal | float | int | str] = None,
    ) -> str:
        current_price = _to_decimal(current_price)
        recent_high = _to_decimal(recent_high)

        if current_price >= recent_high:
            return self.NO_SIGNAL

        pullback_pct = (recent_high - current_price) / recent_high * Decimal("100")

        if breakout_level is not None:
            breakout_level = _to_decimal(breakout_level)
            retest_pct = (
                (current_price - breakout_level).copy_abs() / breakout_level * Decimal("100")
            )
            if retest_pct <= self.retest_tolerance_pct:
                return self.RETEST_ENTRY

        if pullback_pct < Decimal("30"):
            return self.WAIT_CONFIRMATION
        if pullback_pct <= Decimal("50"):
            return self.PULLBACK_ENTRY
        return self.WAIT_CONFIRMATION

    def _calculate_return(
        self,
        prices: Sequence[Decimal | float | int | str],
        lookback_days: int,
    ) -> Decimal:
        if len(prices) < lookback_days + 1:
            raise ValueError("Not enough price data for lookback window.")
        decimal_prices = [_to_decimal(price) for price in prices]
        start_price = decimal_prices[-(lookback_days + 1)]
        end_price = decimal_prices[-1]
        if start_price == 0:
            raise ValueError("Start price cannot be zero.")
        return (end_price - start_price) / start_price

    def rank(
        self,
        asset_data: Mapping[str, Mapping[str, Sequence[Decimal | float | int | str]]],
        btc_prices: Sequence[Decimal | float | int | str],
    ) -> list[AssetScore]:
        ranked: list[AssetScore] = []
        for symbol, data in asset_data.items():
            prices = data["prices"]
            volumes = data["volumes"]
            breakout_level = data.get("breakout_level")

            recent_prices = [_to_decimal(price) for price in prices]
            if len(recent_prices) < self.volume_long_days:
                continue
            recent_high = max(recent_prices[-self.volume_long_days :])
            current_price = recent_prices[-1]
            entry_signal = self._check_entry_signal(
                current_price=current_price,
                recent_high=recent_high,
                breakout_level=breakout_level,
            )
            if entry_signal not in {self.PULLBACK_ENTRY, self.RETEST_ENTRY}:
                continue

            momentum_vs_btc = self._calculate_momentum_vs_btc(prices, btc_prices)
            volume_expansion = self._calculate_volume_expansion(volumes)
            score = momentum_vs_btc + volume_expansion

            ranked.append(
                AssetScore(
                    symbol=symbol,
                    momentum_vs_btc=momentum_vs_btc,
                    volume_expansion=volume_expansion,
                    entry_signal=entry_signal,
                    score=score,
                )
            )

        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked
