"""
Trading System CLI
==================
Simple command-line interface for running the trading system.

Usage:
    python -m src.cli.main scan          # Scan for opportunities
    python -m src.cli.main status        # Show system status
    python -m src.cli.main ticker BTC    # Get ticker for a pair
    python -m src.cli.main health        # Check system health
"""

import argparse
import sys
import logging
from decimal import Decimal
from typing import Optional

from ..orchestrator import TradingOrchestrator
from ..exchange import KrakenClient


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S"
    )


def cmd_scan(args):
    """Scan for trading opportunities."""
    print("\n" + "=" * 60)
    print("TRADING SYSTEM - OPPORTUNITY SCAN")
    print("=" * 60)

    try:
        orchestrator = TradingOrchestrator(
            total_equity=Decimal(str(args.equity)),
            risk_budget_pct=Decimal(str(args.risk))
        )

        print(f"\nEquity: ${args.equity:,.2f}")
        print(f"Risk per trade: {args.risk}%")
        print("-" * 60)

        signals = orchestrator.scan_for_opportunities(
            pairs=args.pairs.split(",") if args.pairs else None,
            top_n=args.top
        )

        if not signals:
            print("\n[!] No opportunities found matching all criteria.")
            print("\nPossible reasons:")
            print("  - No assets have pullback entries (30-50% from high)")
            print("  - Fee gate rejecting due to low volatility")
            print("  - Regime gate in risk-off mode")
            return

        print(f"\n[OK] Found {len(signals)} opportunity(ies):\n")

        for i, signal in enumerate(signals, 1):
            print(f"[{i}] {signal.pair}")
            print(f"    Price: ${signal.price:,.2f}")
            print(f"    Entry: {signal.entry_signal}")
            print(f"    Score: {signal.score:.4f}")
            print(f"    Position: ${signal.position_size_usd:,.2f} ({signal.units:.6f} units)")
            print(f"    Stop: {signal.stop_pct:.2f}%")

            # Show gate status
            gates = signal.checks_passed
            gate_status = []
            for gate, passed in gates.items():
                icon = "OK" if passed else "X"
                gate_status.append(f"{gate}:{icon}")
            print(f"    Gates: {' | '.join(gate_status)}")
            print()

    except Exception as e:
        logging.error(f"Scan failed: {e}")
        if args.verbose:
            raise
        sys.exit(1)


def cmd_status(args):
    """Show system status summary."""
    print("\n" + "=" * 60)
    print("TRADING SYSTEM STATUS")
    print("=" * 60)

    try:
        orchestrator = TradingOrchestrator(
            total_equity=Decimal(str(args.equity)),
            risk_budget_pct=Decimal(str(args.risk))
        )

        print(orchestrator.get_summary())

    except Exception as e:
        logging.error(f"Status check failed: {e}")
        if args.verbose:
            raise
        sys.exit(1)


def cmd_ticker(args):
    """Get ticker data for a pair."""
    pair = f"{args.symbol.upper()}/USD"
    print(f"\nFetching ticker for {pair}...")

    try:
        client = KrakenClient()
        ticker = client.get_ticker(pair)

        if ticker is None:
            print(f"[X] Could not fetch ticker for {pair}")
            sys.exit(1)

        print(f"\n{ticker.pair}")
        print("-" * 40)
        print(f"Last:      ${ticker.last:,.2f}")
        print(f"Bid:       ${ticker.bid:,.2f}")
        print(f"Ask:       ${ticker.ask:,.2f}")
        print(f"Spread:    ${ticker.spread:,.2f} ({ticker.spread_pct:.4f}%)")
        print(f"24h Vol:   {ticker.volume_24h:,.2f}")
        print(f"24h High:  ${ticker.high_24h:,.2f}")
        print(f"24h Low:   ${ticker.low_24h:,.2f}")
        print(f"VWAP:      ${ticker.vwap_24h:,.2f}")

        # Also show volatility if requested
        if args.volatility:
            vol = client.calculate_volatility_pct(pair)
            if vol:
                print(f"14D ATR%:  {vol:.2f}%")

    except Exception as e:
        logging.error(f"Ticker fetch failed: {e}")
        if args.verbose:
            raise
        sys.exit(1)


def cmd_health(args):
    """Check system health."""
    print("\n" + "=" * 60)
    print("SYSTEM HEALTH CHECK")
    print("=" * 60)

    checks = []

    # Check Kraken API
    print("\n[1] Kraken API...", end=" ")
    try:
        client = KrakenClient()
        if client.health_check():
            print("[OK]")
            checks.append(True)
        else:
            print("[FAILED]")
            checks.append(False)
    except Exception as e:
        print(f"[ERROR] {e}")
        checks.append(False)

    # Check module imports
    print("[2] Core modules...", end=" ")
    try:
        from ..gates.fee_gate import FeeGate
        from ..gates.regime_gate import RegimeGate
        from ..sizing.position_sizer import VolatilityPositionSizer
        from ..rotation.asset_ranker import AssetRanker
        from ..core.capital_allocator import CapitalAllocator
        print("[OK]")
        checks.append(True)
    except ImportError as e:
        print(f"[FAILED] {e}")
        checks.append(False)

    # Check orchestrator
    print("[3] Orchestrator...", end=" ")
    try:
        orchestrator = TradingOrchestrator(total_equity=Decimal("1000"))
        print("[OK]")
        checks.append(True)
    except Exception as e:
        print(f"[FAILED] {e}")
        checks.append(False)

    # Summary
    print("\n" + "-" * 60)
    passed = sum(checks)
    total = len(checks)
    if passed == total:
        print(f"[OK] All {total} checks passed. System healthy.")
    else:
        print(f"[X] {passed}/{total} checks passed. Issues detected.")
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Trading System CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.cli.main scan --equity 4100
  python -m src.cli.main status
  python -m src.cli.main ticker BTC --volatility
  python -m src.cli.main health
        """
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan for trading opportunities")
    scan_parser.add_argument(
        "--equity",
        type=float,
        default=4100,
        help="Total equity in USD (default: 4100)"
    )
    scan_parser.add_argument(
        "--risk",
        type=float,
        default=0.5,
        help="Risk per trade percentage (default: 0.5)"
    )
    scan_parser.add_argument(
        "--pairs",
        type=str,
        default=None,
        help="Comma-separated pairs to scan (default: all)"
    )
    scan_parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Number of top opportunities to show (default: 5)"
    )
    scan_parser.set_defaults(func=cmd_scan)

    # Status command
    status_parser = subparsers.add_parser("status", help="Show system status")
    status_parser.add_argument(
        "--equity",
        type=float,
        default=4100,
        help="Total equity in USD (default: 4100)"
    )
    status_parser.add_argument(
        "--risk",
        type=float,
        default=0.5,
        help="Risk per trade percentage (default: 0.5)"
    )
    status_parser.set_defaults(func=cmd_status)

    # Ticker command
    ticker_parser = subparsers.add_parser("ticker", help="Get ticker for a symbol")
    ticker_parser.add_argument(
        "symbol",
        type=str,
        help="Symbol to fetch (e.g., BTC, ETH, SOL)"
    )
    ticker_parser.add_argument(
        "--volatility",
        action="store_true",
        help="Also show 14-day volatility"
    )
    ticker_parser.set_defaults(func=cmd_ticker)

    # Health command
    health_parser = subparsers.add_parser("health", help="Check system health")
    health_parser.set_defaults(func=cmd_health)

    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
