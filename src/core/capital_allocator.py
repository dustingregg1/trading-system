"""
Capital Allocation Enforcer

Prevents self-sabotage by enforcing strict capital boundaries:
- Core (bot): 61% - $2,500 - DO NOT TOUCH
- Reserve: 24% - $1,000 - Drawdown buffer only
- Experiments: 15% - $600 - Ring-fenced discretionary

This module tracks allocations and blocks operations that would
violate the structure.
"""

from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass
from typing import Optional, Dict
from enum import Enum
from datetime import datetime
import json
from pathlib import Path


class AllocationBucket(Enum):
    """Capital allocation buckets."""
    CORE_BOT = "core_bot"
    RESERVE = "reserve"
    EXPERIMENTS = "experiments"


@dataclass
class AllocationState:
    """Current state of capital allocation."""
    total_equity: Decimal
    core_bot: Decimal
    reserve: Decimal
    experiments: Decimal
    core_bot_deployed: Decimal  # Amount currently in positions
    experiments_deployed: Decimal
    last_updated: datetime


@dataclass
class AllocationCheck:
    """Result of allocation check."""
    allowed: bool
    bucket: AllocationBucket
    requested: Decimal
    available: Decimal
    message: str
    warnings: list


class CapitalAllocator:
    """
    Enforces capital allocation rules.

    Usage:
        allocator = CapitalAllocator(total_equity=Decimal("4100"))

        # Check if we can deploy $800 to core bot
        check = allocator.can_deploy(AllocationBucket.CORE_BOT, Decimal("800"))
        if check.allowed:
            allocator.deploy(AllocationBucket.CORE_BOT, Decimal("800"))
    """

    # Default allocation percentages
    DEFAULT_ALLOCATIONS = {
        AllocationBucket.CORE_BOT: Decimal("0.61"),
        AllocationBucket.RESERVE: Decimal("0.24"),
        AllocationBucket.EXPERIMENTS: Decimal("0.15")
    }

    # Minimum thresholds
    MIN_CORE_POSITION = Decimal("500")  # Don't create thin grids
    THIN_GRID_WARNING = Decimal("400")

    def __init__(
        self,
        total_equity: Decimal,
        allocations: Optional[Dict[AllocationBucket, Decimal]] = None,
        state_file: Optional[Path] = None
    ):
        """
        Initialize allocator.

        Args:
            total_equity: Total account equity in USD
            allocations: Custom allocation percentages (must sum to 1.0)
            state_file: Path to persist state (optional)
        """
        self.total_equity = Decimal(str(total_equity))
        self.allocations = allocations or self.DEFAULT_ALLOCATIONS

        # Validate allocations sum to 1.0
        total_pct = sum(self.allocations.values())
        if abs(total_pct - Decimal("1.0")) > Decimal("0.001"):
            raise ValueError(f"Allocations must sum to 1.0, got {total_pct}")

        # Calculate bucket amounts
        self.bucket_amounts = {
            bucket: (self.total_equity * pct).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            for bucket, pct in self.allocations.items()
        }
        self.initial_total_equity = self.total_equity
        self.initial_core_allocation = self.bucket_amounts[AllocationBucket.CORE_BOT]

        # Track deployed capital
        self.deployed = {
            AllocationBucket.CORE_BOT: Decimal("0"),
            AllocationBucket.RESERVE: Decimal("0"),  # Reserve shouldn't be deployed
            AllocationBucket.EXPERIMENTS: Decimal("0")
        }

        self.state_file = state_file

    def get_available(self, bucket: AllocationBucket) -> Decimal:
        """Get available (undeployed) capital in a bucket."""
        return self.bucket_amounts[bucket] - self.deployed[bucket]

    def get_state(self) -> AllocationState:
        """Get current allocation state."""
        return AllocationState(
            total_equity=self.total_equity,
            core_bot=self.bucket_amounts[AllocationBucket.CORE_BOT],
            reserve=self.bucket_amounts[AllocationBucket.RESERVE],
            experiments=self.bucket_amounts[AllocationBucket.EXPERIMENTS],
            core_bot_deployed=self.deployed[AllocationBucket.CORE_BOT],
            experiments_deployed=self.deployed[AllocationBucket.EXPERIMENTS],
            last_updated=datetime.now()
        )

    def can_deploy(
        self,
        bucket: AllocationBucket,
        amount: Decimal
    ) -> AllocationCheck:
        """
        Check if deployment is allowed.

        Args:
            bucket: Which bucket to deploy from
            amount: Amount in USD to deploy

        Returns:
            AllocationCheck with allowed status and details
        """
        amount = Decimal(str(amount))
        available = self.get_available(bucket)
        warnings = []

        # Reserve should never be deployed directly
        if bucket == AllocationBucket.RESERVE:
            return AllocationCheck(
                allowed=False,
                bucket=bucket,
                requested=amount,
                available=available,
                message="Reserve funds cannot be deployed directly. Use for drawdown recovery only.",
                warnings=["Reserve bucket is for emergencies only"]
            )

        # Check if amount exceeds available
        if amount > available:
            return AllocationCheck(
                allowed=False,
                bucket=bucket,
                requested=amount,
                available=available,
                message=f"Insufficient {bucket.value} funds. Requested ${amount}, available ${available}",
                warnings=[]
            )

        # Check for thin grid warning
        if bucket == AllocationBucket.CORE_BOT:
            remaining_after = available - amount
            if remaining_after < self.THIN_GRID_WARNING and remaining_after > 0:
                warnings.append(
                    f"Warning: Only ${remaining_after} will remain in core. "
                    f"Positions below ${self.THIN_GRID_WARNING} create thin grids."
                )

        # Check minimum position size for core
        if bucket == AllocationBucket.CORE_BOT and amount < self.MIN_CORE_POSITION:
            warnings.append(
                f"Warning: ${amount} is below minimum recommended position (${self.MIN_CORE_POSITION}). "
                f"Consider consolidating or skipping."
            )

        return AllocationCheck(
            allowed=True,
            bucket=bucket,
            requested=amount,
            available=available,
            message=f"Deployment of ${amount} from {bucket.value} approved.",
            warnings=warnings
        )

    def deploy(
        self,
        bucket: AllocationBucket,
        amount: Decimal,
        force: bool = False
    ) -> bool:
        """
        Record deployment of capital.

        Args:
            bucket: Which bucket to deploy from
            amount: Amount in USD
            force: Skip checks (use carefully)

        Returns:
            True if deployed, False if rejected
        """
        amount = Decimal(str(amount))

        if not force:
            check = self.can_deploy(bucket, amount)
            if not check.allowed:
                return False

        self.deployed[bucket] += amount
        self._save_state()
        return True

    def release(self, bucket: AllocationBucket, amount: Decimal) -> bool:
        """
        Record release of capital (position closed).

        Args:
            bucket: Which bucket capital returns to
            amount: Amount in USD released

        Returns:
            True if recorded
        """
        amount = Decimal(str(amount))
        self.deployed[bucket] = max(Decimal("0"), self.deployed[bucket] - amount)
        self._save_state()
        return True

    def use_reserve(self, amount: Decimal, reason: str) -> AllocationCheck:
        """
        Request use of reserve funds (requires explicit reason).

        This should only happen when core has drawn down significantly.

        Args:
            amount: Amount to transfer from reserve
            reason: Why reserve is needed

        Returns:
            AllocationCheck (doesn't auto-deploy)
        """
        amount = Decimal(str(amount))
        available = self.get_available(AllocationBucket.RESERVE)

        # Check core drawdown
        drawdown_pct = self._get_core_drawdown_pct()

        warnings = []

        # Only allow reserve use if core has meaningful drawdown
        if drawdown_pct < Decimal("0.15"):
            return AllocationCheck(
                allowed=False,
                bucket=AllocationBucket.RESERVE,
                requested=amount,
                available=available,
                message=f"Reserve use denied. Core drawdown ({drawdown_pct:.1%}) below 15% threshold.",
                warnings=["Reserve is for >15% drawdown recovery only"]
            )

        if amount > available:
            return AllocationCheck(
                allowed=False,
                bucket=AllocationBucket.RESERVE,
                requested=amount,
                available=available,
                message=f"Insufficient reserve. Requested ${amount}, available ${available}",
                warnings=[]
            )

        return AllocationCheck(
            allowed=True,
            bucket=AllocationBucket.RESERVE,
            requested=amount,
            available=available,
            message=f"Reserve use of ${amount} approved. Reason: {reason}",
            warnings=[f"Deploying reserve due to {drawdown_pct:.1%} core drawdown"]
        )

    def _get_core_drawdown_pct(self) -> Decimal:
        """Calculate core drawdown based on equity changes."""
        current_core = self.bucket_amounts[AllocationBucket.CORE_BOT]
        initial_core = self.initial_core_allocation
        if initial_core <= 0:
            return Decimal("0")
        drawdown_pct = (initial_core - current_core) / initial_core
        return max(drawdown_pct, Decimal("0"))

    def update_equity(self, new_equity: Decimal):
        """
        Update total equity and recalculate buckets.

        Call this after significant P&L changes.
        """
        self.total_equity = Decimal(str(new_equity))
        self.bucket_amounts = {
            bucket: (self.total_equity * pct).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            for bucket, pct in self.allocations.items()
        }
        self._save_state()

    def _save_state(self):
        """Persist state to file if configured."""
        if self.state_file:
            state = {
                "total_equity": str(self.total_equity),
                "deployed": {k.value: str(v) for k, v in self.deployed.items()},
                "last_updated": datetime.now().isoformat()
            }
            self.state_file.write_text(json.dumps(state, indent=2))

    def _load_state(self):
        """Load state from file if exists."""
        if self.state_file and self.state_file.exists():
            state = json.loads(self.state_file.read_text())
            self.total_equity = Decimal(state["total_equity"])
            self.deployed = {
                AllocationBucket(k): Decimal(v)
                for k, v in state["deployed"].items()
            }

    def get_summary(self) -> str:
        """Get human-readable allocation summary."""
        lines = [
            "Capital Allocation Summary",
            "=" * 40,
            f"Total Equity: ${self.total_equity:,.2f}",
            "",
        ]

        for bucket in AllocationBucket:
            total = self.bucket_amounts[bucket]
            deployed = self.deployed[bucket]
            available = total - deployed
            pct = self.allocations[bucket] * 100

            lines.append(f"{bucket.value.upper()} ({pct:.0f}%)")
            lines.append(f"  Total:     ${total:,.2f}")
            lines.append(f"  Deployed:  ${deployed:,.2f}")
            lines.append(f"  Available: ${available:,.2f}")
            lines.append("")

        return "\n".join(lines)


if __name__ == "__main__":
    # Demo usage
    allocator = CapitalAllocator(total_equity=Decimal("4100"))

    print(allocator.get_summary())

    print("\nDeployment Tests")
    print("-" * 40)

    # Test core deployment
    check = allocator.can_deploy(AllocationBucket.CORE_BOT, Decimal("800"))
    print(f"\nDeploy $800 to core: {check.allowed}")
    print(f"  Message: {check.message}")
    if check.warnings:
        for w in check.warnings:
            print(f"  Warning: {w}")

    # Test reserve deployment (should fail)
    check = allocator.can_deploy(AllocationBucket.RESERVE, Decimal("500"))
    print(f"\nDeploy $500 from reserve: {check.allowed}")
    print(f"  Message: {check.message}")

    # Test experiment deployment
    check = allocator.can_deploy(AllocationBucket.EXPERIMENTS, Decimal("400"))
    print(f"\nDeploy $400 to experiments: {check.allowed}")
    print(f"  Message: {check.message}")

    # Test over-allocation
    check = allocator.can_deploy(AllocationBucket.EXPERIMENTS, Decimal("1000"))
    print(f"\nDeploy $1000 to experiments: {check.allowed}")
    print(f"  Message: {check.message}")
