# Trading System - Claude/ChatGPT Collaboration

## Purpose
Systematic trading system implementing fee-positive grid trading with risk management gates.

## Collaboration Protocol
- **Claude**: Architecture, risk logic, integration
- **ChatGPT**: Can work on any file tagged with `TODO-GPT`
- **Handoff**: Use `HANDOFF.md` for task assignments

## Core Components

### 1. Fee-Positivity Gate (CRITICAL)
```
C = 2*fee + spread + slippage_buffer
grid_step >= k * C  (k = 2-4)
```

### 2. Volatility-Based Sizing
```
position_size = risk_budget / stop_percent
```

### 3. Capital Split Structure
| Allocation | Percent | Amount | Purpose |
|------------|---------|--------|---------|
| Core (bot) | 61% | $2,500 | Grid trading, don't touch |
| Reserve | 24% | $1,000 | Drawdown buffer, recentering |
| Experiments | 15% | $600 | Discretionary, ring-fenced |

### 4. Regime Detection Gates
- ATR compression detection
- BTC dominance monitoring
- Funding rate extremes

### 5. Rules-Based Rotation (Secondary)
- Weekly rebalancing
- Pullback entries only (-30% to -50% of pump)
- Max 2-3 concurrent positions

## Directory Structure
```
trading-system/
├── config/
│   ├── capital_allocation.json
│   ├── fee_structure.json
│   └── risk_parameters.json
├── src/
│   ├── gates/
│   │   ├── fee_gate.py
│   │   ├── volatility_gate.py
│   │   └── regime_gate.py
│   ├── sizing/
│   │   └── position_sizer.py
│   ├── rotation/
│   │   └── asset_ranker.py
│   └── core/
│       └── grid_engine.py
├── tests/
├── HANDOFF.md
└── README.md
```

## Exchange
- **Primary**: Kraken Spot
- **Maker fee**: -0.02% (rebate)
- **Taker fee**: 0.04%

## Current Status
- [ ] Fee gate implementation
- [ ] Volatility sizing
- [ ] Capital allocation enforcer
- [ ] Regime detection
- [ ] Rotation ranker
