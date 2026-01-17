"""
Tests for Fee-Positivity Gate

Run with: python -m pytest tests/test_fee_gate.py -v
"""

import pytest
from decimal import Decimal
from src.gates.fee_gate import FeeGate, FeeStructure, check_fee_positive


class TestFeeGate:
    """Test fee gate functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.gate = FeeGate(k_factor=Decimal("3"))

    def test_btc_tight_spread_passes(self):
        """BTC with sufficient step should pass."""
        result = self.gate.evaluate("BTC/USD", Decimal("0.005"))  # 0.5%
        assert result.passed is True

    def test_btc_tight_step_fails(self):
        """BTC with step too tight should fail."""
        result = self.gate.evaluate("BTC/USD", Decimal("0.001"))  # 0.1%
        assert result.passed is False
        assert result.recommendation is not None

    def test_altcoin_default_fees(self):
        """Unknown pairs should use conservative default."""
        result = self.gate.evaluate("SHIB/USD", Decimal("0.005"))  # 0.5%
        # Default has higher spread, so 0.5% might not be enough
        # Just verify it uses default structure
        structure = self.gate.get_fee_structure("SHIB/USD")
        assert structure.typical_spread == Decimal("0.0020")

    def test_minimum_step_calculation(self):
        """Verify minimum step calculation."""
        min_step = self.gate.calculate_minimum_step("ETH/USD")
        # ETH: spread=0.06%, slippage=0.02%, mixed fee~0.02%
        # C = 0.02% + 0.06% + 0.02% = 0.10%
        # min = 0.10% * 3 = 0.30%
        assert min_step >= Decimal("0.0025")  # At least 0.25%
        assert min_step <= Decimal("0.0050")  # No more than 0.50%

    def test_maker_only_mode(self):
        """Maker-only mode should have lower costs."""
        gate_mixed = FeeGate(k_factor=Decimal("3"), assume_mixed=True)
        gate_maker = FeeGate(k_factor=Decimal("3"), assume_mixed=False)

        min_mixed = gate_mixed.calculate_minimum_step("BTC/USD")
        min_maker = gate_maker.calculate_minimum_step("BTC/USD")

        # Maker-only should be lower (or equal if maker rebate covers)
        assert min_maker <= min_mixed

    def test_evaluate_all(self):
        """Test batch evaluation."""
        config = {
            "BTC/USD": {"step": Decimal("0.005")},
            "ETH/USD": {"step": Decimal("0.003")},
            "PEPE/USD": {"step": Decimal("0.002")}  # Too tight for illiquid
        }
        results = self.gate.evaluate_all(config)

        assert len(results) == 3
        assert "BTC/USD" in results
        assert results["BTC/USD"].passed is True

    def test_convenience_function(self):
        """Test quick check function."""
        assert check_fee_positive("BTC/USD", 0.005, k=3) is True
        assert check_fee_positive("BTC/USD", 0.001, k=3) is False

    def test_k_factor_impact(self):
        """Higher k-factor should require wider steps."""
        gate_k2 = FeeGate(k_factor=Decimal("2"))
        gate_k4 = FeeGate(k_factor=Decimal("4"))

        min_k2 = gate_k2.calculate_minimum_step("BTC/USD")
        min_k4 = gate_k4.calculate_minimum_step("BTC/USD")

        assert min_k4 > min_k2
        assert min_k4 == min_k2 * 2  # k4/k2 = 2


class TestFeeStructure:
    """Test fee structure calculations."""

    def test_round_trip_costs(self):
        """Verify round-trip cost calculations."""
        structure = FeeStructure(
            maker_fee=Decimal("-0.0002"),
            taker_fee=Decimal("0.0004"),
            typical_spread=Decimal("0.0005"),
            slippage_buffer=Decimal("0.0002")
        )

        # Maker only: 2*(-0.02%) + 0.05% + 0.02% = -0.04% + 0.07% = 0.03%
        maker_cost = structure.round_trip_cost_maker_only
        assert maker_cost == Decimal("0.0003")

        # Mixed: -0.02% + 0.04% + 0.05% + 0.02% = 0.09%
        mixed_cost = structure.round_trip_cost_mixed
        assert mixed_cost == Decimal("0.0009")

        # Taker only: 2*(0.04%) + 0.05% + 0.02% = 0.08% + 0.07% = 0.15%
        taker_cost = structure.round_trip_cost_taker_only
        assert taker_cost == Decimal("0.0015")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
