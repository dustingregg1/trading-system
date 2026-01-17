from decimal import Decimal

from src.rotation.asset_ranker import AssetRanker


def _build_price_series(current_price: Decimal, recent_high: Decimal) -> list[Decimal]:
    base = [Decimal("100")] * 44
    base.append(recent_high)
    base.extend([Decimal("100")] * 14)
    base.append(current_price)
    return base


def test_calculate_momentum_vs_btc() -> None:
    ranker = AssetRanker()
    asset_prices = [Decimal("100")] * 45 + [Decimal("100")] * 14 + [Decimal("110")]
    btc_prices = [Decimal("100")] * 45 + [Decimal("100")] * 14 + [Decimal("105")]

    momentum = ranker._calculate_momentum_vs_btc(asset_prices, btc_prices)

    assert momentum.quantize(Decimal("0.0001")) == Decimal("0.0500")


def test_calculate_volume_expansion() -> None:
    ranker = AssetRanker()
    volumes = [Decimal("100")] * 46 + [Decimal("200")] * 14

    expansion = ranker._calculate_volume_expansion(volumes)

    assert expansion.quantize(Decimal("0.0001")) == Decimal("1.6216")


def test_check_entry_signal_states() -> None:
    ranker = AssetRanker()

    assert (
        ranker._check_entry_signal(current_price=Decimal("100"), recent_high=Decimal("100"))
        == ranker.NO_SIGNAL
    )
    assert (
        ranker._check_entry_signal(current_price=Decimal("80"), recent_high=Decimal("100"))
        == ranker.WAIT_CONFIRMATION
    )
    assert (
        ranker._check_entry_signal(current_price=Decimal("60"), recent_high=Decimal("100"))
        == ranker.PULLBACK_ENTRY
    )
    assert (
        ranker._check_entry_signal(
            current_price=Decimal("109"),
            recent_high=Decimal("130"),
            breakout_level=Decimal("108"),
        )
        == ranker.RETEST_ENTRY
    )


def test_rank_filters_and_sorts() -> None:
    ranker = AssetRanker()
    asset_a_prices = _build_price_series(Decimal("110"), Decimal("130"))
    asset_b_prices = _build_price_series(Decimal("130"), Decimal("130"))

    asset_data = {
        "ASSET_A": {
            "prices": asset_a_prices,
            "volumes": [Decimal("100")] * 46 + [Decimal("200")] * 14,
            "breakout_level": Decimal("108"),
        },
        "ASSET_B": {
            "prices": asset_b_prices,
            "volumes": [Decimal("120")] * 60,
        },
    }
    btc_prices = [Decimal("100")] * 45 + [Decimal("100")] * 14 + [Decimal("105")]

    ranked = ranker.rank(asset_data, btc_prices)

    assert [item.symbol for item in ranked] == ["ASSET_A"]
    assert ranked[0].entry_signal == ranker.RETEST_ENTRY
