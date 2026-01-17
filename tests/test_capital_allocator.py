"""
Tests for Capital Allocator

Run with: python -m pytest tests/test_capital_allocator.py -v
"""

import pytest
from decimal import Decimal
from src.core.capital_allocator import CapitalAllocator, AllocationBucket


class TestCapitalAllocator:
    """Test capital allocation enforcement."""

    def setup_method(self):
        """Set up test fixtures."""
        self.allocator = CapitalAllocator(total_equity=Decimal("4100"))

    def test_default_allocations(self):
        """Verify default allocation percentages."""
        state = self.allocator.get_state()

        # Core: 61% of 4100 = 2501
        assert state.core_bot >= Decimal("2500")
        assert state.core_bot <= Decimal("2510")

        # Reserve: 24% of 4100 = 984
        assert state.reserve >= Decimal("980")
        assert state.reserve <= Decimal("1000")

        # Experiments: 15% of 4100 = 615
        assert state.experiments >= Decimal("610")
        assert state.experiments <= Decimal("620")

    def test_core_deployment_allowed(self):
        """Should allow deployment within core limits."""
        check = self.allocator.can_deploy(AllocationBucket.CORE_BOT, Decimal("800"))
        assert check.allowed is True

    def test_core_over_deployment_blocked(self):
        """Should block deployment exceeding core limit."""
        check = self.allocator.can_deploy(AllocationBucket.CORE_BOT, Decimal("3000"))
        assert check.allowed is False
        assert "Insufficient" in check.message

    def test_reserve_deployment_blocked(self):
        """Reserve should never be deployed directly."""
        check = self.allocator.can_deploy(AllocationBucket.RESERVE, Decimal("100"))
        assert check.allowed is False
        assert "Reserve funds cannot be deployed" in check.message

    def test_experiment_deployment_allowed(self):
        """Should allow experiment deployment within limits."""
        check = self.allocator.can_deploy(AllocationBucket.EXPERIMENTS, Decimal("400"))
        assert check.allowed is True

    def test_thin_grid_warning(self):
        """Should warn about thin grids."""
        # Deploy most of core
        self.allocator.deploy(AllocationBucket.CORE_BOT, Decimal("2200"))

        # Try to deploy more, leaving thin remainder
        check = self.allocator.can_deploy(AllocationBucket.CORE_BOT, Decimal("200"))
        assert check.allowed is True
        assert len(check.warnings) > 0
        assert any("thin" in w.lower() for w in check.warnings)

    def test_deploy_and_release(self):
        """Should track deployments and releases."""
        # Deploy
        self.allocator.deploy(AllocationBucket.CORE_BOT, Decimal("1000"))
        assert self.allocator.get_available(AllocationBucket.CORE_BOT) < Decimal("1600")

        # Release
        self.allocator.release(AllocationBucket.CORE_BOT, Decimal("500"))
        available = self.allocator.get_available(AllocationBucket.CORE_BOT)
        assert available > Decimal("2000")

    def test_reserve_use_requires_drawdown(self):
        """Reserve use should only be allowed after significant drawdown."""
        # No drawdown - should fail
        check = self.allocator.use_reserve(Decimal("500"), "test")
        assert check.allowed is False
        assert "below 15%" in check.message

        # Simulate drawdown by reducing equity
        self.allocator.update_equity(Decimal("3000"))

        # Now should work
        check = self.allocator.use_reserve(Decimal("500"), "drawdown recovery")
        assert check.allowed is True

    def test_equity_update(self):
        """Should recalculate buckets on equity update."""
        self.allocator.update_equity(Decimal("5000"))

        state = self.allocator.get_state()
        assert state.total_equity == Decimal("5000")
        assert state.core_bot > Decimal("2500")  # 61% of 5000 = 3050

    def test_summary_output(self):
        """Should generate readable summary."""
        summary = self.allocator.get_summary()

        assert "Capital Allocation Summary" in summary
        assert "CORE_BOT" in summary
        assert "RESERVE" in summary
        assert "EXPERIMENTS" in summary


class TestAllocationEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_equity(self):
        """Should handle zero equity gracefully."""
        allocator = CapitalAllocator(total_equity=Decimal("0"))
        state = allocator.get_state()
        assert state.core_bot == Decimal("0")

    def test_small_equity(self):
        """Should work with very small equity."""
        allocator = CapitalAllocator(total_equity=Decimal("100"))
        state = allocator.get_state()
        # 61% of 100 = 61
        assert state.core_bot >= Decimal("60")

    def test_custom_allocations(self):
        """Should accept custom allocation percentages."""
        custom = {
            AllocationBucket.CORE_BOT: Decimal("0.70"),
            AllocationBucket.RESERVE: Decimal("0.20"),
            AllocationBucket.EXPERIMENTS: Decimal("0.10")
        }
        allocator = CapitalAllocator(
            total_equity=Decimal("4100"),
            allocations=custom
        )
        state = allocator.get_state()
        # 70% of 4100 = 2870
        assert state.core_bot >= Decimal("2870")

    def test_invalid_allocations_rejected(self):
        """Should reject allocations that don't sum to 1.0."""
        invalid = {
            AllocationBucket.CORE_BOT: Decimal("0.50"),
            AllocationBucket.RESERVE: Decimal("0.20"),
            AllocationBucket.EXPERIMENTS: Decimal("0.10")
        }
        with pytest.raises(ValueError):
            CapitalAllocator(total_equity=Decimal("4100"), allocations=invalid)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
