# Codex Review Request

**Date**: 2026-01-17
**Request**: Full system review before production deployment

---

## What Was Built

A complete crypto trading analysis system with the following modules:

### 1. Core Modules (Pre-existing, Tested)
- `src/gates/fee_gate.py` - Fee-positivity enforcement
- `src/gates/regime_gate.py` - Market regime detection
- `src/sizing/position_sizer.py` - Volatility-based position sizing
- `src/rotation/asset_ranker.py` - Asset ranking with entry signals
- `src/core/capital_allocator.py` - Capital allocation enforcement

### 2. New Modules (Just Built)
- `src/exchange/kraken_client.py` - Kraken API client for market data
- `src/orchestrator/trading_orchestrator.py` - Main orchestrator tying all modules
- `src/cli/main.py` - Command-line interface

---

## Test Status

**30/31 tests passing**

```
PASSED tests/test_asset_ranker.py::test_calculate_momentum_vs_btc
PASSED tests/test_asset_ranker.py::test_calculate_volume_expansion
PASSED tests/test_asset_ranker.py::test_check_entry_signal_states
PASSED tests/test_asset_ranker.py::test_rank_filters_and_sorts
PASSED tests/test_capital_allocator.py::TestCapitalAllocator::test_default_allocations
PASSED tests/test_capital_allocator.py::TestCapitalAllocator::test_core_deployment_allowed
PASSED tests/test_capital_allocator.py::TestCapitalAllocator::test_core_over_deployment_blocked
PASSED tests/test_capital_allocator.py::TestCapitalAllocator::test_reserve_deployment_blocked
PASSED tests/test_capital_allocator.py::TestCapitalAllocator::test_experiment_deployment_allowed
PASSED tests/test_capital_allocator.py::TestCapitalAllocator::test_thin_grid_warning
PASSED tests/test_capital_allocator.py::TestCapitalAllocator::test_deploy_and_release
FAILED tests/test_capital_allocator.py::TestCapitalAllocator::test_reserve_use_requires_drawdown
PASSED tests/test_capital_allocator.py::TestCapitalAllocator::test_equity_update
... (all fee_gate and position_sizer tests passing)
```

### Known Issue
One test failing: `test_reserve_use_requires_drawdown`
- **Cause**: Logic bug in `capital_allocator.py` line 260 - drawdown calculation inverted
- **Current behavior**: Allows reserve use when NO capital deployed (100% "drawdown")
- **Expected**: Should require actual drawdown before allowing reserve use
- **Impact**: Low risk - reserve access is manually triggered

---

## Review Checklist for Codex

### 1. Critical Path Review
- [ ] Fee gate formula: `grid_step >= k * C` where `C = 2*fee + spread + slippage`
- [ ] Position sizing: `size = (equity * risk_budget) / stop_distance`
- [ ] Capital allocation: 61% core, 24% reserve, 15% experiments
- [ ] Entry signals: Only PULLBACK_ENTRY (30-50% from high) or RETEST_ENTRY

### 2. Integration Points
- [ ] Orchestrator correctly wires all modules
- [ ] CLI commands work: `health`, `status`, `scan`, `ticker`
- [ ] Error handling in Kraken client (rate limiting, retries)

### 3. Risk Management
- [ ] Position sizing respects max_position_pct (20%)
- [ ] Minimum position size enforced ($100)
- [ ] Reserve funds cannot be deployed directly
- [ ] Stop percentages calculated from volatility

### 4. Code Quality
- [ ] All Decimal math (no float contamination)
- [ ] Type hints on all public methods
- [ ] Dataclasses for structured data
- [ ] No hardcoded magic numbers (use constants)

### 5. Missing Tests (To Add)
- [ ] Tests for `kraken_client.py`
- [ ] Tests for `trading_orchestrator.py`
- [ ] Tests for CLI commands
- [ ] Integration tests with mocked Kraken API

---

## File Structure

```
C:\Users\dusti\trading-system\
|-- src/
|   |-- __init__.py
|   |-- core/
|   |   |-- __init__.py
|   |   |-- capital_allocator.py   # Capital split enforcement
|   |-- exchange/
|   |   |-- __init__.py
|   |   |-- kraken_client.py       # NEW: Kraken API client
|   |-- gates/
|   |   |-- __init__.py
|   |   |-- fee_gate.py            # Fee-positivity gate
|   |   |-- regime_gate.py         # Market regime detection
|   |-- orchestrator/
|   |   |-- __init__.py
|   |   |-- trading_orchestrator.py # NEW: Main orchestrator
|   |-- rotation/
|   |   |-- __init__.py
|   |   |-- asset_ranker.py        # Asset ranking
|   |-- sizing/
|   |   |-- __init__.py
|   |   |-- position_sizer.py      # Volatility sizing
|   |-- cli/
|   |   |-- __init__.py
|   |   |-- main.py                # NEW: CLI interface
|-- tests/
|   |-- test_asset_ranker.py
|   |-- test_capital_allocator.py
|   |-- test_fee_gate.py
|   |-- test_position_sizer.py
|-- config/
|   |-- (empty - for future config files)
|-- requirements.txt
|-- pyproject.toml
```

---

## CLI Usage

```bash
# Check system health
python -m src.cli.main health

# Show system status
python -m src.cli.main status --equity 4100

# Scan for opportunities
python -m src.cli.main scan --equity 4100 --risk 0.5

# Get ticker for a pair
python -m src.cli.main ticker BTC --volatility
```

---

## Environment

- Python 3.14
- Exchange: Kraken (spot trading)
- User equity: ~$4,100
- Kraken credentials: Set via `KRAKEN_API_KEY` and `KRAKEN_API_SECRET` env vars

---

## Next Steps After Review

1. Fix the reserve drawdown test bug
2. Add tests for new modules (kraken_client, orchestrator, CLI)
3. Add integration tests with mocked API
4. Consider adding signal logging/persistence
5. Create execution module (optional - currently analysis only)

---

## How to Run Review

```bash
cd C:\Users\dusti\trading-system

# Run all tests
python -m pytest tests/ -v

# Check CLI works
python -m src.cli.main health

# Review key files
# - src/orchestrator/trading_orchestrator.py (main logic)
# - src/exchange/kraken_client.py (API integration)
# - src/cli/main.py (user interface)
```

---

**Please review the above and report any issues, bugs, or improvements needed.**
