# HANDOFF - Claude/ChatGPT Task Coordination

## How This Works
1. Each AI marks tasks they're working on
2. Completed work gets committed with clear messages
3. Use this file to pass context and assignments
4. **Pull before starting, push after completing**

---

## Repository Location
`C:\Users\dusti\trading-system\`

---

## Current Sprint: Core Infrastructure

### Claude (Completed)
- [x] Repository setup and structure
- [x] Config files (capital_allocation.json, fee_structure.json, risk_parameters.json)
- [x] `src/gates/fee_gate.py` - Fee-positivity enforcement
- [x] `src/gates/regime_gate.py` - Market regime detection
- [x] `src/core/capital_allocator.py` - Capital split enforcement
- [x] `tests/test_fee_gate.py` - Unit tests
- [x] `tests/test_capital_allocator.py` - Unit tests

### ChatGPT (Assigned) - PRIORITY ORDER

#### 1. Position Sizer (HIGH PRIORITY)
**File**: `src/sizing/position_sizer.py`

Implement the `VolatilityPositionSizer` class:

```python
def calculate(self, asset_volatility_pct, current_price, custom_stop_pct=None):
    """
    Core formula: position_size = (equity * risk_budget) / stop_distance

    Steps:
    1. stop_distance = custom_stop_pct or (asset_volatility_pct * 1.5)
    2. raw_size = (equity * risk_budget_pct) / stop_distance
    3. Apply max_position_pct cap
    4. Apply min_position_usd floor (skip if below)
    5. Calculate units: size_usd / current_price
    """
```

**Test file needed**: `tests/test_position_sizer.py`

#### 2. Asset Ranker (MEDIUM PRIORITY)
**File**: `src/rotation/asset_ranker.py`

Implement the `AssetRanker` class with:
- `_calculate_momentum_vs_btc()` - 14D return differential
- `_calculate_volume_expansion()` - 14D/60D volume ratio
- `_check_entry_signal()` - Pullback detection (30-50% from high)
- `rank()` - Full ranking pipeline

**Key rule**: NO day-1 pump entries. Must wait for pullback or retest.

#### 3. Kraken Integration (OPTIONAL)
**File**: `src/exchange/kraken_client.py`

If time permits, create a simple Kraken client for:
- Fetching OHLCV data
- Getting current spreads
- Checking 24h volume

---

## Context for ChatGPT

### User's Trading Situation
- **Capital**: ~$4,100
- **Exchange**: Kraken spot
- **Problem**: Previously lost money to fee churn in low-volatility chop
- **Maker fee**: -0.02% (rebate)
- **Taker fee**: 0.04%

### Capital Allocation (ENFORCED)
| Bucket | Percent | Amount | Rule |
|--------|---------|--------|------|
| Core Bot | 61% | $2,500 | Never touch for discretionary |
| Reserve | 24% | $1,000 | Only use if core draws down >15% |
| Experiments | 15% | $600 | Ring-fenced, strict rules |

### Key Formulas

**Position Sizing**:
```
position_size = (equity * risk_budget_pct) / stop_pct

Example: $4100 equity, 0.5% risk, 20% stop
= (4100 * 0.005) / 0.20 = $102.50
```

**Fee Gate**:
```
C = 2*fee + spread + slippage
grid_step >= k * C  (k=3 recommended)

If step < minimum → widen or skip pair
```

**Entry Signal (for rotation)**:
- NO_SIGNAL: At or near high (day-1 pump)
- WAIT_CONFIRMATION: Pulled back <30%
- PULLBACK_ENTRY: Pulled back 30-50% ✓
- RETEST_ENTRY: Testing previous breakout ✓

---

## Code Standards

1. **Use Decimal** for all financial calculations (not float)
2. **Type hints** on all functions
3. **Docstrings** with examples
4. **Keep functions pure** where possible
5. **Tests required** for all new modules

---

## Git Workflow

```bash
# Before starting
git pull origin main

# After completing a module
git add .
git commit -m "feat(sizing): implement VolatilityPositionSizer"
git push origin main
```

Commit message format:
- `feat(module): description` - New feature
- `fix(module): description` - Bug fix
- `test(module): description` - Tests
- `docs: description` - Documentation

---

## Files Ready for ChatGPT

These files have skeletons with TODO-GPT markers:

1. `src/sizing/position_sizer.py` - **Needs implementation**
2. `src/rotation/asset_ranker.py` - **Needs implementation**

---

## Completed Handoffs

### 2025-01-17 - Claude → ChatGPT
**What was done**:
- Created full repository structure
- Implemented fee gate with Kraken fee structures
- Implemented regime gate (ATR compression, BTC dominance, funding rates)
- Implemented capital allocator with bucket enforcement
- Created config files with user's actual numbers
- Wrote unit tests for completed modules

**What's needed from ChatGPT**:
1. Implement `VolatilityPositionSizer` class
2. Implement `AssetRanker` class
3. Write tests for both
4. (Optional) Kraken data fetching

---

## Questions for User (If Needed)
- What's your Kraken API key situation? (for live data fetching)
- Do you want real-time spread fetching or use estimates?
- Which pairs should be in the rotation universe?

---

## Success Criteria

When ChatGPT is done, the system should:
1. Calculate position sizes based on volatility ✓
2. Rank assets by momentum + volume + volatility ✓
3. Only signal entries on pullbacks (no pump chasing) ✓
4. All tests pass ✓
